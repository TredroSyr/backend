"""What each store owes the rep who serves it.

The three figures the stores list and the store page both show — invoiced, paid,
still due — are a rollup of that customer's sales invoices. They are not stored
anywhere: `total_amount`, `paid_amount` and `balance_due` are already derived per
invoice by `apps.invoices.services.balances` (invoicing spec §6.2), so summing
them is the whole calculation, and a payment recorded anywhere in the system
moves these numbers without a second write.

**Scoped to the asking rep**, like every other `/api/reps/` read. A store may
also buy direct from the company or from another rep; those invoices are that
rep's business, not this one's, and folding them in would show a rep a debt they
cannot collect.
"""

from __future__ import annotations

from django.db.models import Count, Sum

from apps.invoices.models import SalesInvoice
from core.responses import decimal_string

#: What a store with no invoices yet reports — the "0 ل.س" card, not a blank one.
EMPTY_BALANCE = {
    "invoice_count": 0,
    "total_invoiced": "0.00",
    "paid_amount": "0.00",
    "returned_amount": "0.00",
    "balance_due": "0.00",
}


def customer_balances(
    company_id: int, rep_id: int, customer_ids=None
) -> dict[int, dict]:
    """The rollup for many stores in one query, keyed by customer id.

    Pass `customer_ids` to bound the aggregate to the page being rendered.
    Customers with no invoices are simply absent — callers fall back to
    `EMPTY_BALANCE` rather than this inventing rows for stores it was not asked
    about.
    """
    queryset = SalesInvoice.objects.filter(company_id=company_id, rep_id=rep_id)
    if customer_ids is not None:
        queryset = queryset.filter(customer_id__in=customer_ids)

    return {
        row["customer_id"]: {
            "invoice_count": row["invoice_count"],
            "total_invoiced": decimal_string(row["total_invoiced"]),
            "paid_amount": decimal_string(row["paid_amount"]),
            "returned_amount": decimal_string(row["returned_amount"]),
            "balance_due": decimal_string(row["balance_due"]),
        }
        for row in queryset.values("customer_id").annotate(
            invoice_count=Count("id"),
            total_invoiced=Sum("total_amount"),
            paid_amount=Sum("paid_amount"),
            returned_amount=Sum("returned_amount"),
            balance_due=Sum("balance_due"),
        )
    }
