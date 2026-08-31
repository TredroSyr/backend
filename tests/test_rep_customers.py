"""The rep app's stores list and store page.

Both screens print the same three figures — invoiced, paid, still due — so what
these pin down is whose invoices those figures count. A store's debt belongs to
the rep who sold to it; a rep must never be shown a balance they cannot collect,
nor a store they were not assigned.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_rep
from apps.customers.models import Customer
from apps.invoices.services.documents import LineInput
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.sales import create_sales_invoice
from apps.reps.models import RepCustomerAssignment


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


def only_customer(payload) -> dict:
    customers = payload["data"]["customers"]
    assert len(customers) == 1
    return customers[0]


# ---------------------------------------------------------------------------
# The stores list
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_store_row_carries_address_days_and_balance(
    company, rep, customer, stocked_rep_warehouse, product
):
    customer.address = "شارع النيل، الفرقان، حلب"
    customer.save(update_fields=["address"])
    RepCustomerAssignment.objects.filter(rep=rep, customer=customer).update(
        work_days=["saturday"]
    )

    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("40.00"),
        collected_by_id=rep.id,
    )

    response = client_for(rep).get("/api/reps/customers/")
    row = only_customer(response.json())

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 1
    assert row["name"] == "Abu Ahmad Market"
    assert row["address"] == "شارع النيل، الفرقان، حلب"
    assert row["work_days"] == ["saturday"]
    assert row["total_invoiced"] == "100.00"
    assert row["paid_amount"] == "40.00"
    assert row["balance_due"] == "60.00"
    assert row["invoice_count"] == 1


@pytest.mark.django_db
def test_a_store_with_no_invoices_reports_zero_not_null(company, rep, customer):
    """The '0 ل.س' card — a new store is at zero, not unknown."""
    row = only_customer(client_for(rep).get("/api/reps/customers/").json())

    assert row["total_invoiced"] == "0.00"
    assert row["paid_amount"] == "0.00"
    assert row["balance_due"] == "0.00"
    assert row["invoice_count"] == 0


@pytest.mark.django_db
def test_a_balance_counts_only_the_asking_reps_sales(
    company, rep, other_rep, customer, stocked_rep_warehouse, product
):
    """Another rep's sale to the same store is not this rep's to collect."""
    from apps.products.models import Warehouse, WarehouseOwnerType
    from apps.products.services.stock import StockChange, apply_stock_changes
    from apps.products.models import StockMovementType

    other_van = Warehouse.objects.create(
        company=company,
        name="Nour's van",
        owner_type=WarehouseOwnerType.REP,
        rep=other_rep,
    )
    apply_stock_changes(
        company_id=company.id,
        warehouse=other_van,
        changes=[StockChange(product_id=product.id, quantity=Decimal("50"))],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    RepCustomerAssignment.objects.create(rep=other_rep, customer=customer)

    make_sale(company, rep, customer, product, quantity="10")
    make_sale(company, other_rep, customer, product, quantity="5")

    mine = only_customer(client_for(rep).get("/api/reps/customers/").json())
    theirs = only_customer(client_for(other_rep).get("/api/reps/customers/").json())

    assert mine["total_invoiced"] == "100.00"
    assert theirs["total_invoiced"] == "50.00"


@pytest.mark.django_db
def test_a_rep_only_sees_stores_assigned_to_them(company, rep, other_rep, customer):
    assert client_for(other_rep).get("/api/reps/customers/").json()["data"]["total"] == 0


@pytest.mark.django_db
def test_work_day_filter_selects_todays_route(company, rep, customer):
    saturday_store = Customer.objects.create(
        name="Saturday shop", phone="+963955000001"
    )
    RepCustomerAssignment.objects.create(
        rep=rep, customer=saturday_store, work_days=["saturday"]
    )
    RepCustomerAssignment.objects.filter(rep=rep, customer=customer).update(
        work_days=["sunday"]
    )

    client = client_for(rep)

    assert [
        row["name"]
        for row in client.get("/api/reps/customers/?work_day=saturday").json()["data"][
            "customers"
        ]
    ] == ["Saturday shop"]
    assert client.get("/api/reps/customers/?work_day=monday").json()["data"]["total"] == 0


@pytest.mark.django_db
def test_work_day_filter_honours_the_reps_default_days(company, rep, customer):
    """An assignment naming no days inherits the rep's, on the badge and the filter."""
    rep.work_days = ["tuesday"]
    rep.save(update_fields=["work_days"])
    # The fixture's assignment leaves work_days empty.

    client = client_for(rep)
    row = only_customer(client.get("/api/reps/customers/").json())

    assert row["work_days"] == ["tuesday"]
    assert client.get("/api/reps/customers/?work_day=tuesday").json()["data"]["total"] == 1
    assert client.get("/api/reps/customers/?work_day=friday").json()["data"]["total"] == 0


