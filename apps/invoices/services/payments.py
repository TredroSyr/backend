"""Payment Collection service (invoicing spec §3.6).

A payment is an append-only row, never a field on the invoice: one sale can be
collected across several visits. Every insert recomputes the parent invoice's
derived totals, and a rep never types a "new balance" — they append what they
collected and the balance follows.

Two entry points:

* `add_payment` — the invoice is already owned by the caller's transaction (it
  was just created, or already locked).
* `collect_payment` — locks the invoice first. This is what views call.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import record_audit
from apps.invoices.models import (
    MONEY_ZERO,
    PaymentCollection,
    PaymentSource,
    SalesInvoice,
)
from apps.invoices.services.balances import lock_sales_invoice, recompute_sales_invoice
from core.domain import DomainError

if TYPE_CHECKING:
    from datetime import datetime

    from rest_framework.request import Request

    from apps.invoices.models import PendingCustomerCredit


def add_payment(
    invoice: SalesInvoice,
    *,
    amount: Decimal,
    collected_by_id: int | None = None,
    collected_at: datetime | None = None,
    source: str = PaymentSource.CASH,
    applied_credit: PendingCustomerCredit | None = None,
    note: str = "",
    request: Request | None = None,
) -> PaymentCollection:
    """Append one payment to an invoice the caller already owns, then recompute.

    Overpayment is rejected. The spec's only defined route for money exceeding
    the invoice total is a return that produces an overage (§3.5 rule 3), which
    carries a `refund_method`; a bare cash overpayment has no defined resolution,
    so accepting one would leave money the system cannot account for.
    """
    if amount <= MONEY_ZERO:
        raise DomainError(
            "قيمة الدفعة يجب أن تكون أكبر من صفر",
            {"amount": ["Payment amount must be positive."]},
        )

    if amount > invoice.balance_due:
        raise DomainError(
            "قيمة الدفعة تتجاوز الرصيد المتبقي على الفاتورة",
            {
                "amount": ["Payment exceeds the invoice balance."],
                "balance_due": [str(invoice.balance_due)],
            },
        )

    payment = PaymentCollection.objects.create(
        company_id=invoice.company_id,
        sales_invoice=invoice,
        amount=amount,
        collected_by_id=collected_by_id,
        collected_at=collected_at or timezone.now(),
        source=source,
        applied_credit=applied_credit,
        note=note,
    )

    recompute_sales_invoice(invoice)

    record_audit(
        company_id=invoice.company_id,
        entity=invoice,
        action="payment_recorded",
        request=request,
        to_status=invoice.status,
        changes={
            "payment_id": payment.id,
            "amount": str(amount),
            "source": source,
            "balance_due": str(invoice.balance_due),
        },
    )
    return payment


@transaction.atomic
def collect_payment(
    *,
    company_id: int,
    invoice_id: int,
    amount: Decimal,
    collected_by_id: int | None = None,
    collected_at: datetime | None = None,
    note: str = "",
    request: Request | None = None,
) -> tuple[PaymentCollection, SalesInvoice]:
    """Lock the invoice, append the payment, return both."""
    invoice = lock_sales_invoice(invoice_id, company_id)
    payment = add_payment(
        invoice,
        amount=amount,
        collected_by_id=collected_by_id,
        collected_at=collected_at,
        note=note,
        request=request,
    )
    return payment, invoice
