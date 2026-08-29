"""Sales invoice balance and status derivation (invoicing spec §3.4.1, §6.2).

Payment is not binary. A customer can pay in full, pay part, or defer entirely,
and goods can come back after the fact — so the invoice carries a running
balance, and `paid_amount` / `returned_amount` / `balance_due` / `status` are
*always* recomputed from the underlying `PaymentCollection` and issued
`ReturnInvoice` rows. Nothing here trusts a value sent by a client, and nothing
elsewhere in the codebase writes those four fields.

Call `recompute_sales_invoice` after every payment, every issued return, and
every credit application — inside the same transaction as the mutation.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum

from apps.invoices.models import (
    MONEY_ZERO,
    PaymentCollection,
    ReturnInvoice,
    ReturnInvoiceStatus,
    SalesInvoice,
    SalesInvoiceStatus,
)

DERIVED_FIELDS = ["paid_amount", "returned_amount", "balance_due", "status", "updated_at"]


def lock_sales_invoice(invoice_id: int, company_id: int) -> SalesInvoice:
    """Re-read an invoice under a row lock.

    Two reps recording payments on the same invoice, or a payment racing a
    return, would otherwise both read the same stale totals and one would
    overwrite the other's recompute.
    """
    return SalesInvoice.objects.select_for_update().get(
        id=invoice_id, company_id=company_id
    )


def paid_total(invoice_id: int) -> Decimal:
    total = PaymentCollection.objects.filter(sales_invoice_id=invoice_id).aggregate(
        total=Sum("amount")
    )["total"]
    return total or MONEY_ZERO


def returned_total(invoice_id: int) -> Decimal:
    """Only *issued* returns count — a draft credit note has not happened yet."""
    total = ReturnInvoice.objects.filter(
        sales_invoice_id=invoice_id, status=ReturnInvoiceStatus.ISSUED
    ).aggregate(total=Sum("amount"))["total"]
    return total or MONEY_ZERO


def derive_status(*, balance_due: Decimal, paid: Decimal, returned: Decimal) -> str:
    """§3.4.1, verbatim."""
    if balance_due == MONEY_ZERO:
        return SalesInvoiceStatus.FULLY_PAID
    if paid + returned > MONEY_ZERO:
        return SalesInvoiceStatus.PARTIALLY_PAID
    return SalesInvoiceStatus.DEFERRED


def overage_for(*, total: Decimal, paid: Decimal, returned: Decimal) -> Decimal:
    """How far payments plus returns exceed the invoice total, floored at zero."""
    excess = paid + returned - total
    return excess if excess > MONEY_ZERO else MONEY_ZERO


def recompute_sales_invoice(invoice: SalesInvoice, *, save: bool = True) -> SalesInvoice:
    """Refresh the four derived fields from their source records.

    `balance_due` floors at zero and never goes negative (§3.5 rule 3); the excess
    is handled as an overage on the return that caused it.
    """
    paid = paid_total(invoice.id)
    returned = returned_total(invoice.id)
    remaining = invoice.total_amount - paid - returned

    invoice.paid_amount = paid
    invoice.returned_amount = returned
    invoice.balance_due = remaining if remaining > MONEY_ZERO else MONEY_ZERO
    invoice.status = derive_status(
        balance_due=invoice.balance_due, paid=paid, returned=returned
    )

    if save:
        invoice.save(update_fields=DERIVED_FIELDS)

    return invoice
