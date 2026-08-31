"""Pricing resolution service for products.

This module contains framework-agnostic pricing logic that can be reused
across the API and other parts of the application (e.g., order creation).
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from apps.common.models import Currency
from apps.products.models import PriceType, ProductPrice

if TYPE_CHECKING:
    from typing import Sequence

    from apps.customers.models import CustomerCategory
    from apps.products.models import Product


class PriceNotFoundError(Exception):
    """Raised when no price is found for the given criteria."""
    
    pass


def resolve_product_price(
    product: Product,
    currency: Currency | int,
    customer_category: CustomerCategory | int | None = None,
    price_type: str = "standard",
) -> dict:
    """
    Resolve the price for a product given currency and optional customer category.
    
    Resolution logic (in priority order):
    1. If customer_category is provided, look for a price specific to that category
    2. Fall back to the general price for the currency/price_type (no customer_category)
    3. If neither exists, raise PriceNotFoundError
    
    Args:
        product: Product instance or product ID
        currency: Currency instance or currency ID
        customer_category: Optional CustomerCategory instance or ID for category-specific pricing
        price_type: Price type (default: "standard")
    
    Returns:
        dict with:
            - price: Decimal price value
            - currency: Currency instance
            - price_type: str
            - customer_category: CustomerCategory instance or None
            - is_default: bool
            - is_category_specific: bool (True if resolved from category-specific price)
    
    Raises:
        PriceNotFoundError: If no price is found for the given criteria
    
    Example:
        >>> price_info = resolve_product_price(
        ...     product=product_obj,
        ...     currency=usd_currency,
        ...     customer_category=wholesale_category,
        ...     price_type="standard"
        ... )
        >>> print(f"Price: {price_info['price']} {price_info['currency'].code}")
    """
    # Convert IDs to integers if needed
    currency_id = currency.id if hasattr(currency, "id") else currency
    customer_category_id = (
        customer_category.id if hasattr(customer_category, "id") else customer_category
    )
    
    # Build base query
    base_query = ProductPrice.objects.filter(
        product=product,
        currency_id=currency_id,
        price_type=price_type,
    ).select_related("currency", "customer_category")
    
    resolved_price = None
    is_category_specific = False
    
    # Step 1: Try customer-category specific price first
    if customer_category_id:
        category_price = base_query.filter(
            customer_category_id=customer_category_id
        ).first()
        
        if category_price:
            resolved_price = category_price
            is_category_specific = True
    
    # Step 2: Fall back to general price (no customer_category)
    if not resolved_price:
        general_price = base_query.filter(customer_category__isnull=True).first()
        
        if general_price:
            resolved_price = general_price
            is_category_specific = False
    
    # Step 3: No price found
    if not resolved_price:
        category_msg = (
            f" and customer category ID {customer_category_id}"
            if customer_category_id
            else ""
        )
        raise PriceNotFoundError(
            f"No price found for product ID {product.id}, "
            f"currency ID {currency_id}, price type '{price_type}'{category_msg}"
        )
    
    # Return resolved price info
    return {
        "price": resolved_price.price,
        "currency": resolved_price.currency,
        "price_type": resolved_price.price_type,
        "customer_category": resolved_price.customer_category,
        "is_default": resolved_price.is_default,
        "is_category_specific": is_category_specific,
        "valid_from": resolved_price.valid_from,
        "valid_until": resolved_price.valid_until,
        "price_id": resolved_price.id,
    }


def get_product_prices(
    product: Product,
    currency: Currency | int | None = None,
    customer_category: CustomerCategory | int | None = None,
    price_type: str | None = None,
    include_expired: bool = False,
) -> list[ProductPrice]:
    """
    Get all prices for a product with optional filtering.
    
    This is useful for displaying all available prices in the UI or for
    price comparison/selection scenarios.
    
    Args:
        product: Product instance
        currency: Optional currency filter
        customer_category: Optional customer category filter
        price_type: Optional price type filter
        include_expired: Whether to include prices outside valid_from/valid_until range
    
    Returns:
        List of ProductPrice instances matching the criteria
    """
    query = ProductPrice.objects.filter(product=product).select_related(
        "currency", "customer_category"
    )
    
    if currency:
        currency_id = currency.id if hasattr(currency, "id") else currency
        query = query.filter(currency_id=currency_id)
    
    if customer_category is not None:
        if customer_category:
            customer_category_id = (
                customer_category.id
                if hasattr(customer_category, "id")
                else customer_category
            )
            query = query.filter(customer_category_id=customer_category_id)
        else:
            # Explicitly filter for general prices (no customer_category)
            query = query.filter(customer_category__isnull=True)
    
    if price_type:
        query = query.filter(price_type=price_type)
    
    if not include_expired:
        from django.utils import timezone
        now = timezone.now()
        # Include prices where:
        # - valid_from is null OR valid_from <= now
        # - valid_until is null OR valid_until >= now
        from django.db.models import Q
        query = query.filter(
            Q(valid_from__isnull=True) | Q(valid_from__lte=now),
            Q(valid_until__isnull=True) | Q(valid_until__gte=now),
        )
    
    return list(query.order_by("customer_category_id", "currency__code", "price_type"))


def calculate_price_with_tax(
    price: Decimal,
    product: Product,
    include_tax: bool = True,
) -> dict:
    """
    Calculate price with or without tax based on product configuration.
    
    Args:
        price: Base price
        product: Product instance (for tax rate and is_taxable)
        include_tax: Whether to include tax in the result
    
    Returns:
        dict with:
            - base_price: Decimal base price (without tax)
            - tax_amount: Decimal tax amount
            - tax_rate: Decimal tax rate percentage (or None)
            - total_price: Decimal total price (with or without tax based on include_tax)
            - is_taxable: bool
    """
    base_price = Decimal(str(price))
    
    if not product.is_taxable or not product.tax_rate or not include_tax:
        return {
            "base_price": base_price,
            "tax_amount": Decimal("0"),
            "tax_rate": product.tax_rate if product.is_taxable else None,
            "total_price": base_price,
            "is_taxable": product.is_taxable,
        }
    
    tax_rate = Decimal(str(product.tax_rate)) / Decimal("100")
    tax_amount = base_price * tax_rate
    total_price = base_price + tax_amount
    
    return {
        "base_price": base_price,
        "tax_amount": tax_amount.quantize(Decimal("0.01")),
        "tax_rate": product.tax_rate,
        "total_price": total_price.quantize(Decimal("0.01")),
        "is_taxable": True,
    }


def general_prices_by_product(
    product_ids: Sequence[int],
    *,
    currency_code: str,
    price_type: str = PriceType.STANDARD,
) -> dict[int, Decimal]:
    """The general price of many products at once, keyed by product id.

    `resolve_product_price` answers for one product and costs a query each; a
    listing — a van's contents, a catalog page — needs the same answer for every
    row and would otherwise fire one query per product.

    Only the general (no customer category) price is read, which is the whole
    rule when there is no customer in context: nobody is being quoted, the number
    is the shelf price. Missing products are simply absent from the mapping, the
    same way `resolve_unit_price` returns None rather than raising.
    """
    product_ids = {product_id for product_id in product_ids}
    if not product_ids:
        return {}

    currency = Currency.objects.filter(code=currency_code, is_active=True).first()
    if currency is None:
        return {}

    return {
        row.product_id: row.price
        for row in ProductPrice.objects.filter(
            product_id__in=product_ids,
            currency_id=currency.id,
            price_type=price_type,
            customer_category__isnull=True,
        )
    }
