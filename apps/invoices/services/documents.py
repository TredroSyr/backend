"""Pieces every financial document shares.

Header snapshots, line persistence and the translation from lines to stock
deltas are identical for incoming, sales and return invoices — they live here so
the three document services differ only where the domain actually differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import TYPE_CHECKING, Iterable, Sequence

from apps.invoices.models import MONEY_ZERO, InvoiceSettings
from apps.products.models import Warehouse, WarehouseOwnerType
from apps.products.services.stock import StockChange
from core.domain import DomainError

if TYPE_CHECKING:
    from django.db.models import Model

    from apps.products.models import Product


@dataclass(frozen=True)
class LineInput:
    """One validated document line, resolved to model instances by the serializer.

    `extra` carries fields specific to a single document type (e.g. the
    `sales_invoice_line` a return line credits) without forcing every caller to
    know about them.
    """

    product: Product
    quantity: Decimal
    unit_price: Decimal
    tax_rate: Decimal = MONEY_ZERO
    extra: dict = field(default_factory=dict)


def get_invoice_settings(company_id: int) -> InvoiceSettings:
    """Fetch (creating on first use) the company's shared invoice settings (§6.8)."""
    settings, _ = InvoiceSettings.objects.select_related("company").get_or_create(
        company_id=company_id
    )
    return settings


def persist_lines(
    line_model: type[Model],
    *,
    company_id: int,
    parent_field: str,
    parent: Model,
    inputs: Sequence[LineInput],
) -> Decimal:
    """Create the document's lines and return the summed subtotal.

    `bulk_create` skips `Model.save()`, so subtotals are computed explicitly here
    rather than relying on the override in `DocumentLine`.
    """
    lines = [
        line_model(
            company_id=company_id,
            product=item.product,
            unit_id=item.product.unit_id,
            quantity=item.quantity,
            unit_price=item.unit_price,
            tax_rate=item.tax_rate,
            **{parent_field: parent},
            **item.extra,
        )
        for item in inputs
    ]

    for line in lines:
        line.subtotal = line.compute_subtotal()

    line_model.objects.bulk_create(lines)
    return sum((line.subtotal for line in lines), MONEY_ZERO)


def stock_changes(lines: Iterable[LineInput | Model], *, outbound: bool) -> list[StockChange]:
    """Turn document lines into signed ledger deltas.

    Accepts either `LineInput`s (before the lines exist) or persisted line rows —
    both expose `product` and `quantity`.
    """
    sign = -1 if outbound else 1
    return [
        StockChange(product_id=line.product.id, quantity=sign * line.quantity)
        for line in lines
    ]


def require_warehouse(
    warehouse: Warehouse,
    *,
    company_id: int,
    owner_type: str | None = None,
    rep_id: int | None = None,
) -> Warehouse:
    """Validate that a warehouse may be used by this company/rep for a document.

    Documents name the warehouse they move stock through, so this guard is what
    stops an incoming invoice from filling a rep's van or one rep's sale from
    draining another rep's stock.
    """
    if warehouse.company_id != company_id:
        raise DomainError("المستودع لا ينتمي لهذه الشركة", {"warehouse": ["Wrong company."]})

    if not warehouse.is_active:
        raise DomainError("المستودع غير نشط", {"warehouse": ["Inactive warehouse."]})

    if owner_type and warehouse.owner_type != owner_type:
        expected = (
            "مستودع الشركة"
            if owner_type == WarehouseOwnerType.COMPANY
            else "مستودع المندوب"
        )
        raise DomainError(
            f"المستودع المحدد يجب أن يكون {expected}",
            {"warehouse": [f"Expected owner_type={owner_type}."]},
        )

    if rep_id is not None and warehouse.rep_id != rep_id:
        raise DomainError(
            "المستودع لا يخص هذا المندوب",
            {"warehouse": ["Warehouse belongs to another rep."]},
        )

    return warehouse


def default_rep_warehouse(company_id: int, rep_id: int) -> Warehouse:
    """The rep's own warehouse — the default source for sales and destination for
    returns, so field clients don't have to send a warehouse id at all.
    """
    warehouse = (
        Warehouse.objects.filter(
            company_id=company_id,
            rep_id=rep_id,
            owner_type=WarehouseOwnerType.REP,
            is_active=True,
        )
        .order_by("id")
        .first()
    )

    if warehouse is None:
        raise DomainError(
            "لا يوجد مستودع مرتبط بهذا المندوب",
            {"warehouse": ["The rep has no active warehouse."]},
        )

    return warehouse
