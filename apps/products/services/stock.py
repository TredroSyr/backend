"""Warehouse stock primitives (invoicing spec §6.1 and §6.5).

Every document that moves goods funnels through `apply_stock_changes`. Callers
never touch `ProductWarehouseStock.quantity` or `StockMovement` directly, which
is what keeps three invariants true everywhere:

* **Atomic** (§6.1) — the ledger rows and the projected quantity are written in
  the caller's transaction, alongside the financial record that caused them.
* **Row-locked** (§6.5) — the affected `ProductWarehouseStock` rows are locked
  in a stable order (by product id), so a rep confirming receipt and an admin
  approving a transfer cannot interleave into a lost update or a deadlock.
* **Never negative** — an outbound move that would overdraw a warehouse raises
  `InsufficientStockError` before anything is written.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable, Sequence

from django.db import transaction
from django.db.models import Sum

from apps.products.models import (
    ProductWarehouseStock,
    StockMovement,
    Warehouse,
)
from core.domain import DomainError

if TYPE_CHECKING:
    from apps.products.models import Product

ZERO = Decimal("0")


class InsufficientStockError(DomainError):
    """Raised when an outbound movement would push a warehouse below zero.

    Carries the numbers so the client can show the rep exactly what is on hand
    rather than a bare failure.
    """

    def __init__(self, product: Product, warehouse: Warehouse, available: Decimal, requested: Decimal):
        self.product = product
        self.warehouse = warehouse
        self.available = available
        self.requested = requested
        super().__init__(
            message=f"الكمية غير متوفرة في المستودع للمنتج: {product.name}",
            errors={
                "product_id": [str(product.id)],
                "warehouse_id": [str(warehouse.id)],
                "available": [str(available)],
                "requested": [str(requested)],
            },
        )


@dataclass(frozen=True)
class StockChange:
    """One signed quantity delta for a product. Positive = inbound."""

    product_id: int
    quantity: Decimal


def _merged(changes: Iterable[StockChange]) -> dict[int, Decimal]:
    """Collapse repeated products into a single delta, so a document listing the
    same product on two lines still locks and updates one row.
    """
    merged: dict[int, Decimal] = {}
    for change in changes:
        merged[change.product_id] = merged.get(change.product_id, ZERO) + change.quantity
    return {product_id: delta for product_id, delta in merged.items() if delta != ZERO}


@transaction.atomic
def apply_stock_changes(
    *,
    company_id: int,
    warehouse: Warehouse,
    changes: Sequence[StockChange],
    movement_type: str,
    source_type: str,
    source_id: int | None = None,
    source_number: str = "",
    note: str = "",
) -> list[StockMovement]:
    """Apply signed deltas to one warehouse and append the matching ledger rows.

    Runs in the caller's transaction when there is one (this decorator nests as a
    savepoint), so the financial record and the stock movement commit together.
    """
    deltas = _merged(changes)
    if not deltas:
        return []

    product_ids = sorted(deltas)

    # Ensure a projection row exists for every product before locking. Concurrent
    # callers may race here; ignore_conflicts leans on the (product, warehouse)
    # unique constraint so the loser simply proceeds to the lock below.
    ProductWarehouseStock.objects.bulk_create(
        [
            ProductWarehouseStock(
                company_id=company_id,
                product_id=product_id,
                warehouse=warehouse,
                quantity=ZERO,
            )
            for product_id in product_ids
        ],
        ignore_conflicts=True,
    )

    # Deterministic lock order (product id ascending) prevents deadlocks between
    # two documents touching overlapping product sets in the same warehouse.
    locked = {
        row.product_id: row
        for row in ProductWarehouseStock.objects.select_for_update()
        .select_related("product")
        .filter(warehouse=warehouse, product_id__in=product_ids)
        .order_by("product_id")
    }

    movements: list[StockMovement] = []
    for product_id in product_ids:
        row = locked[product_id]
        delta = deltas[product_id]
        new_quantity = row.quantity + delta

        if new_quantity < ZERO:
            raise InsufficientStockError(
                product=row.product,
                warehouse=warehouse,
                available=row.quantity,
                requested=-delta,
            )

        row.quantity = new_quantity
        movements.append(
            StockMovement(
                company_id=company_id,
                warehouse=warehouse,
                product_id=product_id,
                quantity=delta,
                balance_after=new_quantity,
                movement_type=movement_type,
                source_type=source_type,
                source_id=source_id,
                source_number=source_number,
                note=note,
            )
        )

    ProductWarehouseStock.objects.bulk_update(
        locked.values(), ["quantity", "updated_at"]
    )
    StockMovement.objects.bulk_create(movements)
    return movements


def available_quantity(warehouse_id: int, product_id: int) -> Decimal:
    """Current projected quantity for a (warehouse, product) pair."""
    row = ProductWarehouseStock.objects.filter(
        warehouse_id=warehouse_id, product_id=product_id
    ).first()
    return row.quantity if row else ZERO


def ledger_balance(warehouse_id: int, product_id: int) -> Decimal:
    """Recompute a quantity straight from the ledger.

    The projection is the fast path; this is the source of truth used to verify
    it (reconciliation jobs, tests, support questions).
    """
    total = StockMovement.objects.filter(
        warehouse_id=warehouse_id, product_id=product_id
    ).aggregate(total=Sum("quantity"))["total"]
    return total or ZERO
