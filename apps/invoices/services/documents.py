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
from apps.products.services.stock import StockChange

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
