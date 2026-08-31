"""What is in a rep's van, read through the existing stock projection.

Nothing here owns a quantity. `ProductWarehouseStock` is the projection
`apps.products.services.stock` maintains from the `StockMovement` ledger, so the
van screen and the sales invoice that deducts it are reading the same number by
construction — a rep can never be shown stock a sale would then refuse to move.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db.models import Count, Sum

from apps.products.models import (
    ProductWarehouseStock,
    Warehouse,
    WarehouseOwnerType,
)
from apps.products.services.images import primary_image_prefetch

if TYPE_CHECKING:
    from django.db.models import QuerySet

ZERO = Decimal("0")


def rep_warehouse(company_id: int, rep_id: int) -> Warehouse | None:
    """The rep's van, or None when they have not got an active one.

    `products.services.warehouses.default_rep_warehouse` answers the same
    question by raising, which is right for a document that cannot be written
    without a warehouse. A read-only screen has to render anyway — a rep whose
    van an admin just deactivated should see an empty van, not an error — so this
    returns None and leaves the decision to the caller.
    """
    return (
        Warehouse.objects.filter(
            company_id=company_id,
            rep_id=rep_id,
            owner_type=WarehouseOwnerType.REP,
            is_active=True,
        )
        .order_by("id")
        .first()
    )


def van_stock_queryset(
    warehouse: Warehouse, *, include_empty: bool = False
) -> QuerySet[ProductWarehouseStock]:
    """Rows for one van, carrying everything a stock line renders.

    Products that ran out are hidden by default: a van list is "what can I sell
    right now", and a row reading zero is noise on a phone. `include_empty` is
    for the stock-take screen, where the zeroes are the point.
    """
    queryset = ProductWarehouseStock.objects.filter(
        warehouse=warehouse, product__is_active=True
    ).select_related("product", "product__unit")

    if not include_empty:
        queryset = queryset.exclude(quantity=ZERO)

    return queryset.prefetch_related(
        primary_image_prefetch("product__images")
    ).order_by("product__name", "product_id")


def van_totals(queryset: QuerySet[ProductWarehouseStock]) -> dict:
    """The two headline numbers above a van list.

    `total_quantity` deliberately adds cartons to bags to litres. It is the
    "314 قطعة" the rep app prints — a count of things loaded, not a dimensioned
    quantity — and the per-line units below it are what carry the meaning.
    """
    totals = queryset.aggregate(
        total_quantity=Sum("quantity"), product_count=Count("id")
    )
    return {
        "total_quantity": totals["total_quantity"] or ZERO,
        "product_count": totals["product_count"] or 0,
    }
