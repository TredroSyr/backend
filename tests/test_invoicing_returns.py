"""Return invoices, overages and customer credits (spec §3.5, §3.7, flow §4.4)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.invoices.models import (
    CustomerCreditStatus,
    PaymentSource,
    PendingCustomerCredit,
    RefundMethod,
    RepCashAdjustment,
    ReturnInvoiceStatus,
    SalesInvoiceStatus,
)
from apps.invoices.services.credits import apply_credits, lock_credits, pending_credits_for
from apps.invoices.services.documents import LineInput
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.returns import (
    create_return_invoice,
    issue_return_invoice,
    projected_overage,
)
from apps.invoices.services.sales import create_sales_invoice
from apps.products.services.stock import available_quantity
from core.domain import DomainError, InvalidTransition


@pytest.fixture
def sale(company, rep, customer, stocked_rep_warehouse, product):
    """A 10 x 10.00 = 100.00 sale, unpaid."""
    return create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product, quantity=Decimal("10"), unit_price=Decimal("10.00")
            )
        ],
    )


def return_of(company, sale, quantity, **kwargs):
    return create_return_invoice(
        company_id=company.id,
        sales_invoice=sale,
        requested_lines=[(sale.lines.get().id, Decimal(quantity))],
        **kwargs,
    )


@pytest.mark.django_db
def test_a_return_copies_the_price_from_the_original_line(company, sale):
    credit_note = return_of(company, sale, "2")

    assert credit_note.number.startswith("INV-RET-")
    assert credit_note.status == ReturnInvoiceStatus.DRAFT
    assert credit_note.amount == Decimal("20.00")
    assert credit_note.lines.get().unit_price == Decimal("10.00")
    assert credit_note.lines.get().sales_invoice_line_id == sale.lines.get().id


@pytest.mark.django_db
def test_a_draft_return_has_not_happened_yet(company, sale, stocked_rep_warehouse, product):
    return_of(company, sale, "2")
    sale.refresh_from_db()

    assert sale.returned_amount == Decimal("0.00")
    assert sale.balance_due == Decimal("100.00")
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("90.000")


@pytest.mark.django_db
def test_issuing_a_return_restocks_and_recomputes_the_sale(
    company, sale, stocked_rep_warehouse, product
):
    credit_note = return_of(company, sale, "2")
    issue_return_invoice(credit_note)
    sale.refresh_from_db()

    assert credit_note.status == ReturnInvoiceStatus.ISSUED
    assert sale.returned_amount == Decimal("20.00")
    assert sale.balance_due == Decimal("80.00")
    assert sale.status == SalesInvoiceStatus.PARTIALLY_PAID
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("92.000")


@pytest.mark.django_db
def test_returns_can_be_routed_to_a_company_warehouse(
    company, sale, company_warehouse, stocked_rep_warehouse, product
):
    """Defective goods pulled out of circulation — a field, not a hardcoded rule."""
    credit_note = return_of(company, sale, "2", warehouse=company_warehouse)
    issue_return_invoice(credit_note)

    assert available_quantity(company_warehouse.id, product.id) == Decimal("2.000")
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("90.000")


@pytest.mark.django_db
def test_returns_accumulate_across_visits(company, sale):
    """§3.5 rule 4: always recompute from the full set, never assume one-to-one."""
    issue_return_invoice(return_of(company, sale, "2"))
    issue_return_invoice(return_of(company, sale, "3"))
    sale.refresh_from_db()

    assert sale.returns.count() == 2
    assert sale.returned_amount == Decimal("50.00")
    assert sale.balance_due == Decimal("50.00")


@pytest.mark.django_db
def test_a_customer_cannot_return_more_than_they_bought(company, sale):
    issue_return_invoice(return_of(company, sale, "8"))

    with pytest.raises(DomainError):
        return_of(company, sale, "3")


@pytest.mark.django_db
def test_a_return_cannot_be_issued_twice(company, sale, stocked_rep_warehouse, product):
    credit_note = return_of(company, sale, "2")
    issue_return_invoice(credit_note)

    with pytest.raises(InvalidTransition):
        issue_return_invoice(credit_note)

    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("92.000")


# ---------------------------------------------------------------------------
# Overage — §3.5 rule 3, both resolution paths
# ---------------------------------------------------------------------------


@pytest.fixture
def paid_sale(company, sale):
    """The same sale, paid in full — the setup for an over-return."""
    _, invoice = collect_payment(
        company_id=company.id, invoice_id=sale.id, amount=Decimal("100.00")
    )
    return invoice


@pytest.mark.django_db
def test_an_overage_requires_a_refund_method_before_issuing(company, paid_sale):
    credit_note = return_of(company, paid_sale, "3")
    assert projected_overage(credit_note) == Decimal("30.00")

    with pytest.raises(DomainError):
        issue_return_invoice(credit_note)

    credit_note.refresh_from_db()
    assert credit_note.status == ReturnInvoiceStatus.DRAFT


@pytest.mark.django_db
def test_a_return_within_the_balance_needs_no_refund_method(company, sale):
    credit_note = return_of(company, sale, "3")
    assert projected_overage(credit_note) == Decimal("0.00")

    issue_return_invoice(credit_note)
    assert credit_note.status == ReturnInvoiceStatus.ISSUED


@pytest.mark.django_db
def test_cash_refund_closes_the_sale_and_reduces_the_reps_expected_cash(
    company, rep, paid_sale
):
    credit_note = return_of(
        company,
        paid_sale,
        "3",
        refund_method=RefundMethod.CASH_REFUNDED_BY_REP,
    )
    issue_return_invoice(credit_note)
    paid_sale.refresh_from_db()

    # The balance floors at zero and never goes negative.
    assert paid_sale.balance_due == Decimal("0.00")
    assert paid_sale.status == SalesInvoiceStatus.FULLY_PAID
    assert credit_note.overage_amount == Decimal("30.00")

    adjustment = RepCashAdjustment.objects.get()
    assert adjustment.rep_id == rep.id
    assert adjustment.amount == Decimal("-30.00")
    assert PendingCustomerCredit.objects.count() == 0


@pytest.mark.django_db
def test_deferred_credit_moves_the_amount_onto_a_credit_record(
    company, customer, paid_sale
):
    credit_note = return_of(
        company,
        paid_sale,
        "3",
        refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT,
    )
    issue_return_invoice(credit_note)
    paid_sale.refresh_from_db()

    assert paid_sale.balance_due == Decimal("0.00")
    assert RepCashAdjustment.objects.count() == 0

    credit = PendingCustomerCredit.objects.get()
    assert credit.customer_id == customer.id
    assert credit.amount == Decimal("30.00")
    assert credit.status == CustomerCreditStatus.PENDING
    assert credit.source_return_invoice_id == credit_note.id


@pytest.mark.django_db
def test_a_second_over_return_only_refunds_its_own_increment(company, paid_sale):
    """The cumulative formula would re-refund what the first return already paid back."""
    first = return_of(
        company, paid_sale, "3", refund_method=RefundMethod.CASH_REFUNDED_BY_REP
    )
    issue_return_invoice(first)

    second = return_of(
        company, paid_sale, "2", refund_method=RefundMethod.CASH_REFUNDED_BY_REP
    )
    issue_return_invoice(second)

    assert first.overage_amount == Decimal("30.00")
    assert second.overage_amount == Decimal("20.00")
    assert sum(a.amount for a in RepCashAdjustment.objects.all()) == Decimal("-50.00")


@pytest.mark.django_db
def test_a_return_straddling_the_balance_only_overages_the_excess(company, sale):
    """Half paid, then everything returned: only the paid part can be refunded."""
    collect_payment(company_id=company.id, invoice_id=sale.id, amount=Decimal("40.00"))

    credit_note = return_of(
        company, sale, "10", refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT
    )
    issue_return_invoice(credit_note)
    sale.refresh_from_db()

    assert credit_note.amount == Decimal("100.00")
    assert credit_note.overage_amount == Decimal("40.00")
    assert sale.balance_due == Decimal("0.00")
    assert PendingCustomerCredit.objects.get().amount == Decimal("40.00")


# ---------------------------------------------------------------------------
# Applying credits — §3.7
# ---------------------------------------------------------------------------


@pytest.fixture
def pending_credit(company, paid_sale):
    credit_note = return_of(
        company, paid_sale, "3", refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT
    )
    issue_return_invoice(credit_note)
    return PendingCustomerCredit.objects.get()


@pytest.mark.django_db
def test_pending_credits_are_surfaced_for_the_customer(company, customer, pending_credit):
    assert list(pending_credits_for(company.id, customer.id)) == [pending_credit]


@pytest.mark.django_db
def test_applying_a_credit_records_a_traceable_payment(
    company, rep, customer, stocked_rep_warehouse, product, pending_credit
):
    """§3.7 rule 2: treated as a payment sourced from the credit, not a discount,
    so `paid_amount` stays accurate and every unit of value has a source.
    """
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product, quantity=Decimal("5"), unit_price=Decimal("10.00")
            )
        ],
        credit_ids=[pending_credit.id],
    )
    pending_credit.refresh_from_db()

    assert invoice.total_amount == Decimal("50.00")
    assert invoice.paid_amount == Decimal("30.00")
    assert invoice.balance_due == Decimal("20.00")
    assert invoice.status == SalesInvoiceStatus.PARTIALLY_PAID

    payment = invoice.payments.get()
    assert payment.source == PaymentSource.CUSTOMER_CREDIT
    assert payment.applied_credit_id == pending_credit.id

    assert pending_credit.status == CustomerCreditStatus.APPLIED
    assert pending_credit.applied_to_invoice_id == invoice.id
    assert pending_credit.applied_at is not None


@pytest.mark.django_db
def test_a_credit_cannot_be_spent_twice(
    company, rep, customer, stocked_rep_warehouse, product, pending_credit
):
    create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(product=product, quantity=Decimal("5"), unit_price=Decimal("10.00"))
        ],
        credit_ids=[pending_credit.id],
    )

    with pytest.raises(DomainError):
        create_sales_invoice(
            company_id=company.id,
            rep=rep,
            customer=customer,
            lines=[
                LineInput(
                    product=product, quantity=Decimal("5"), unit_price=Decimal("10.00")
                )
            ],
            credit_ids=[pending_credit.id],
        )


@pytest.mark.django_db
def test_credits_exceeding_the_new_invoice_total_are_refused(
    company, rep, customer, stocked_rep_warehouse, product, pending_credit
):
    """§3.7 rule 4: several credits may be applied, but not beyond the total."""
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(product=product, quantity=Decimal("1"), unit_price=Decimal("10.00"))
        ],
    )

    with pytest.raises(DomainError):
        apply_credits(
            invoice,
            lock_credits(company.id, customer.id, [pending_credit.id]),
        )


@pytest.mark.django_db
def test_two_drafts_cannot_together_over_return_a_line(company, sale):
    """Each draft looks fine alone; the second one to be issued must fail."""
    first = return_of(company, sale, "6")
    second = return_of(company, sale, "6")

    issue_return_invoice(first)

    with pytest.raises(DomainError):
        issue_return_invoice(second)

    second.refresh_from_db()
    sale.refresh_from_db()
    assert second.status == ReturnInvoiceStatus.DRAFT
    assert sale.returned_amount == Decimal("60.00")
