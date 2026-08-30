"""Pending customer credits (invoicing spec §3.7).

This is a tracked list, not a ledger. Full credit-balance automation is
explicitly deferred (§7), so nothing here applies a credit on its own: a rep or
admin picks the credits to use while writing a new Sales Invoice, and each one
applied is recorded as a `PaymentCollection` with `source=customer_credit`. That
keeps `paid_amount` accurate and every unit of value traceable to where it came
from, instead of a silent discount nobody can audit later.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from django.db import transaction
from django.db.models import QuerySet, Sum
from django.utils import timezone

from apps.common.services.audit import record_audit
from apps.invoices.models import (
    MONEY_ZERO,
    CustomerCreditStatus,
    PaymentSource,
    PendingCustomerCredit,
    RefundMethod,
    SalesInvoice,
)
from apps.invoices.services.payments import add_payment
from core.domain import DomainError

if TYPE_CHECKING:
    from rest_framework.request import Request

    from apps.invoices.models import ReturnInvoice


def pending_credits_for(company_id: int, customer_id: int) -> QuerySet[PendingCustomerCredit]:
    """Credits a customer can still spend with this company.

    Surfaced when a rep starts a new invoice ("this customer has a pending credit
    of X — apply it?"), never applied silently (§3.7 rule 1).
    """
    return (
        PendingCustomerCredit.objects.filter(
            company_id=company_id,
            customer_id=customer_id,
            status=CustomerCreditStatus.PENDING,
        )
        .select_related("source_return_invoice")
        .order_by("created_at")
    )


def pending_credit_total(company_id: int, customer_id: int) -> Decimal:
    total = pending_credits_for(company_id, customer_id).aggregate(total=Sum("amount"))[
        "total"
    ]
    return total or MONEY_ZERO


def create_credit_from_return(
    return_invoice: ReturnInvoice,
    *,
    amount: Decimal,
    request: Request | None = None,
) -> PendingCustomerCredit:
    """The `deferred_customer_credit` refund path (§3.5 rule 3).

    No cash moved; the customer is owed value against a future purchase. The sale
    itself closes at `balance_due = 0` and the amount now lives on this record.
    """
    credit = PendingCustomerCredit.objects.create(
        company_id=return_invoice.company_id,
        customer_id=return_invoice.sales_invoice.customer_id,
        source_return_invoice=return_invoice,
        amount=amount,
    )

    record_audit(
        company_id=credit.company_id,
        entity=credit,
        action="credit_created",
        request=request,
        to_status=credit.status,
        changes={
            "amount": str(amount),
            "return_invoice": return_invoice.number,
            "refund_method": RefundMethod.DEFERRED_CUSTOMER_CREDIT.value,
        },
    )
    return credit


def lock_credits(
    company_id: int, customer_id: int, credit_ids: Sequence[int]
) -> list[PendingCustomerCredit]:
    """Load the chosen credits under a row lock, rejecting any already spent."""
    credits = list(
        PendingCustomerCredit.objects.select_for_update()
        .filter(company_id=company_id, customer_id=customer_id, id__in=credit_ids)
        .order_by("id")
    )

    found = {credit.id for credit in credits}
    missing = [credit_id for credit_id in credit_ids if credit_id not in found]
    if missing:
        raise DomainError(
            "بعض الأرصدة المحددة غير موجودة لهذا العميل",
            {"credit_ids": [f"Not found for this customer: {missing}"]},
        )

    spent = [c.id for c in credits if c.status != CustomerCreditStatus.PENDING]
    if spent:
        raise DomainError(
            "بعض الأرصدة المحددة تم استخدامها مسبقاً",
            {"credit_ids": [f"Already applied or cancelled: {spent}"]},
        )

    return credits


@transaction.atomic
def apply_credits(
    invoice: SalesInvoice,
    credits: Sequence[PendingCustomerCredit],
    *,
    request: Request | None = None,
) -> list:
    """Spend the given credits against an invoice the caller already owns.

    Treated as an immediate partial payment sourced from the credit (§3.7 rule 2)
    rather than a discount, so `paid_amount` stays honest. Several credits may be
    applied at once as long as they fit inside the invoice total (§3.7 rule 4) and
    share its currency.
    """
    if not credits:
        return []

    # Currency first: a credit is denominated by the sale it came back from, and
    # documents no longer all share the company's currency. Comparing a USD credit
    # against a SYP total below would be arithmetic on two different units — the
    # "exceeds the invoice" check cannot mean anything until this one passes.
    mismatched = [
        credit.id
        for credit in credits
        if credit.source_return_invoice.currency != invoice.currency
    ]
    if mismatched:
        raise DomainError(
            "لا يمكن استخدام رصيد بعملة مختلفة عن عملة الفاتورة",
            {
                "credit_ids": [
                    f"Credits not denominated in {invoice.currency}: {mismatched}"
                ],
                "currency": [invoice.currency],
            },
        )

    total = sum((credit.amount for credit in credits), MONEY_ZERO)
    if total > invoice.total_amount:
        raise DomainError(
            "مجموع الأرصدة المستخدمة يتجاوز قيمة الفاتورة",
            {
                "credit_ids": ["Sum of credits exceeds the invoice total."],
                "total_amount": [str(invoice.total_amount)],
                "credits_total": [str(total)],
            },
        )

    payments = []
    for credit in credits:
        payment = add_payment(
            invoice,
            amount=credit.amount,
            collected_by_id=invoice.rep_id,
            source=PaymentSource.CUSTOMER_CREDIT,
            applied_credit=credit,
            note=f"Applied customer credit #{credit.id} from {credit.source_return_invoice.number}",
            request=request,
        )
        payments.append(payment)

        credit.status = CustomerCreditStatus.APPLIED
        credit.applied_to_invoice = invoice
        credit.applied_at = timezone.now()
        credit.save(
            update_fields=["status", "applied_to_invoice", "applied_at", "updated_at"]
        )

        record_audit(
            company_id=credit.company_id,
            entity=credit,
            action="credit_applied",
            request=request,
            from_status=CustomerCreditStatus.PENDING,
            to_status=credit.status,
            changes={"invoice": invoice.number, "amount": str(credit.amount)},
        )

    return payments


@transaction.atomic
def cancel_credit(
    credit: PendingCustomerCredit, *, request: Request | None = None
) -> PendingCustomerCredit:
    """Write off a credit the company no longer owes (admin action)."""
    if credit.status != CustomerCreditStatus.PENDING:
        raise DomainError(
            "لا يمكن إلغاء رصيد تم استخدامه",
            {"status": [f"Cannot cancel a credit in status '{credit.status}'."]},
        )

    previous_status = credit.status
    credit.status = CustomerCreditStatus.CANCELLED
    credit.save(update_fields=["status", "updated_at"])

    record_audit(
        company_id=credit.company_id,
        entity=credit,
        action="credit_cancelled",
        request=request,
        from_status=previous_status,
        to_status=credit.status,
    )
    return credit
