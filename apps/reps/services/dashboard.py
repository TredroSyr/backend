"""The rep home screen, assembled from documents that already exist.

Every figure here is derived on read. The period cards come from the rep's own
sales and return invoices, the receivables figure from the same `balance_due`
the invoice services maintain (invoicing spec §6.2), and the van contents from
the `ProductWarehouseStock` projection. Nothing is cached and nothing is stored,
so the screen cannot drift away from the documents behind it.

**Two different time windows live on this screen and the difference matters.**
The `sales` and `returns` cards answer "what did I do in this period". The
`receivables` card answers "what am I still owed", which is deliberately *not*
period-scoped — money owed from last week is still owed today, and scoping it to
the selected day would show a rep zero outstanding debt every morning.

The preview lists are a convenience, not a second API: they let the home screen
render in one call. Anything longer than `preview_limit` is read from the
endpoints that already page and filter — `/api/reps/sales-invoices/` and
`/api/reps/return-invoices/` — which accept the same `date_from`/`date_to`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Count, Sum

from apps.common.models import Currency
from apps.common.serializers import LINE_COUNT_ANNOTATION
from apps.common.services.periods import parse_period, within_period
from apps.invoices.models import (
    ReturnInvoice,
    ReturnInvoiceStatus,
    SalesInvoice,
)
from apps.invoices.services.reports import OUTSTANDING_STATUSES, overdue_queryset
from apps.notifications.models import ActorType
from apps.notifications.services import unread_count
from apps.products.services.pricing import general_prices_by_product
from apps.reps.services.inventory import rep_warehouse, van_stock_queryset, van_totals
from core.domain import DomainError
from core.responses import decimal_string

if TYPE_CHECKING:
    from datetime import datetime

    from apps.companies.models import Company
    from apps.reps.models import Rep

#: Re-exported so the view imports its whole vocabulary from one module. The
#: parsing itself is shared with the invoice lists — see
#: `apps.common.services.periods` for why a bare date covers its whole day.
__all__ = [
    "DEFAULT_PREVIEW_LIMIT",
    "MAX_PREVIEW_LIMIT",
    "parse_period",
    "parse_preview_limit",
    "rep_dashboard",
    "van_summary",
]

#: Rows returned inline per section. Enough to fill a phone screen; the full
#: lists live on the paged document endpoints.
DEFAULT_PREVIEW_LIMIT = 10
MAX_PREVIEW_LIMIT = 50


def parse_preview_limit(params) -> int:
    """How many rows each section returns inline, clamped to something sane."""
    raw = params.get("limit")
    if not raw:
        return DEFAULT_PREVIEW_LIMIT

    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise DomainError("قيمة غير صالحة", {"limit": ["Expected a positive integer."]})

    if limit < 1:
        raise DomainError("قيمة غير صالحة", {"limit": ["Expected a positive integer."]})

    return min(limit, MAX_PREVIEW_LIMIT)


def _currency_payload(code: str) -> dict:
    """The document currency, with the symbol the app prints beside every total."""
    currency = Currency.objects.filter(code=code).first()
    return {
        "code": code,
        "name": currency.name if currency else "",
        "symbol": currency.symbol if currency else "",
    }


def van_summary(*, company: Company, rep: Rep, preview_limit: int) -> dict | None:
    """The van card: its totals, and the first rows of what is loaded.

    None when the rep has no active van — the client renders "no warehouse"
    rather than an empty one, which are different things to a rep about to load
    up. Prices are resolved for the whole page in one query, so a full van does
    not turn the home screen into one query per product.
    """
    warehouse = rep_warehouse(company.id, rep.id)
    if warehouse is None:
        return None

    stock = van_stock_queryset(warehouse)
    totals = van_totals(stock)
    items = list(stock[:preview_limit])

    return {
        "id": warehouse.id,
        "name": warehouse.name,
        "total_quantity": decimal_string(totals["total_quantity"], places=3),
        "product_count": totals["product_count"],
        "items": items,
        "prices": general_prices_by_product(
            [row.product_id for row in items], currency_code=company.currency
        ),
    }


def rep_dashboard(
    *,
    company: Company,
    rep: Rep,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    preview_limit: int = DEFAULT_PREVIEW_LIMIT,
) -> dict:
    """Every number and list the rep home screen renders, in one read.

    Money is returned as fixed-precision strings via `decimal_string`; documents
    are returned as model instances, which the view then renders with the very
    serializers the document endpoints use, so an invoice looks identical
    whichever screen it appears on.
    """
    sales = SalesInvoice.objects.filter(company_id=company.id, rep_id=rep.id)
    period_sales = within_period(sales, "date", date_from, date_to)

    sales_totals = period_sales.aggregate(
        invoice_count=Count("id"),
        total_amount=Sum("total_amount"),
        paid_amount=Sum("paid_amount"),
        balance_due=Sum("balance_due"),
    )

    returns = ReturnInvoice.objects.filter(company_id=company.id, rep_id=rep.id)
    period_returns = within_period(returns, "date", date_from, date_to)

    # Only an issued return moved goods or money; a draft is one the rep started
    # and has not committed. Counting it separately keeps the period's returned
    # total honest while still letting the app badge unfinished work.
    issued_returns = period_returns.filter(status=ReturnInvoiceStatus.ISSUED)
    returns_totals = issued_returns.aggregate(
        count=Count("id"), total_amount=Sum("amount")
    )

    outstanding = sales.filter(status__in=OUTSTANDING_STATUSES)
    receivables = outstanding.aggregate(
        invoice_count=Count("id"), total_balance_due=Sum("balance_due")
    )
    # Same threshold the admin overdue report uses, so "late" means one thing
    # across the two apps rather than two.
    overdue = overdue_queryset(company.id, rep_id=rep.id).aggregate(
        invoice_count=Count("id"), total_balance_due=Sum("balance_due")
    )

    return {
        "rep": {
            "id": rep.id,
            "name": rep.name,
            "phone": rep.phone,
            "work_days": rep.work_days,
            "company": {"id": company.id, "name": company.name},
        },
        "period": {"date_from": date_from, "date_to": date_to},
        "currency": _currency_payload(company.currency),
        "sales": {
            "invoice_count": sales_totals["invoice_count"] or 0,
            "total_amount": decimal_string(sales_totals["total_amount"]),
            "paid_amount": decimal_string(sales_totals["paid_amount"]),
            "balance_due": decimal_string(sales_totals["balance_due"]),
            "invoices": list(
                period_sales.select_related("customer", "rep", "warehouse")
                .annotate(**{LINE_COUNT_ANNOTATION: Count("lines")})
                .order_by("-date", "-id")[:preview_limit]
            ),
        },
        "returns": {
            "count": returns_totals["count"] or 0,
            "total_amount": decimal_string(returns_totals["total_amount"]),
            "draft_count": period_returns.filter(
                status=ReturnInvoiceStatus.DRAFT
            ).count(),
            "return_invoices": list(
                period_returns.select_related(
                    "sales_invoice", "rep", "warehouse"
                ).order_by("-date", "-id")[:preview_limit]
            ),
        },
        "receivables": {
            "invoice_count": receivables["invoice_count"] or 0,
            "total_balance_due": decimal_string(receivables["total_balance_due"]),
            "overdue_invoice_count": overdue["invoice_count"] or 0,
            "overdue_balance_due": decimal_string(overdue["total_balance_due"]),
        },
        "warehouse": van_summary(company=company, rep=rep, preview_limit=preview_limit),
        "notifications": {
            "unread_count": unread_count(
                recipient_actor_type=ActorType.REP,
                recipient_actor_id=rep.id,
                company_id=company.id,
            )
        },
    }
