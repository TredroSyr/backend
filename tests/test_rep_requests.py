"""The rep app's orders screen (الطلبات).

A customer request stays a signal, not a sale, and these hold that line: the rep
answering one moves no stock and creates no debt, and the only thing that marks a
request delivered is the Sales Invoice that actually left the van.

The prices on the cards are indicative — resolved from the catalog on read, never
stored — so what is pinned here is that they follow the catalog, honour the
customer's category, and never turn "no price" into zero.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_rep
from apps.customers.models import (
    CustomerCategory,
    CustomerCategoryAssignment,
)
from apps.invoices.services.documents import LineInput
from apps.invoices.services.sales import create_sales_invoice
from apps.notifications.models import ActorType, Notification
from apps.orders.models import CustomerRequest, CustomerRequestStatus
from apps.orders.services.requests import create_customer_request
from apps.products.models import ProductPrice


def client_for(rep) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    return client


def make_request(company, customer, *lines):
    return create_customer_request(
        company_id=company.id, customer_id=customer.id, lines=list(lines)
    )


def rows(client, query=""):
    return client.get(f"/api/reps/customer-requests/{query}").json()["data"]["requests"]


# ---------------------------------------------------------------------------
# The cards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_card_shows_its_lines_priced_and_totalled(
    company, rep, customer, product, other_product, currency
):
    make_request(
        company,
        customer,
        (product, Decimal("3")),      # 10.00 each
        (other_product, Decimal("24")),  # 5.00 each
    )

    card = rows(client_for(rep))[0]

    assert card["status"] == "pending"
    assert card["customer_name"] == "Abu Ahmad Market"
    assert card["line_count"] == 2
    assert card["estimated_total"] == "150.00"

    by_name = {line["product_name"]: line for line in card["lines"]}
    assert by_name["Rice 1kg"]["desired_quantity"] == "3.000"
    assert by_name["Rice 1kg"]["unit_price"] == "10.00"
    assert by_name["Rice 1kg"]["line_total"] == "30.00"
    assert by_name["Sugar 1kg"]["line_total"] == "120.00"


@pytest.mark.django_db
def test_a_price_follows_the_customers_category(
    company, rep, customer, product, currency
):
    """The card quotes what this customer would be charged, override included."""
    wholesale = CustomerCategory.objects.create(company=company, name="جملة")
    CustomerCategoryAssignment.objects.create(
        customer=customer, company=company, category=wholesale
    )
    ProductPrice.objects.create(
        product=product,
        currency=currency,
        customer_category=wholesale,
        price=Decimal("7.00"),
    )
    make_request(company, customer, (product, Decimal("2")))

    card = rows(client_for(rep))[0]

    assert card["lines"][0]["unit_price"] == "7.00"
    assert card["estimated_total"] == "14.00"


@pytest.mark.django_db
def test_an_unpriced_product_is_null_not_zero(company, rep, customer, unit):
    """"Not priced" and "free" are different claims."""
    from apps.products.models import Product

    unpriced = Product.objects.create(company=company, name="No price yet", unit=unit)
    make_request(company, customer, (unpriced, Decimal("5")))

    card = rows(client_for(rep))[0]

    assert card["lines"][0]["unit_price"] is None
    assert card["lines"][0]["line_total"] is None
    assert card["estimated_total"] is None


# ---------------------------------------------------------------------------
# Answering
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_accepting_moves_it_to_accepted_and_tells_the_customer(
    company, rep, customer, product
):
    customer_request = make_request(company, customer, (product, Decimal("1")))
    client = client_for(rep)

    response = client.post(f"/api/reps/customer-requests/{customer_request.id}/accept/")

    assert response.status_code == 200
    assert response.json()["data"]["request"]["status"] == "accepted"
    assert response.json()["data"]["request"]["accepted_at"] is not None

    customer_request.refresh_from_db()
    assert customer_request.status == CustomerRequestStatus.ACCEPTED

    told = Notification.objects.filter(
        recipient_actor_type=ActorType.CUSTOMER,
        recipient_actor_id=customer.id,
        event_key="customer_request.accepted",
    )
    assert told.count() == 1
    assert told.first().payload["title"] == "وافق المندوب على طلبك"


@pytest.mark.django_db
def test_rejecting_records_the_reason(company, rep, customer, product):
    customer_request = make_request(company, customer, (product, Decimal("1")))

    response = client_for(rep).post(
        f"/api/reps/customer-requests/{customer_request.id}/reject/",
        {"reason": "المنتج غير متوفر حالياً"},
        format="json",
    )
    body = response.json()["data"]["request"]

    assert response.status_code == 200
    assert body["status"] == "rejected"
    assert body["rejection_reason"] == "المنتج غير متوفر حالياً"
    assert body["rejected_at"] is not None
    assert Notification.objects.filter(
        recipient_actor_type=ActorType.CUSTOMER,
        event_key="customer_request.rejected",
    ).exists()


@pytest.mark.django_db
def test_rejecting_without_a_reason_is_allowed(company, rep, customer, product):
    customer_request = make_request(company, customer, (product, Decimal("1")))

    response = client_for(rep).post(
        f"/api/reps/customer-requests/{customer_request.id}/reject/"
    )

    assert response.status_code == 200
    assert response.json()["data"]["request"]["rejection_reason"] == ""


@pytest.mark.django_db
def test_a_request_can_only_be_answered_once(company, rep, customer, product):
    customer_request = make_request(company, customer, (product, Decimal("1")))
    client = client_for(rep)
    client.post(f"/api/reps/customer-requests/{customer_request.id}/accept/")

    again = client.post(f"/api/reps/customer-requests/{customer_request.id}/accept/")
    flipped = client.post(f"/api/reps/customer-requests/{customer_request.id}/reject/")

    assert again.status_code == 400
    assert flipped.status_code == 400
    customer_request.refresh_from_db()
    assert customer_request.status == CustomerRequestStatus.ACCEPTED


@pytest.mark.django_db
def test_a_rep_cannot_answer_another_reps_request(
    company, rep, other_rep, customer, product
):
    customer_request = make_request(company, customer, (product, Decimal("1")))

    response = client_for(other_rep).post(
        f"/api/reps/customer-requests/{customer_request.id}/accept/"
    )

    assert response.status_code == 404
    customer_request.refresh_from_db()
    assert customer_request.status == CustomerRequestStatus.PENDING


# ---------------------------------------------------------------------------
# Delivery — the invoice, not a status flip
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_accepted_request_is_still_deliverable(
    company, rep, customer, stocked_rep_warehouse, product
):
    """The regression that matters: accepting must not close a request.

    `fulfil_requests` used to admit only `pending`, so a rep who tapped قبول
    would have been unable to deliver against their own promise.
    """
    customer_request = make_request(company, customer, (product, Decimal("2")))
    client_for(rep).post(f"/api/reps/customer-requests/{customer_request.id}/accept/")

    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product, quantity=Decimal("2"), unit_price=Decimal("10.00")
            )
        ],
        fulfils_request_ids=[customer_request.id],
    )

    customer_request.refresh_from_db()
    assert customer_request.status == CustomerRequestStatus.FULFILLED
    assert customer_request.fulfilled_by_invoice_id == invoice.id
    assert customer_request.fulfilled_at is not None


@pytest.mark.django_db
def test_a_rejected_request_cannot_be_delivered_against(
    company, rep, customer, stocked_rep_warehouse, product
):
    from core.domain import DomainError

    customer_request = make_request(company, customer, (product, Decimal("2")))
    client_for(rep).post(f"/api/reps/customer-requests/{customer_request.id}/reject/")

    with pytest.raises(DomainError):
        create_sales_invoice(
            company_id=company.id,
            rep=rep,
            customer=customer,
            lines=[
                LineInput(
                    product=product, quantity=Decimal("2"), unit_price=Decimal("10.00")
                )
            ],
            fulfils_request_ids=[customer_request.id],
        )


@pytest.mark.django_db
def test_answering_moves_no_stock(
    company, rep, customer, stocked_rep_warehouse, product
):
    """Accepting is a promise to visit; the van is untouched until the sale."""
    from apps.products.services.stock import available_quantity

    before = available_quantity(stocked_rep_warehouse.id, product.id)
    customer_request = make_request(company, customer, (product, Decimal("5")))
    client_for(rep).post(f"/api/reps/customer-requests/{customer_request.id}/accept/")

    assert available_quantity(stocked_rep_warehouse.id, product.id) == before


# ---------------------------------------------------------------------------
# The filter tabs
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_status_filter_drives_the_tabs(
    company, rep, customer, stocked_rep_warehouse, product
):
    pending = make_request(company, customer, (product, Decimal("1")))
    accepted = make_request(company, customer, (product, Decimal("1")))
    rejected = make_request(company, customer, (product, Decimal("1")))
    client = client_for(rep)

    client.post(f"/api/reps/customer-requests/{accepted.id}/accept/")
    client.post(f"/api/reps/customer-requests/{rejected.id}/reject/")

    delivered = make_request(company, customer, (product, Decimal("1")))
    create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product, quantity=Decimal("1"), unit_price=Decimal("10.00")
            )
        ],
        fulfils_request_ids=[delivered.id],
    )

    def ids(query):
        return {row["id"] for row in rows(client, query)}

    assert ids("") == {pending.id, accepted.id, rejected.id, delivered.id}
    assert ids("?status=pending") == {pending.id}
    assert ids("?status=accepted") == {accepted.id}
    assert ids("?status=rejected") == {rejected.id}
    assert ids("?status=fulfilled") == {delivered.id}


@pytest.mark.django_db
def test_the_orders_list_is_scoped_to_the_asking_rep(
    company, rep, other_rep, customer, product
):
    make_request(company, customer, (product, Decimal("1")))

    assert rows(client_for(other_rep)) == []
    assert len(rows(client_for(rep))) == 1


@pytest.mark.django_db
def test_the_orders_list_takes_the_same_dates_as_every_other_screen(
    company, rep, customer, product
):
    from datetime import timedelta

    from django.utils import timezone

    customer_request = make_request(company, customer, (product, Decimal("1")))
    client = client_for(rep)
    today = timezone.localdate().isoformat()
    old = (timezone.localdate() - timedelta(days=5)).isoformat()

    assert len(rows(client, f"?date={today}")) == 1
    assert rows(client, f"?date={old}") == []
    # A bare date_to must cover its whole day, as it does everywhere else.
    assert len(rows(client, f"?date_from={today}&date_to={today}")) == 1


@pytest.mark.django_db
def test_the_orders_screen_is_rep_only(owner):
    from apps.authentication.utils import generate_tokens_for_subuser

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )

    assert client.get("/api/reps/customer-requests/").status_code == 403
