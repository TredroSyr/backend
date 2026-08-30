"""Product lookups shared by every document that has lines.

Both `invoices` and `orders` need the same thing when a client posts line data:
fetch all referenced products in one query, confirm they belong to the caller's
company, and fail with the offending ids rather than a bare 404.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from apps.common.models import Currency
from apps.products.models import Product
from apps.products.services.pricing import PriceNotFoundError, resolve_product_price
from core.domain import DomainError

if TYPE_CHECKING:
    from apps.companies.models import Company
    from apps.customers.models import Customer


def products_by_id(
    company_id: int, product_ids: Sequence[int], *, sellable_only: bool = False
) -> dict[int, Product]:
    """Load the company's products keyed by id, rejecting anything unknown.

    `sellable_only` guards the sales path so a product flagged not-for-sale can
    still be received into stock but never invoiced out.
    """
    queryset = Product.objects.filter(
        company_id=company_id, id__in=set(product_ids), is_active=True
    ).select_related("unit")

    if sellable_only:
        queryset = queryset.filter(is_sellable=True)

    products = {product.id: product for product in queryset}

    missing = [product_id for product_id in product_ids if product_id not in products]
    if missing:
        raise DomainError(
            "بعض المنتجات غير موجودة أو غير متاحة",
            {"lines": [f"Unknown or unavailable product ids: {sorted(set(missing))}"]},
        )

    return products


def resolve_unit_price(
    product: Product,
    *,
    company: Company,
    customer: Customer | None = None,
    currency_code: str = "",
) -> Decimal | None:
    """Best-known price for a product, or None when the catalog has no answer.

    Reuses the existing pricing resolution (customer-category override, then the
    general price) so a rep can post a line without a price and get the same
    figure the catalog would show. Returning None rather than raising lets the
    caller ask for an explicit price instead of guessing.

    `currency_code` is the document's own currency, which is not always the
    company's: prices are stored per currency, so a document priced in USD has to
    read the USD rows or the number would be a SYP figure wearing a USD label.
    Defaults to the company's currency, which is what the document defaults to.
    """
    currency = Currency.objects.filter(
        code=currency_code or company.currency, is_active=True
    ).first()
    if currency is None:
        return None

    category = (
        customer.get_category_for_company(company.id) if customer is not None else None
    )

    try:
        return resolve_product_price(
            product, currency=currency, customer_category=category
        )["price"]
    except PriceNotFoundError:
        return None
