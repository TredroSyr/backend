"""Sales invoices, payments and balance derivation (spec §3.4, §3.4.1, §3.6)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.invoices.models import (
    PaymentCollection,
    PaymentSource,
    SalesInvoice,
    SalesInvoiceStatus,
)
from apps.invoices.services.documents import LineInput
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.sales import create_sales_invoice
from apps.orders.models import CustomerRequestStatus
from apps.orders.services.requests import create_customer_request
from apps.products.services.stock import InsufficientStockError, available_quantity
from core.domain import DomainError


def line(product, quantity="3", price="10.00"):
    return LineInput(
        product=product, quantity=Decimal(quantity), unit_price=Decimal(price)
    )


@pytest.fixture
def sell(company, rep, customer, stocked_rep_warehouse, product):
    """Create a sale of 3 x 10.00 = 30.00 with configurable extras."""

    def _sell(**kwargs):
        kwargs.setdefault("lines", [line(product)])
        return create_sales_invoice(
            company_id=company.id, rep=rep, customer=customer, **kwargs
        )

    return _sell


@pytest.mark.django_db
def test_a_new_sale_defers_the_whole_balance_and_empties_the_van(
    sell, stocked_rep_warehouse, product
):
    invoice = sell()

    assert invoice.number.startswith("INV-SALE-")
    assert invoice.total_amount == Decimal("30.00")
    assert invoice.paid_amount == Decimal("0.00")
    assert invoice.balance_due == Decimal("30.00")
    assert invoice.status == SalesInvoiceStatus.DEFERRED
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("97.000")


@pytest.mark.django_db
def test_the_rep_warehouse_is_the_default_source(sell, stocked_rep_warehouse):
    assert sell().warehouse_id == stocked_rep_warehouse.id


@pytest.mark.django_db
def test_cash_on_delivery_is_settled_in_the_same_call(sell):
    invoice = sell(payment_amount=Decimal("30.00"))

    assert invoice.status == SalesInvoiceStatus.FULLY_PAID
    assert invoice.balance_due == Decimal("0.00")
    assert PaymentCollection.objects.get().source == PaymentSource.CASH


@pytest.mark.django_db
def test_partial_payments_accumulate_across_visits(company, sell):
    invoice = sell()

    collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=Decimal("10.00")
    )
    _, invoice = collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=Decimal("5.00")
    )

    assert invoice.paid_amount == Decimal("15.00")
    assert invoice.balance_due == Decimal("15.00")
    assert invoice.status == SalesInvoiceStatus.PARTIALLY_PAID
    assert PaymentCollection.objects.count() == 2


@pytest.mark.django_db
def test_the_last_payment_closes_the_invoice(company, sell):
    invoice = sell()
    collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=Decimal("10.00")
    )
    _, invoice = collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=Decimal("20.00")
    )

    assert invoice.balance_due == Decimal("0.00")
    assert invoice.status == SalesInvoiceStatus.FULLY_PAID


@pytest.mark.django_db
def test_paying_more_than_the_balance_is_refused(company, sell):
    """A cash overpayment has no defined resolution path; only a return produces
    an overage, and that one carries a refund_method (§3.5 rule 3).
    """
    invoice = sell()

    with pytest.raises(DomainError):
        collect_payment(
            company_id=company.id, invoice_id=invoice.id, amount=Decimal("30.01")
        )

    invoice.refresh_from_db()
    assert invoice.balance_due == Decimal("30.00")
    assert PaymentCollection.objects.count() == 0


@pytest.mark.django_db
def test_a_sale_the_van_cannot_cover_writes_nothing_at_all(
    company, rep, customer, rep_warehouse, product
):
    """§6.1: the financial record must never exist without its stock movement."""
    with pytest.raises(InsufficientStockError):
        create_sales_invoice(
            company_id=company.id,
            rep=rep,
            customer=customer,
            lines=[line(product, quantity="5")],
        )

    assert SalesInvoice.objects.count() == 0
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_selling_from_another_reps_warehouse_is_refused(
    company, other_rep, customer, stocked_rep_warehouse, product
):
    with pytest.raises(DomainError):
        create_sales_invoice(
            company_id=company.id,
            rep=other_rep,
            customer=customer,
            lines=[line(product)],
            warehouse=stocked_rep_warehouse,
        )


@pytest.mark.django_db
def test_a_delivery_can_resolve_the_requests_it_fulfils(
    company, customer, sell, product
):
    """§3.3: linking is optional, but when the rep links it the request closes."""
    customer_request = create_customer_request(
        company_id=company.id,
        customer_id=customer.id,
        lines=[(product, Decimal("3"))],
    )
    assert customer_request.status == CustomerRequestStatus.PENDING

    invoice = sell(fulfils_request_ids=[customer_request.id])
    customer_request.refresh_from_db()

    assert customer_request.status == CustomerRequestStatus.FULFILLED
    assert customer_request.fulfilled_by_invoice_id == invoice.id


@pytest.mark.django_db
def test_a_sale_needs_no_request_at_all(company, customer, sell):
    """A rep may deliver goods nobody asked for — invoicing is never blocked."""
    invoice = sell()
    assert invoice.fulfilled_requests.count() == 0


@pytest.mark.django_db
def test_the_same_request_cannot_be_fulfilled_twice(company, customer, sell, product):
    customer_request = create_customer_request(
        company_id=company.id,
        customer_id=customer.id,
        lines=[(product, Decimal("3"))],
    )
    sell(fulfils_request_ids=[customer_request.id])

    with pytest.raises(DomainError):
        sell(fulfils_request_ids=[customer_request.id])


@pytest.mark.django_db
def test_unit_price_falls_back_to_the_product_catalog(
    company, rep, customer, stocked_rep_warehouse, product
):
    from apps.products.services.lookup import resolve_unit_price

    assert resolve_unit_price(product, company=company, customer=customer) == Decimal(
        "10.00"
    )


@pytest.mark.django_db
def test_each_document_type_numbers_independently(
    company, company_warehouse, sell, product
):
    """§6.3: one sequence per type, never a shared global counter."""
    from apps.invoices.services.incoming import create_incoming_invoice

    first_sale = sell()
    incoming = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=[line(product)],
    )
    second_sale = sell()

    assert first_sale.number == "INV-SALE-00001"
    assert second_sale.number == "INV-SALE-00002"
    assert incoming.number == "INV-IN-00001"
