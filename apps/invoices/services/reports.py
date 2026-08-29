"""Admin-facing reports (invoicing spec §5).

Overdue debt is a computed report, not a real-time alert — v1 is pull-only
(§7 defers push alerts). It is refreshed on read, so there is no cached table to
drift out of date.

An invoice is overdue when it is still owed (`deferred` or `partially_paid`) and
more than `overdue_threshold_days` have passed since it was created. The
threshold is configurable per company on Invoice Settings and defaults to 7 days.

The report groups by both dimensions the spec requires — by rep and by customer —
from a single pass over the same queryset.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.db.models import Count, QuerySet, Sum
from django.utils import timezone

from apps.invoices.models import (
    MONEY_ZERO,
    PaymentCollection,
    PaymentSource,
    RepCashAdjustment,
    SalesInvoice,
    SalesInvoiceStatus,
)
from apps.invoices.services.documents import get_invoice_settings
from core.responses import decimal_string

if TYPE_CHECKING:
    from datetime import datetime

#: Statuses that still owe the company money.
OUTSTANDING_STATUSES = (
    SalesInvoiceStatus.DEFERRED,
    SalesInvoiceStatus.PARTIALLY_PAID,
)


def overdue_queryset(
    company_id: int,
    *,
    threshold_days: int | None = None,
    rep_id: int | None = None,
    customer_id: int | None = None,
) -> QuerySet[SalesInvoice]:
    """Sales invoices past the company's overdue threshold and still owed."""
    if threshold_days is None:
        threshold_days = get_invoice_settings(company_id).overdue_threshold_days

    cutoff = timezone.now() - timedelta(days=threshold_days)
    queryset = SalesInvoice.objects.filter(
        company_id=company_id,
        status__in=OUTSTANDING_STATUSES,
        created_at__lt=cutoff,
    )

    if rep_id:
        queryset = queryset.filter(rep_id=rep_id)
    if customer_id:
        queryset = queryset.filter(customer_id=customer_id)

    return queryset


def overdue_debt_report(
    company_id: int,
    *,
    threshold_days: int | None = None,
    rep_id: int | None = None,
    customer_id: int | None = None,
) -> dict:
    """Outstanding debt grouped by rep and by customer, plus the company total.

    Surfaced from the existing rep-activity monitoring screen rather than a new
    module — the per-rep grouping is exactly what that screen already shows.
    """
    if threshold_days is None:
        threshold_days = get_invoice_settings(company_id).overdue_threshold_days

    invoices = overdue_queryset(
        company_id,
        threshold_days=threshold_days,
        rep_id=rep_id,
        customer_id=customer_id,
    )

    by_rep = [
        {
            "rep_id": row["rep_id"],
            "rep_name": row["rep__name"],
            "invoice_count": row["invoice_count"],
            "total_balance_due": decimal_string(row["total_balance_due"]),
        }
        for row in invoices.values("rep_id", "rep__name")
        .annotate(
            invoice_count=Count("id"),
            total_balance_due=Sum("balance_due"),
        )
        .order_by("-total_balance_due")
    ]

    # Per customer the spec also wants the individual invoice ids, so this
    # dimension is built from the rows rather than a GROUP BY.
    customers: dict[int, dict] = {}
    for invoice in invoices.select_related("customer").order_by("created_at"):
        entry = customers.setdefault(
            invoice.customer_id,
            {
                "customer_id": invoice.customer_id,
                "customer_name": invoice.customer.name,
                "invoice_count": 0,
                "total_balance_due": MONEY_ZERO,
                "invoices": [],
            },
        )
        entry["invoice_count"] += 1
        entry["total_balance_due"] += invoice.balance_due
        entry["invoices"].append(
            {
                "id": invoice.id,
                "number": invoice.number,
                "date": invoice.date,
                "balance_due": decimal_string(invoice.balance_due),
                "status": invoice.status,
                "days_overdue": (timezone.now() - invoice.created_at).days,
            }
        )

    totals = invoices.aggregate(
        invoice_count=Count("id"), total_balance_due=Sum("balance_due")
    )

    return {
        "overdue_threshold_days": threshold_days,
        "generated_at": timezone.now(),
        "totals": {
            "invoice_count": totals["invoice_count"] or 0,
            "total_balance_due": decimal_string(totals["total_balance_due"]),
        },
        "by_rep": by_rep,
        "by_customer": [
            {**row, "total_balance_due": decimal_string(row["total_balance_due"])}
            for row in sorted(
                customers.values(),
                key=lambda row: row["total_balance_due"],
                reverse=True,
            )
        ],
    }


def rep_cash_reconciliation(
    company_id: int,
    *,
    rep_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> dict:
    """What each rep is expected to hand in.

    Cash collected, minus cash they refunded to customers on the spot via the
    `cash_refunded_by_rep` path (§3.5 rule 3). Credits applied are excluded —
    no money changed hands for those.

    This is the reconciliation figure the refund path needs, not a full
    settlement module: nothing here closes a period or records a hand-over.
    """
    payments = PaymentCollection.objects.filter(
        company_id=company_id, source=PaymentSource.CASH, collected_by__isnull=False
    )
    adjustments = RepCashAdjustment.objects.filter(company_id=company_id)

    if rep_id:
        payments = payments.filter(collected_by_id=rep_id)
        adjustments = adjustments.filter(rep_id=rep_id)
    if date_from:
        payments = payments.filter(collected_at__gte=date_from)
        adjustments = adjustments.filter(created_at__gte=date_from)
    if date_to:
        payments = payments.filter(collected_at__lte=date_to)
        adjustments = adjustments.filter(created_at__lte=date_to)

    collected: dict[int, dict] = {}
    for row in payments.values("collected_by_id", "collected_by__name").annotate(
        total=Sum("amount"), payment_count=Count("id")
    ):
        collected[row["collected_by_id"]] = {
            "rep_id": row["collected_by_id"],
            "rep_name": row["collected_by__name"],
            "cash_collected": row["total"] or MONEY_ZERO,
            "payment_count": row["payment_count"],
            "adjustments": MONEY_ZERO,
            "expected_cash_in": row["total"] or MONEY_ZERO,
        }

    for row in adjustments.values("rep_id", "rep__name").annotate(total=Sum("amount")):
        entry = collected.setdefault(
            row["rep_id"],
            {
                "rep_id": row["rep_id"],
                "rep_name": row["rep__name"],
                "cash_collected": MONEY_ZERO,
                "payment_count": 0,
                "adjustments": MONEY_ZERO,
                "expected_cash_in": MONEY_ZERO,
            },
        )
        entry["adjustments"] = row["total"] or MONEY_ZERO
        entry["expected_cash_in"] = entry["cash_collected"] + entry["adjustments"]

    rows = sorted(collected.values(), key=lambda row: row["rep_name"] or "")
    money_fields = ("cash_collected", "adjustments", "expected_cash_in")

    return {
        "generated_at": timezone.now(),
        "date_from": date_from,
        "date_to": date_to,
        "totals": {
            field: decimal_string(sum((row[field] for row in rows), MONEY_ZERO))
            for field in money_fields
        },
        "by_rep": [
            {**row, **{field: decimal_string(row[field]) for field in money_fields}}
            for row in rows
        ],
    }
