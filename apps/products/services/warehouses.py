"""Warehouse selection and validation, shared by every document that moves stock.

Lives in `products` because that is where `Warehouse` lives and because all three
callers need the same rules: `invoices` (incoming, sales, returns) and `orders`
(stock transfers). Keeping one copy is what stops "which warehouse?" from being
answered slightly differently per document type.

The guards here are what prevent an incoming invoice filling a rep's van, or one
rep's sale draining another rep's stock.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from apps.products.models import Warehouse, WarehouseOwnerType
from core.domain import DomainError

if TYPE_CHECKING:
    from apps.reps.models import Rep


def require_warehouse(
    warehouse: Warehouse,
    *,
    company_id: int,
    owner_type: str | None = None,
    rep_id: int | None = None,
    field: str = "warehouse",
) -> Warehouse:
    """Validate that a warehouse may be used by this company/rep for a document.

    `field` names the request field in the error payload, so a stock transfer can
    report `source_warehouse` / `destination_warehouse` rather than a generic key.
    """
    if warehouse.company_id != company_id:
        raise DomainError("المستودع لا ينتمي لهذه الشركة", {field: ["Wrong company."]})

    if not warehouse.is_active:
        raise DomainError("المستودع غير نشط", {field: ["Inactive warehouse."]})

    if owner_type and warehouse.owner_type != owner_type:
        expected = (
            "مستودع الشركة"
            if owner_type == WarehouseOwnerType.COMPANY
            else "مستودع المندوب"
        )
        raise DomainError(
            f"المستودع المحدد يجب أن يكون {expected}",
            {field: [f"Expected owner_type={owner_type}."]},
        )

    if rep_id is not None and warehouse.rep_id != rep_id:
        raise DomainError(
            "المستودع لا يخص هذا المندوب",
            {field: ["Warehouse belongs to another rep."]},
        )

    return warehouse


def default_company_warehouse(company_id: int, *, field: str = "warehouse") -> Warehouse:
    """The company's own warehouse — source for transfers and for direct sales."""
    warehouse = (
        Warehouse.objects.filter(
            company_id=company_id,
            owner_type=WarehouseOwnerType.COMPANY,
            is_active=True,
        )
        .order_by("id")
        .first()
    )

    if warehouse is None:
        raise DomainError(
            "لا يوجد مستودع نشط للشركة",
            {field: ["The company has no active warehouse."]},
        )

    return warehouse


def default_rep_warehouse(
    company_id: int, rep_id: int, *, field: str = "warehouse"
) -> Warehouse:
    """The rep's own van — default source for their sales, destination for returns.

    Having a default is what lets field clients post a sale without knowing any
    warehouse ids.
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
            {field: ["The rep has no active warehouse."]},
        )

    return warehouse


def ensure_rep_warehouse(rep: Rep, *, name: str = "") -> Warehouse:
    """Give a rep their van, so their first sale does not fail for want of one.

    Called when a rep is created. Every field document defaults its warehouse to
    `default_rep_warehouse`, so a rep without one cannot sell, take a return, or
    receive a transfer — the company would have to notice and create it by hand.

    Idempotent, and deliberately blunt about what "exists" means: if the rep has
    any warehouse row at all it is returned untouched, inactive included. An
    inactive van was deactivated by an admin on purpose; quietly minting a second
    one would work around that decision rather than honour it.
    """
    existing = (
        Warehouse.objects.filter(
            company_id=rep.company_id,
            rep_id=rep.id,
            owner_type=WarehouseOwnerType.REP,
        )
        .order_by("id")
        .first()
    )
    if existing is not None:
        return existing

    return Warehouse.objects.create(
        company_id=rep.company_id,
        rep=rep,
        owner_type=WarehouseOwnerType.REP,
        name=name or f"مستودع {rep.name}",
    )
