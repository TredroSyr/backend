"""`customer` and `rep` filtering across the invoice list endpoints.

Two parallel worlds are built once: rep Sami selling to Abu Ahmad, and rep Nour
selling to Abu Khalil. Every assertion then says "asking for one must not return
the other" — the cheap mistake a filter typo makes is returning everything, and a
single-row fixture would not catch it.

Returns, payments and credits carry no customer or rep column of their own; they
inherit through the document that created them, so those filters exercise a join.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import (
    generate_tokens_for_rep,
    generate_tokens_for_subuser,
)
from apps.customers.models import Customer
from apps.invoices.models import RefundMethod
from apps.invoices.services.documents import LineInput
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.returns import create_return_invoice, issue_return_invoice
from apps.invoices.services.sales import create_sales_invoice
from apps.products.models import StockMovementType, Warehouse, WarehouseOwnerType
from apps.products.services.stock import StockChange, apply_stock_changes
from apps.reps.models import RepCustomerAssignment


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


@pytest.fixture
def rep_client(rep) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    return client


@pytest.fixture
def other_customer(db, other_rep) -> Customer:
    customer = Customer.objects.create(name="Abu Khalil Market", phone="+963966666666")
    RepCustomerAssignment.objects.create(rep=other_rep, customer=customer)
    return customer


@pytest.fixture
def stocked_other_rep_warehouse(company, other_rep, product) -> Warehouse:
    warehouse = Warehouse.objects.create(
        company=company,
        name="Nour van",
        owner_type=WarehouseOwnerType.REP,
        rep=other_rep,
    )
    apply_stock_changes(
        company_id=company.id,
        warehouse=warehouse,
        changes=[StockChange(product_id=product.id, quantity=Decimal("100"))],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    return warehouse


def _sell_pay_and_credit(company, rep, customer, product):
    """One full cycle: sell 10, collect the 100, then take it all back.

    Paying in full before returning everything leaves an overage, and settling
    that as `deferred_customer_credit` is the only path that mints a
    PendingCustomerCredit — so this one helper seeds all four list endpoints.
    """
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product, quantity=Decimal("10"), unit_price=Decimal("10.00")
            )
        ],
    )
    payment, invoice = collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=Decimal("100.00")
    )
    line = invoice.lines.first()
    return_invoice = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(line.id, Decimal("10"))],
        refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT,
    )
    return_invoice = issue_return_invoice(return_invoice)

    return invoice, payment, return_invoice


@pytest.fixture
def two_worlds(
    company,
    rep,
    other_rep,
    customer,
    other_customer,
    product,
    stocked_rep_warehouse,
    stocked_other_rep_warehouse,
):
    """(mine, theirs) — one complete document set per rep/customer pair."""
    return (
        _sell_pay_and_credit(company, rep, customer, product),
        _sell_pay_and_credit(company, other_rep, other_customer, product),
    )


def rows(response, key):
    assert response.status_code == 200, response.data
    return response.data["data"][key]


# ---------------------------------------------------------------------------
# Sales invoices
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_sales_invoices_filter_by_customer(admin_client, two_worlds, customer):
    (mine, _, _), _ = two_worlds

    result = rows(
        admin_client.get("/api/companies/sales-invoices/", {"customer": customer.id}),
        "invoices",
    )

    assert [row["id"] for row in result] == [mine.id]


@pytest.mark.django_db
def test_admin_sales_invoices_filter_by_rep(admin_client, two_worlds, other_rep):
    _, (theirs, _, _) = two_worlds

    result = rows(
        admin_client.get("/api/companies/sales-invoices/", {"rep": other_rep.id}),
        "invoices",
    )

    assert [row["id"] for row in result] == [theirs.id]


@pytest.mark.django_db
def test_rep_sales_invoices_filter_by_customer(rep_client, two_worlds, customer):
    (mine, _, _), _ = two_worlds

    result = rows(
        rep_client.get("/api/reps/sales-invoices/", {"customer": customer.id}),
        "invoices",
    )

    assert [row["id"] for row in result] == [mine.id]


@pytest.mark.django_db
def test_rep_sales_invoices_stay_scoped_to_the_caller(
    rep_client, two_worlds, other_customer
):
    """The rep list is scoped before filtering: another rep's customer yields
    nothing rather than leaking that rep's sale.
    """
    result = rows(
        rep_client.get("/api/reps/sales-invoices/", {"customer": other_customer.id}),
        "invoices",
    )

    assert result == []


# ---------------------------------------------------------------------------
# Return invoices
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_return_invoices_filter_by_customer(admin_client, two_worlds, customer):
    (_, _, mine), _ = two_worlds

    result = rows(
        admin_client.get("/api/companies/return-invoices/", {"customer": customer.id}),
        "return_invoices",
    )

    assert [row["id"] for row in result] == [mine.id]


@pytest.mark.django_db
def test_admin_return_invoices_filter_by_rep(admin_client, two_worlds, other_rep):
    _, (_, _, theirs) = two_worlds

    result = rows(
        admin_client.get("/api/companies/return-invoices/", {"rep": other_rep.id}),
        "return_invoices",
    )

    assert [row["id"] for row in result] == [theirs.id]


@pytest.mark.django_db
def test_rep_return_invoices_filter_by_customer(
    rep_client, two_worlds, customer, other_customer
):
    (_, _, mine), _ = two_worlds

    assert [
        row["id"]
        for row in rows(
            rep_client.get("/api/reps/return-invoices/", {"customer": customer.id}),
            "return_invoices",
        )
    ] == [mine.id]
    assert (
        rows(
            rep_client.get(
                "/api/reps/return-invoices/", {"customer": other_customer.id}
            ),
            "return_invoices",
        )
        == []
    )


# ---------------------------------------------------------------------------
# Payment collections
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_payments_filter_by_customer(admin_client, two_worlds, customer):
    (_, mine, _), _ = two_worlds

    response = admin_client.get(
        "/api/companies/payment-collections/", {"customer": customer.id}
    )
    result = rows(response, "payments")

    assert [row["id"] for row in result] == [mine.id]
    assert response.data["data"]["total_amount"] == "100.00"


@pytest.mark.django_db
def test_admin_payments_filter_by_rep_means_who_collected(
    admin_client, two_worlds, rep, other_rep
):
    """These were booked against the invoice with no rep on the collection, so
    both reps come back empty — `rep` here is the collector, not the seller.
    """
    for who in (rep, other_rep):
        assert (
            rows(
                admin_client.get("/api/companies/payment-collections/", {"rep": who.id}),
                "payments",
            )
            == []
        )


@pytest.mark.django_db
def test_rep_payments_filter_by_customer_respects_the_rep_scope(
    rep_client, two_worlds, customer
):
    """The rep list only shows what they collected — none here, so the customer
    filter narrows an already-empty set rather than widening it.
    """
    assert (
        rows(rep_client.get("/api/reps/payments/", {"customer": customer.id}), "payments")
        == []
    )


@pytest.mark.django_db
def test_rep_collected_payment_is_filterable_by_customer(
    rep_client, company, rep, customer, product, stocked_rep_warehouse
):
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(product=product, quantity=Decimal("5"), unit_price=Decimal("10.00"))
        ],
    )
    payment, _ = collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("50.00"),
        collected_by_id=rep.id,
    )

    result = rows(
        rep_client.get("/api/reps/payments/", {"customer": customer.id}), "payments"
    )

    assert [row["id"] for row in result] == [payment.id]


# ---------------------------------------------------------------------------
# Customer credits
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_credits_filter_by_customer(admin_client, two_worlds, customer):
    result = rows(
        admin_client.get("/api/companies/customer-credits/", {"customer": customer.id}),
        "credits",
    )

    assert [row["customer"] for row in result] == [customer.id]


@pytest.mark.django_db
def test_admin_credits_filter_by_rep(
    admin_client, two_worlds, other_rep, other_customer
):
    """A credit has no rep column — it inherits the one on the return that raised
    it, so this filter has to reach through `source_return_invoice`.
    """
    result = rows(
        admin_client.get("/api/companies/customer-credits/", {"rep": other_rep.id}),
        "credits",
    )

    assert [row["customer"] for row in result] == [other_customer.id]


@pytest.mark.django_db
def test_rep_credits_filter_by_customer(rep_client, two_worlds, other_customer):
    """The rep credit list is company-wide on purpose: a rep must be able to check
    any customer's balance before invoicing them (§3.7 rule 1).
    """
    result = rows(
        rep_client.get("/api/reps/customer-credits/", {"customer": other_customer.id}),
        "credits",
    )

    assert [row["customer"] for row in result] == [other_customer.id]
