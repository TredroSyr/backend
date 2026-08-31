"""The rep app's home screen: the dashboard, the van, and the notification bell.

The screen is read-only and every figure on it is derived, so what these tests
pin down is not "does a number appear" but *which* number: that the period cards
follow the date picker, that receivables deliberately do not, that a rep sees
their own documents and van and nobody else's, and that the bell counts only
notifications addressed to them.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_rep
from apps.invoices.models import SalesInvoice
from apps.invoices.services.documents import LineInput
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.returns import create_return_invoice, issue_return_invoice
from apps.invoices.services.sales import create_sales_invoice
from apps.notifications.models import ActorType, Notification
from apps.notifications.services import STOCK_TRANSFER_DISPATCHED, notify_rep


def client_for(rep) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    return client


def make_sale(company, rep, customer, product, quantity="10", price="10.00"):
    return create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product,
                quantity=Decimal(quantity),
                unit_price=Decimal(price),
            )
        ],
    )


def dated(invoice: SalesInvoice, days_ago: int) -> SalesInvoice:
    """Move an invoice back in time, both the business date and `created_at`.

    `date` is what the period filter reads; `created_at` is what the overdue
    threshold reads. A test that moved only one would be testing a state the
    application never produces.
    """
    moment = timezone.now() - timedelta(days=days_ago)
    SalesInvoice.objects.filter(id=invoice.id).update(date=moment, created_at=moment)
    invoice.refresh_from_db()
    return invoice


# ---------------------------------------------------------------------------
# The period cards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_sums_todays_sales(
    company, rep, customer, stocked_rep_warehouse, product
):
    make_sale(company, rep, customer, product, quantity="10", price="10.00")
    make_sale(company, rep, customer, product, quantity="5", price="10.00")

    response = client_for(rep).get("/api/reps/dashboard/")
    sales = response.json()["data"]["sales"]

    assert response.status_code == 200
    assert sales["invoice_count"] == 2
    assert sales["total_amount"] == "150.00"
    assert len(sales["invoices"]) == 2


@pytest.mark.django_db
def test_a_single_date_covers_that_whole_day(
    company, rep, customer, stocked_rep_warehouse, product
):
    """`date=` must not stop at midnight — an invoice written this afternoon counts."""
    make_sale(company, rep, customer, product)
    today = timezone.localdate().isoformat()

    response = client_for(rep).get(f"/api/reps/dashboard/?date={today}")
    data = response.json()["data"]

    assert data["sales"]["invoice_count"] == 1
    assert data["period"]["date_from"] is not None
    assert data["period"]["date_to"] is not None


@pytest.mark.django_db
def test_a_day_with_no_sales_reports_zero_not_yesterdays_total(
    company, rep, customer, stocked_rep_warehouse, product
):
    dated(make_sale(company, rep, customer, product), days_ago=3)
    today = timezone.localdate().isoformat()

    sales = client_for(rep).get(f"/api/reps/dashboard/?date={today}").json()["data"][
        "sales"
    ]

    assert sales["invoice_count"] == 0
    assert sales["total_amount"] == "0.00"
    assert sales["invoices"] == []


@pytest.mark.django_db
def test_no_date_params_means_all_time(
    company, rep, customer, stocked_rep_warehouse, product
):
    """Clearing the picker shows everything, not a server-chosen default day."""
    dated(make_sale(company, rep, customer, product), days_ago=30)

    data = client_for(rep).get("/api/reps/dashboard/").json()["data"]

    assert data["period"] == {"date_from": None, "date_to": None}
    assert data["sales"]["invoice_count"] == 1


@pytest.mark.django_db
def test_a_bad_date_is_rejected_rather_than_ignored(rep, stocked_rep_warehouse):
    response = client_for(rep).get("/api/reps/dashboard/?date=yesterday")

    assert response.status_code == 400
    assert response.json()["success"] is False


# ---------------------------------------------------------------------------
# Receivables — the card that is deliberately not period-scoped
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_receivables_survive_a_period_filter(
    company, rep, customer, stocked_rep_warehouse, product
):
    """Debt from last month is still owed today, even while viewing today."""
    dated(make_sale(company, rep, customer, product), days_ago=30)
    today = timezone.localdate().isoformat()

    data = client_for(rep).get(f"/api/reps/dashboard/?date={today}").json()["data"]

    assert data["sales"]["invoice_count"] == 0
    assert data["receivables"]["total_balance_due"] == "100.00"
    assert data["receivables"]["invoice_count"] == 1
    # Past the 7-day default threshold, so it is late as well as owed.
    assert data["receivables"]["overdue_invoice_count"] == 1
    assert data["receivables"]["overdue_balance_due"] == "100.00"


@pytest.mark.django_db
def test_a_settled_invoice_leaves_receivables(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
        collected_by_id=rep.id,
    )

    receivables = client_for(rep).get("/api/reps/dashboard/").json()["data"][
        "receivables"
    ]

    assert receivables["invoice_count"] == 0
    assert receivables["total_balance_due"] == "0.00"


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_only_issued_returns_count_toward_the_period_total(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = make_sale(company, rep, customer, product)
    line = invoice.lines.first()

    draft = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(line.id, Decimal("2"))],
        rep_id=rep.id,
    )
    returns = client_for(rep).get("/api/reps/dashboard/").json()["data"]["returns"]

    assert returns["count"] == 0
    assert returns["total_amount"] == "0.00"
    assert returns["draft_count"] == 1

    issue_return_invoice(draft)
    returns = client_for(rep).get("/api/reps/dashboard/").json()["data"]["returns"]

    assert returns["count"] == 1
    assert returns["total_amount"] == "20.00"
    assert returns["draft_count"] == 0


@pytest.mark.django_db
def test_rep_return_list_accepts_the_same_dates_as_the_dashboard(
    company, rep, customer, stocked_rep_warehouse, product
):
    """The period picker drives the paged list too, or the two screens disagree."""
    invoice = make_sale(company, rep, customer, product)
    line = invoice.lines.first()
    issue_return_invoice(
        create_return_invoice(
            company_id=company.id,
            sales_invoice=invoice,
            requested_lines=[(line.id, Decimal("1"))],
            rep_id=rep.id,
        )
    )

    client = client_for(rep)
    today = timezone.localdate().isoformat()

    assert (
        len(
            client.get(
                f"/api/reps/return-invoices/?date_from={today}&date_to={today}"
            ).json()["data"]["return_invoices"]
        )
        == 1
    )
    # A bare date_to must cover its whole day here too, so a same-day return
    # cannot fall between the two screens.
    old = (timezone.localdate() - timedelta(days=5)).isoformat()
    assert (
        client.get(f"/api/reps/return-invoices/?date_to={old}").json()["data"][
            "return_invoices"
        ]
        == []
    )


# ---------------------------------------------------------------------------
# The van
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dashboard_shows_the_van_with_prices(
    company, rep, stocked_rep_warehouse, product, other_product, currency
):
    warehouse = client_for(rep).get("/api/reps/dashboard/").json()["data"]["warehouse"]

    assert warehouse["name"] == "Sami's van"
    assert warehouse["product_count"] == 2
    assert warehouse["total_quantity"] == "200.000"

    by_name = {item["product_name"]: item for item in warehouse["items"]}
    assert by_name["Rice 1kg"]["quantity"] == "100.000"
    assert by_name["Rice 1kg"]["unit_price"] == "10.00"
    assert by_name["Rice 1kg"]["unit_name"] == "Package"
    # The price mapping is an internal detail of the service, not a response field.
    assert "prices" not in warehouse


@pytest.mark.django_db
def test_a_rep_with_no_van_still_gets_a_dashboard(company, rep):
    """A deactivated van is not an error — the rest of the screen must render."""
    data = client_for(rep).get("/api/reps/dashboard/").json()["data"]

    assert data["warehouse"] is None
    assert data["sales"]["invoice_count"] == 0


@pytest.mark.django_db
def test_inventory_endpoint_lists_the_van(
    company, rep, stocked_rep_warehouse, product, other_product, currency
):
    response = client_for(rep).get("/api/reps/inventory/")
    data = response.json()["data"]

    assert response.status_code == 200
    assert data["product_count"] == 2
    assert data["total_quantity"] == "200.000"
    assert data["warehouse"]["name"] == "Sami's van"
    assert {item["product_name"] for item in data["items"]} == {
        "Rice 1kg",
        "Sugar 1kg",
    }


@pytest.mark.django_db
def test_inventory_hides_sold_out_products_unless_asked(
    company, rep, customer, stocked_rep_warehouse, product, other_product
):
    make_sale(company, rep, customer, product, quantity="100", price="10.00")
    client = client_for(rep)

    listed = client.get("/api/reps/inventory/").json()["data"]
    assert [item["product_name"] for item in listed["items"]] == ["Sugar 1kg"]
    assert listed["product_count"] == 1

    with_empties = client.get("/api/reps/inventory/?include_empty=true").json()["data"]
    assert with_empties["product_count"] == 2


@pytest.mark.django_db
def test_inventory_search_matches_product_name(
    company, rep, stocked_rep_warehouse, product, other_product
):
    items = client_for(rep).get("/api/reps/inventory/?search=Rice").json()["data"][
        "items"
    ]

    assert [item["product_name"] for item in items] == ["Rice 1kg"]


@pytest.mark.django_db
def test_a_rep_never_sees_another_reps_van(
    company, rep, other_rep, stocked_rep_warehouse, product
):
    from apps.products.models import Warehouse, WarehouseOwnerType

    Warehouse.objects.create(
        company=company,
        name="Nour's van",
        owner_type=WarehouseOwnerType.REP,
        rep=other_rep,
    )

    data = client_for(other_rep).get("/api/reps/inventory/").json()["data"]

    assert data["warehouse"]["name"] == "Nour's van"
    assert data["items"] == []


@pytest.mark.django_db
def test_a_rep_never_sees_another_reps_sales(
    company, rep, other_rep, customer, stocked_rep_warehouse, product
):
    make_sale(company, rep, customer, product)

    data = client_for(other_rep).get("/api/reps/dashboard/").json()["data"]

    assert data["sales"]["invoice_count"] == 0
    assert data["receivables"]["total_balance_due"] == "0.00"


# ---------------------------------------------------------------------------
# The bell
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_bell_counts_only_this_reps_notifications(company, rep, other_rep):
    notify_rep(company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED)
    notify_rep(company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED)
    notify_rep(
        company_id=company.id, rep_id=other_rep.id, event_key=STOCK_TRANSFER_DISPATCHED
    )
    # Same numeric id, different actor type: the pair must be matched, not the id.
    Notification.objects.create(
        company_id=company.id,
        recipient_actor_type=ActorType.SUBUSER,
        recipient_actor_id=rep.id,
        event_key=STOCK_TRANSFER_DISPATCHED,
    )

    client = client_for(rep)

    assert (
        client.get("/api/reps/dashboard/").json()["data"]["notifications"][
            "unread_count"
        ]
        == 2
    )
    assert (
        client.get("/api/notifications/unread-count/").json()["data"]["unread_count"]
        == 2
    )
    assert len(client.get("/api/notifications/").json()["data"]["notifications"]) == 2


@pytest.mark.django_db
def test_notification_copy_is_lifted_out_of_the_payload(company, rep):
    notify_rep(company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED)

    row = client_for(rep).get("/api/notifications/").json()["data"]["notifications"][0]

    assert row["title"] == "بضاعة بانتظارك في المستودع"
    assert row["body"]
    assert row["is_read"] is False


@pytest.mark.django_db
def test_marking_one_read_clears_only_that_one(company, rep):
    first = notify_rep(
        company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED
    )
    notify_rep(company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED)
    client = client_for(rep)

    response = client.post(f"/api/notifications/{first.id}/read/")

    assert response.status_code == 200
    assert response.json()["data"]["notification"]["is_read"] is True
    assert (
        client.get("/api/notifications/unread-count/").json()["data"]["unread_count"]
        == 1
    )


@pytest.mark.django_db
def test_read_all_empties_the_bell(company, rep):
    for _ in range(3):
        notify_rep(
            company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED
        )
    client = client_for(rep)

    response = client.post("/api/notifications/read-all/")

    assert response.json()["data"]["updated_count"] == 3
    assert (
        client.get("/api/notifications/unread-count/").json()["data"]["unread_count"]
        == 0
    )


@pytest.mark.django_db
def test_a_rep_cannot_mark_another_reps_notification_read(company, rep, other_rep):
    theirs = notify_rep(
        company_id=company.id, rep_id=other_rep.id, event_key=STOCK_TRANSFER_DISPATCHED
    )

    response = client_for(rep).post(f"/api/notifications/{theirs.id}/read/")

    assert response.status_code == 404
    theirs.refresh_from_db()
    assert theirs.read_at is None


@pytest.mark.django_db
def test_marking_read_twice_keeps_the_first_timestamp(company, rep):
    notification = notify_rep(
        company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED
    )
    client = client_for(rep)

    client.post(f"/api/notifications/{notification.id}/read/")
    notification.refresh_from_db()
    first_seen = notification.read_at

    client.post(f"/api/notifications/{notification.id}/read/")
    notification.refresh_from_db()

    assert notification.read_at == first_seen


# ---------------------------------------------------------------------------
# Access
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_home_endpoints_are_rep_only(owner):
    from apps.authentication.utils import generate_tokens_for_subuser

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )

    assert client.get("/api/reps/dashboard/").status_code == 403
    assert client.get("/api/reps/inventory/").status_code == 403


@pytest.mark.django_db
def test_the_home_endpoints_need_a_token(db):
    client = APIClient()

    assert client.get("/api/reps/dashboard/").status_code == 401
    assert client.get("/api/notifications/").status_code == 401


@pytest.mark.django_db
def test_the_inbox_serves_an_admin_too(company, owner, rep):
    """One URL, three audiences — the token says who is asking."""
    from apps.authentication.utils import generate_tokens_for_subuser
    from apps.notifications.services import (
        STOCK_TRANSFER_REQUESTED,
        notify_company_admins,
    )
    from apps.common.modules import STOCK_TRANSFERS

    notify_company_admins(
        company_id=company.id,
        module=STOCK_TRANSFERS,
        event_key=STOCK_TRANSFER_REQUESTED,
    )
    notify_rep(company_id=company.id, rep_id=rep.id, event_key=STOCK_TRANSFER_DISPATCHED)

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    rows = client.get("/api/notifications/").json()["data"]["notifications"]

    assert [row["event_key"] for row in rows] == ["stock_transfer.requested"]