@pytest.mark.django_db
def test_search_matches_the_address_too(company, rep, customer):
    customer.address = "الجميلية، مقابل الحديقة العامة"
    customer.save(update_fields=["address"])

    client = client_for(rep)

    assert client.get("/api/reps/customers/?search=الجميلية").json()["data"]["total"] == 1
    assert client.get("/api/reps/customers/?search=حلب").json()["data"]["total"] == 0


# ---------------------------------------------------------------------------
# The store page
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_store_page_totals_match_the_list_row(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("40.00"),
        collected_by_id=rep.id,
    )

    client = client_for(rep)
    detail = client.get(f"/api/reps/customers/{customer.id}/").json()["data"]["customer"]
    row = only_customer(client.get("/api/reps/customers/").json())

    assert detail["phone"] == "+963955555555"
    assert detail["total_invoiced"] == row["total_invoiced"] == "100.00"
    assert detail["paid_amount"] == row["paid_amount"] == "40.00"
    assert detail["balance_due"] == row["balance_due"] == "60.00"


@pytest.mark.django_db
def test_a_rep_cannot_open_a_store_that_is_not_theirs(company, rep, other_rep, customer):
    assert (
        client_for(other_rep).get(f"/api/reps/customers/{customer.id}/").status_code
        == 404
    )


@pytest.mark.django_db
def test_the_store_page_tabs_are_scoped_to_that_store(
    company, rep, customer, stocked_rep_warehouse, product, other_product
):
    """السجل / الدفعات / المرتجعات all hang off `?customer=`."""
    from apps.invoices.services.returns import (
        create_return_invoice,
        issue_return_invoice,
    )
    from apps.orders.services.requests import create_customer_request

    other_store = Customer.objects.create(name="Elsewhere", phone="+963955000002")
    RepCustomerAssignment.objects.create(rep=rep, customer=other_store)

    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("10.00"),
        collected_by_id=rep.id,
    )
    issue_return_invoice(
        create_return_invoice(
            company_id=company.id,
            sales_invoice=invoice,
            requested_lines=[(invoice.lines.first().id, Decimal("1"))],
            rep_id=rep.id,
        )
    )
    create_customer_request(
        company_id=company.id,
        customer_id=customer.id,
        lines=[(other_product, Decimal("24"))],
    )
    make_sale(company, rep, other_store, product)

    client = client_for(rep)
    scoped = f"?customer={customer.id}"

    assert len(client.get(f"/api/reps/sales-invoices/{scoped}").json()["data"]["invoices"]) == 1
    assert len(client.get(f"/api/reps/payments/{scoped}").json()["data"]["payments"]) == 1
    assert (
        len(client.get(f"/api/reps/return-invoices/{scoped}").json()["data"]["return_invoices"])
        == 1
    )
    requests = client.get(f"/api/reps/customer-requests/{scoped}").json()["data"]["requests"]
    assert len(requests) == 1
    # "الطلبات السابقة" prints product × quantity, so the rows must carry lines.
    assert [
        (line["product_name"], line["desired_quantity"])
        for line in requests[0]["lines"]
    ] == [("Sugar 1kg", "24.000")]


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_rep_can_correct_a_store_address(company, rep, customer):
    response = client_for(rep).patch(
        f"/api/reps/customers/{customer.id}/",
        {"address": "السليمانية، شارع الحمام"},
        format="json",
    )

    assert response.status_code == 200
    assert "العنوان" in response.json()["message"]
    customer.refresh_from_db()
    assert customer.address == "السليمانية، شارع الحمام"


@pytest.mark.django_db
def test_a_rep_can_create_a_store_with_an_address(company, rep):
    response = client_for(rep).post(
        "/api/reps/customers/",
        {
            "name": "بقالية الهلك",
            "phone": "+963944111222",
            "address": "الهلك، الشارع الرئيسي",
            "work_days": ["tuesday"],
        },
        format="json",
    )
    created = response.json()["data"]["customer"]

    assert response.status_code == 201
    assert created["address"] == "الهلك، الشارع الرئيسي"
    assert created["work_days"] == ["tuesday"]
    assert created["balance_due"] == "0.00"


@pytest.mark.django_db
def test_the_stores_list_is_rep_only(owner):
    from apps.authentication.utils import generate_tokens_for_subuser

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )

    assert client.get("/api/reps/customers/").status_code == 403
