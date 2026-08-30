"""Company-direct sales: a customer buying from the company, with no rep.

Extends the spec, which models the sale purely as the rep's field document. The
distinction that matters is where the goods come from and whose cash it is:

* rep sale     -> leaves the rep's van, cash counts toward their settlement
* direct sale  -> leaves a company warehouse, cash is company cash
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_subuser
from apps.invoices.models import (
    PendingCustomerCredit,
    RefundMethod,
    RepCashAdjustment,
    SalesInvoice,
    SalesInvoiceStatus,
)
from apps.invoices.services.documents import LineInput
from apps.invoices.services.reports import rep_cash_reconciliation
from apps.invoices.services.returns import create_return_invoice, issue_return_invoice
from apps.invoices.services.sales import create_sales_invoice
from apps.products.models import StockMovementType
from apps.products.services.stock import (
    StockChange,
    apply_stock_changes,
    available_quantity,
)
from core.domain import DomainError


@pytest.fixture
def stocked_company_warehouse(company, company_warehouse, product):
    apply_stock_changes(
        company_id=company.id,
        warehouse=company_warehouse,
        changes=[StockChange(product_id=product.id, quantity=Decimal("100"))],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    return company_warehouse


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


def direct_sale(company, customer, product, **kwargs):
    kwargs.setdefault(
        "lines",
        [LineInput(product=product, quantity=Decimal("10"), unit_price=Decimal("10.00"))],
    )
    return create_sales_invoice(company_id=company.id, customer=customer, **kwargs)


# ---------------------------------------------------------------------------
# Service layer
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_direct_sale_has_no_rep_and_leaves_the_company_warehouse(
    company, customer, stocked_company_warehouse, product
):
    invoice = direct_sale(company, customer, product)

    assert invoice.rep_id is None
    assert invoice.warehouse_id == stocked_company_warehouse.id
    assert invoice.number.startswith("INV-SALE-")
    assert invoice.total_amount == Decimal("100.00")
    assert invoice.balance_due == Decimal("100.00")
    assert invoice.status == SalesInvoiceStatus.DEFERRED
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("90.000")


@pytest.mark.django_db
def test_a_direct_sale_never_touches_a_rep_warehouse(
    company, customer, stocked_company_warehouse, stocked_rep_warehouse, product
):
    direct_sale(company, customer, product)

    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("100.000")


@pytest.mark.django_db
def test_a_direct_sale_shares_the_numbering_sequence_with_rep_sales(
    company, rep, customer, stocked_company_warehouse, stocked_rep_warehouse, product
):
    """One sequence per document *type*, not per channel (§6.3)."""
    first = direct_sale(company, customer, product)
    second = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(product=product, quantity=Decimal("1"), unit_price=Decimal("10.00"))
        ],
    )

    assert first.number == "INV-SALE-00001"
    assert second.number == "INV-SALE-00002"


@pytest.mark.django_db
def test_cash_from_a_direct_sale_is_company_cash_not_rep_cash(
    company, rep, customer, stocked_company_warehouse, product
):
    invoice = direct_sale(company, customer, product, payment_amount=Decimal("100.00"))

    assert invoice.status == SalesInvoiceStatus.FULLY_PAID
    assert invoice.payments.get().collected_by_id is None

    # Nothing lands in any rep's settlement figure.
    assert rep_cash_reconciliation(company.id)["by_rep"] == []


@pytest.mark.django_db
def test_supplying_a_rep_records_the_sale_on_their_behalf(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = direct_sale(company, customer, product, rep=rep)

    assert invoice.rep_id == rep.id
    assert invoice.warehouse_id == stocked_rep_warehouse.id
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("90.000")


@pytest.mark.django_db
def test_a_direct_sale_is_refused_when_the_company_warehouse_is_short(
    company, customer, company_warehouse, product
):
    with pytest.raises(DomainError):
        direct_sale(company, customer, product)

    assert SalesInvoice.objects.count() == 0


@pytest.mark.django_db
def test_a_direct_sale_cannot_be_pointed_at_a_rep_warehouse(
    company, customer, stocked_rep_warehouse, product
):
    with pytest.raises(DomainError):
        direct_sale(company, customer, product, warehouse=stocked_rep_warehouse)


# ---------------------------------------------------------------------------
# Returns against a direct sale
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_return_against_a_direct_sale_goes_back_to_the_company_warehouse(
    company, customer, stocked_company_warehouse, product
):
    invoice = direct_sale(company, customer, product)

    credit_note = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.get().id, Decimal("4"))],
    )
    issue_return_invoice(credit_note)
    invoice.refresh_from_db()

    assert credit_note.rep_id is None
    assert credit_note.warehouse_id == stocked_company_warehouse.id
    assert invoice.returned_amount == Decimal("40.00")
    assert invoice.balance_due == Decimal("60.00")
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("94.000")


@pytest.mark.django_db
def test_a_cash_refund_on_a_direct_sale_adjusts_no_rep(
    company, customer, stocked_company_warehouse, product
):
    """The money came from the company till, so there is no rep float to correct."""
    invoice = direct_sale(company, customer, product, payment_amount=Decimal("100.00"))

    credit_note = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.get().id, Decimal("3"))],
        refund_method=RefundMethod.CASH_REFUNDED_BY_REP,
    )
    issue_return_invoice(credit_note)
    invoice.refresh_from_db()

    assert credit_note.overage_amount == Decimal("30.00")
    assert invoice.balance_due == Decimal("0.00")
    assert RepCashAdjustment.objects.count() == 0


@pytest.mark.django_db
def test_a_deferred_credit_on_a_direct_sale_still_credits_the_customer(
    company, customer, stocked_company_warehouse, product
):
    invoice = direct_sale(company, customer, product, payment_amount=Decimal("100.00"))

    credit_note = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.get().id, Decimal("3"))],
        refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT,
    )
    issue_return_invoice(credit_note)

    credit = PendingCustomerCredit.objects.get()
    assert credit.customer_id == customer.id
    assert credit.amount == Decimal("30.00")


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_admin_can_create_a_direct_sale_over_the_api(
    admin_client, customer, stocked_company_warehouse, product
):
    response = admin_client.post(
        "/api/companies/sales-invoices/",
        {
            "customer_id": customer.id,
            "lines": [{"product_id": product.id, "quantity": "3", "unit_price": "10.00"}],
            "payment_amount": "30.00",
        },
        format="json",
    )

    assert response.status_code == 201
    invoice = response.data["data"]["invoice"]
    assert invoice["rep"] is None
    assert invoice["total_amount"] == "30.00"
    assert invoice["paid_amount"] == "30.00"
    assert invoice["balance_due"] == "0.00"
    assert invoice["status"] == "fully_paid"
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("97.000")


@pytest.mark.django_db
def test_rep_name_stays_present_as_null_on_a_direct_sale(
    admin_client, customer, stocked_company_warehouse, product
):
    """DRF drops a nested source when the FK is null unless allow_null is set —
    the key must stay in the payload so clients get a stable shape.
    """
    admin_client.post(
        "/api/companies/sales-invoices/",
        {
            "customer_id": customer.id,
            "lines": [{"product_id": product.id, "quantity": "1", "unit_price": "10.00"}],
        },
        format="json",
    )

    listing = admin_client.get("/api/companies/sales-invoices/")
    row = listing.data["data"]["invoices"][0]

    assert "rep" in row and row["rep"] is None
    assert "rep_name" in row and row["rep_name"] is None


@pytest.mark.django_db
def test_admin_can_attribute_a_sale_to_a_rep_over_the_api(
    admin_client, rep, customer, stocked_rep_warehouse, product
):
    response = admin_client.post(
        "/api/companies/sales-invoices/",
        {
            "customer_id": customer.id,
            "rep": rep.id,
            "lines": [{"product_id": product.id, "quantity": "2", "unit_price": "10.00"}],
        },
        format="json",
    )

    assert response.status_code == 201
    assert response.data["data"]["invoice"]["rep"] == rep.id
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("98.000")


@pytest.mark.django_db
def test_a_rep_from_another_company_is_rejected(
    admin_client, customer, stocked_company_warehouse, product, db
):
    from apps.companies.models import Company
    from apps.reps.models import Rep

    other = Company.objects.create(name="Rival", slug="rival", currency="SYP")
    outsider = Rep.objects.create(
        company=other, name="Outsider", phone="+963999999999",
        password="x", referral_code="REP-OUT",
    )

    response = admin_client.post(
        "/api/companies/sales-invoices/",
        {
            "customer_id": customer.id,
            "rep": outsider.id,
            "lines": [{"product_id": product.id, "quantity": "1", "unit_price": "10.00"}],
        },
        format="json",
    )

    assert response.status_code == 400
    assert SalesInvoice.objects.count() == 0


@pytest.mark.django_db
def test_a_rep_cannot_see_company_direct_sales(
    company, rep, customer, stocked_company_warehouse, product
):
    """Rep endpoints filter on rep_id, so a null-rep invoice is not theirs."""
    from apps.authentication.utils import generate_tokens_for_rep

    direct_sale(company, customer, product)

    field = APIClient()
    field.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    response = field.get("/api/reps/sales-invoices/")

    assert response.status_code == 200
    assert response.data["data"]["invoices"] == []
    assert SalesInvoice.objects.count() == 1
