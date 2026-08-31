"""Indicative money on a customer request.

A request line deliberately stores no price — nothing has been agreed yet, and
the rep prices the goods when the Sales Invoice is written (§3.3). But the rep
screen still has to show what a request is roughly worth, or "accept" is a
decision made blind.

So the figures here are **resolved from the catalog on read, never stored**. They
are what the customer *would* be charged today, category override included, which
is the same answer `resolve_unit_price` gives the sales-invoice service. If the
catalog changes before the visit, the next read shows the new number — which is
correct, because nothing was ever promised.

Two queries for a whole page: one for the customers' categories, one for the
prices. Resolving per line would be one query each.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Iterable

from apps.customers.models import CustomerCategoryAssignment
from apps.products.services.pricing import price_for, prices_by_product

if TYPE_CHECKING:
    from apps.companies.models import Company
    from apps.orders.models import CustomerRequest

ZERO = Decimal("0")


def price_requests(requests: Iterable[CustomerRequest], *, company: Company) -> dict:
    """Unit prices for every line across `requests`, keyed by line id.

    Returned as a flat `{line_id: Decimal}` so a serializer can look a line up
    without knowing anything about categories or currencies. A product the
    catalog has no price for is absent, and renders as null rather than zero —
    "not priced" and "free" are different claims.
    """
    requests = list(requests)
    if not requests:
        return {}

    lines = [line for item in requests for line in item.lines.all()]
    if not lines:
        return {}

    # One customer may appear on several requests; one query covers them all.
    categories = dict(
        CustomerCategoryAssignment.objects.filter(
            company_id=company.id,
            customer_id__in={item.customer_id for item in requests},
        ).values_list("customer_id", "category_id")
    )

    prices = prices_by_product(
        [line.product_id for line in lines],
        currency_code=company.currency,
        category_ids=set(categories.values()),
    )

    resolved = {}
    for item in requests:
        category_id = categories.get(item.customer_id)
        for line in item.lines.all():
            price = price_for(prices, line.product_id, category_id)
            if price is not None:
                resolved[line.id] = price

    return resolved
