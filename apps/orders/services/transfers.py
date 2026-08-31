"""Stock Transfer service (invoicing spec §3.2, flow §4.2).

    Rep requests quantity              -> pending
    Admin approves as-is               -> confirmed
    Admin modifies quantities          -> modified_by_admin -> pending_rep_confirmation
        rep approves                   -> confirmed
        rep rejects                    -> cancelled
    Rep taps "received"                -> received   <- the only stock movement

The office can also start the document itself, for goods the rep never asked for
— a van loaded overnight, a promotion pushed to the whole team:

    Admin dispatches quantity          -> confirmed
    Rep taps "received"                -> received   <- still the only movement

A dispatch skips `pending` because there is nobody left to approve: the office
both asked and answered. It joins the machine at `confirmed`, so from the rep's
side the two origins are indistinguishable, and `receive` needs no special case.

Confirmation and receipt are deliberately separate. Confirming means the rep
agreed to the quantity; the goods have not left the building. Stock moves only on
`received`, as two ledger rows in one transaction: out of the company warehouse
and into the rep's. That holds for a dispatch too — the office cannot put goods
in a van by decree, because a van's contents are what the rep is accountable for.

This is a transfer record, not an invoice: no tax fields, no totals, no money.
Nothing internal is being sold.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Mapping, Sequence

from django.db import transaction
from django.utils import timezone

from apps.common.models import DocumentType
from apps.common.services.audit import record_audit
from apps.common.services.numbering import next_document_number
from apps.common.modules import STOCK_TRANSFERS
from apps.notifications.services import (
    STOCK_TRANSFER_CANCELLED,
    STOCK_TRANSFER_CONFIRMED,
    STOCK_TRANSFER_DISPATCHED,
    STOCK_TRANSFER_MODIFIED,
    STOCK_TRANSFER_RECEIVED,
    STOCK_TRANSFER_REQUESTED,
    notify_company_admins,
    notify_rep,
)
from apps.orders.models import (
    StockTransfer,
    StockTransferLine,
    StockTransferStatus,
)
from apps.products.models import StockMovementType, Warehouse, WarehouseOwnerType
from apps.products.services.stock import StockChange, apply_stock_changes
from apps.products.services.warehouses import (
    default_company_warehouse,
    default_rep_warehouse,
    require_warehouse,
)
from core.domain import DomainError, InvalidTransition

if TYPE_CHECKING:
    from rest_framework.request import Request

    from apps.products.models import Product
    from apps.reps.models import Rep

ZERO = Decimal("0")


def _transition(
    transfer: StockTransfer,
    *,
    to_status: str,
    action: str,
    request: Request | None,
    changes: dict | None = None,
    **fields,
) -> StockTransfer:
    """Validate one hop of the state machine, apply it, and log it.

    Every status change in this module goes through here, so an illegal hop is
    impossible to write by accident and the audit trail can never be forgotten.
    """
    if not transfer.can_transition_to(to_status):
        raise InvalidTransition(
            "لا يمكن تنفيذ هذا الإجراء على الطلب في حالته الحالية",
            {"status": [f"Cannot move from '{transfer.status}' to '{to_status}'."]},
        )

    previous_status = transfer.status
    transfer.status = to_status
    for field, value in fields.items():
        setattr(transfer, field, value)
    transfer.save(update_fields=["status", *fields, "updated_at"])

    record_audit(
        company_id=transfer.company_id,
        entity=transfer,
        action=action,
        request=request,
        from_status=previous_status,
        to_status=to_status,
        changes=changes or {},
    )
    return transfer


def _open_transfer(
    *,
    company_id: int,
    rep: Rep,
    lines: Sequence[tuple[Product, Decimal]],
    source_warehouse: Warehouse | None,
    destination_warehouse: Warehouse | None,
    notes: str,
    status: str,
    pre_approved: bool,
    approved_by_id: int | None = None,
    pickup_within_hours: int | None = None,
) -> StockTransfer:
    """Write a new transfer and its lines. Shared by the rep and office origins.

    `pre_approved` fills `approved_qty` from the requested quantity at creation:
    true for a dispatch, where the office already decided, and false for a
    request, where the quantity is still a proposal.
    """
    if not lines:
        raise DomainError("لا يمكن إرسال طلب فارغ", {"lines": ["No lines."]})

    if any(quantity <= ZERO for _, quantity in lines):
        raise DomainError(
            "الكميات المطلوبة يجب أن تكون أكبر من صفر",
            {"lines": ["Requested quantities must be positive."]},
        )

    source = source_warehouse or default_company_warehouse(
        company_id, field="source_warehouse"
    )
    destination = destination_warehouse or default_rep_warehouse(
        company_id, rep.id, field="destination_warehouse"
    )

    require_warehouse(
        source,
        company_id=company_id,
        owner_type=WarehouseOwnerType.COMPANY,
        field="source_warehouse",
    )
    require_warehouse(
        destination,
        company_id=company_id,
        owner_type=WarehouseOwnerType.REP,
        rep_id=rep.id,
        field="destination_warehouse",
    )

    now = timezone.now()
    transfer = StockTransfer.objects.create(
        company_id=company_id,
        number=next_document_number(company_id, DocumentType.STOCK_TRANSFER),
        rep=rep,
        source_warehouse=source,
        destination_warehouse=destination,
        status=status,
        requested_at=now,
        approved_at=now if pre_approved else None,
        approved_by_id=approved_by_id,
        pickup_within_hours=pickup_within_hours,
        notes=notes,
    )

    StockTransferLine.objects.bulk_create(
        [
            StockTransferLine(
                company_id=company_id,
                transfer=transfer,
                product=product,
                unit_id=product.unit_id,
                requested_qty=quantity,
                approved_qty=quantity if pre_approved else None,
            )
            for product, quantity in lines
        ]
    )
    return transfer


@transaction.atomic
def create_stock_transfer(
    *,
    company_id: int,
    rep: Rep,
    lines: Sequence[tuple[Product, Decimal]],
    source_warehouse: Warehouse | None = None,
    destination_warehouse: Warehouse | None = None,
    notes: str = "",
    pickup_within_hours: int | None = None,
    request: Request | None = None,
) -> StockTransfer:
    """A rep asks the company for goods. Starts at `pending`; nothing moves yet.

    `pickup_within_hours` is the window the rep promises to collect in. It is
    information for the warehouse keeper — when to have the goods on the dock —
    and nothing in the state machine enforces it: a transfer does not expire.
    """
    transfer = _open_transfer(
        company_id=company_id,
        rep=rep,
        lines=lines,
        source_warehouse=source_warehouse,
        destination_warehouse=destination_warehouse,
        notes=notes,
        status=StockTransferStatus.PENDING,
        pre_approved=False,
        pickup_within_hours=pickup_within_hours,
    )

    notify_company_admins(
        company_id=company_id,
        module=STOCK_TRANSFERS,
        event_key=STOCK_TRANSFER_REQUESTED,
        payload={
            "stock_transfer_id": transfer.id,
            "number": transfer.number,
            "rep_id": rep.id,
            "pickup_within_hours": pickup_within_hours,
        },
    )

    record_audit(
        company_id=company_id,
        entity=transfer,
        action="requested",
        request=request,
        to_status=transfer.status,
        changes={"lines": len(lines)},
    )
    return transfer


@transaction.atomic
def dispatch_stock_transfer(
    *,
    company_id: int,
    rep: Rep,
    lines: Sequence[tuple[Product, Decimal]],
    source_warehouse: Warehouse | None = None,
    destination_warehouse: Warehouse | None = None,
    notes: str = "",
    dispatched_by_id: int | None = None,
    request: Request | None = None,
) -> StockTransfer:
    """The office sends a rep goods they never requested. Starts at `confirmed`.

    The mirror image of `create_stock_transfer`: same document, same ledger, same
    receipt — only the origin differs. It opens at `confirmed` rather than
    `pending` because a dispatch has nothing left to approve; the office asked and
    answered in one act, which is why `approved_by` is the dispatching admin.

    Still no stock movement here. The rep taps `receive` exactly as they would for
    a transfer they raised, and until they do, the goods are the warehouse's. A
    rep who will not carry them can `cancel` from `confirmed` — already a legal
    hop, so refusal needs no special path.
    """
    transfer = _open_transfer(
        company_id=company_id,
        rep=rep,
        lines=lines,
        source_warehouse=source_warehouse,
        destination_warehouse=destination_warehouse,
        notes=notes,
        status=StockTransferStatus.CONFIRMED,
        pre_approved=True,
        approved_by_id=dispatched_by_id,
    )

    notify_rep(
        company_id=company_id,
        rep_id=rep.id,
        event_key=STOCK_TRANSFER_DISPATCHED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )

    record_audit(
        company_id=company_id,
        entity=transfer,
        action="dispatched",
        request=request,
        to_status=transfer.status,
        changes={"lines": len(lines), "dispatched_by_id": dispatched_by_id},
    )
    return transfer


@transaction.atomic
def approve_transfer(
    transfer: StockTransfer,
    *,
    approved_by_id: int | None = None,
    request: Request | None = None,
) -> StockTransfer:
    """Admin approves the requested quantities unchanged: pending -> confirmed."""
    lines = list(transfer.lines.all())
    for line in lines:
        line.approved_qty = line.requested_qty
    StockTransferLine.objects.bulk_update(lines, ["approved_qty"])

    _transition(
        transfer,
        to_status=StockTransferStatus.CONFIRMED,
        action="approved",
        request=request,
        approved_at=timezone.now(),
        approved_by_id=approved_by_id,
        changes={"approved_as_requested": True},
    )

    notify_rep(
        company_id=transfer.company_id,
        rep_id=transfer.rep_id,
        event_key=STOCK_TRANSFER_CONFIRMED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )
    return transfer


@transaction.atomic
def modify_transfer(
    transfer: StockTransfer,
    approved_quantities: Mapping[int, Decimal],
    *,
    approved_by_id: int | None = None,
    request: Request | None = None,
) -> StockTransfer:
    """Admin cuts quantities down: pending -> modified_by_admin -> awaiting the rep.

    The rep now has to accept the new numbers; the transfer parks in
    `pending_rep_confirmation` until they do.
    """
    lines = list(transfer.lines.all())
    known = {line.id for line in lines}
    unknown = [line_id for line_id in approved_quantities if line_id not in known]
    if unknown:
        raise DomainError(
            "بعض البنود لا تنتمي لهذا الطلب",
            {"lines": [f"Unknown transfer lines: {unknown}"]},
        )

    changes: dict[str, list] = {"modified_lines": []}
    for line in lines:
        approved = approved_quantities.get(line.id, line.requested_qty)
        if approved < ZERO:
            raise DomainError(
                "الكمية المعتمدة لا يمكن أن تكون سالبة",
                {"lines": [f"Line {line.id}: approved quantity must be >= 0."]},
            )
        if approved > line.requested_qty:
            raise DomainError(
                "الكمية المعتمدة لا يمكن أن تتجاوز الكمية المطلوبة",
                {"lines": [f"Line {line.id}: approved exceeds requested."]},
            )
        if approved != line.requested_qty:
            changes["modified_lines"].append(
                {
                    "line_id": line.id,
                    "requested": str(line.requested_qty),
                    "approved": str(approved),
                }
            )
        line.approved_qty = approved

    if not changes["modified_lines"]:
        raise DomainError(
            "لم يتم تعديل أي كمية — استخدم الموافقة المباشرة بدلاً من ذلك",
            {"lines": ["Nothing was modified; use approve instead."]},
        )

    StockTransferLine.objects.bulk_update(lines, ["approved_qty"])

    _transition(
        transfer,
        to_status=StockTransferStatus.MODIFIED_BY_ADMIN,
        action="modified",
        request=request,
        approved_at=timezone.now(),
        approved_by_id=approved_by_id,
        changes=changes,
    )
    # The admin's edit is done; the document is now waiting on the rep.
    _transition(
        transfer,
        to_status=StockTransferStatus.PENDING_REP_CONFIRMATION,
        action="awaiting_rep_confirmation",
        request=request,
    )

    notify_rep(
        company_id=transfer.company_id,
        rep_id=transfer.rep_id,
        event_key=STOCK_TRANSFER_MODIFIED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )
    return transfer


@transaction.atomic
def rep_confirm_transfer(
    transfer: StockTransfer, *, request: Request | None = None
) -> StockTransfer:
    """Rep accepts the admin's modified quantities: -> confirmed."""
    _transition(
        transfer,
        to_status=StockTransferStatus.CONFIRMED,
        action="rep_confirmed",
        request=request,
    )

    notify_company_admins(
        company_id=transfer.company_id,
        module=STOCK_TRANSFERS,
        event_key=STOCK_TRANSFER_CONFIRMED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )
    return transfer


@transaction.atomic
def cancel_transfer(
    transfer: StockTransfer,
    *,
    action: str = "cancelled",
    request: Request | None = None,
) -> StockTransfer:
    """Rep rejects, or either side calls the transfer off. Terminal."""
    _transition(
        transfer,
        to_status=StockTransferStatus.CANCELLED,
        action=action,
        request=request,
        cancelled_at=timezone.now(),
    )

    notify_company_admins(
        company_id=transfer.company_id,
        module=STOCK_TRANSFERS,
        event_key=STOCK_TRANSFER_CANCELLED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )
    notify_rep(
        company_id=transfer.company_id,
        rep_id=transfer.rep_id,
        event_key=STOCK_TRANSFER_CANCELLED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )
    return transfer


@transaction.atomic
def receive_transfer(
    transfer: StockTransfer, *, request: Request | None = None
) -> StockTransfer:
    """Rep confirms physical receipt: the only step that moves stock.

    Two ledger rows per product — out of the company warehouse, into the rep's —
    written atomically with the status change.
    """
    lines = list(transfer.lines.select_related("product").all())
    moving = [(line, line.effective_qty) for line in lines]
    moving = [(line, quantity) for line, quantity in moving if quantity > ZERO]

    if not moving:
        raise DomainError(
            "لا توجد كميات معتمدة لاستلامها",
            {"lines": ["Nothing approved to receive."]},
        )

    out_changes = [
        StockChange(product_id=line.product_id, quantity=-quantity)
        for line, quantity in moving
    ]
    in_changes = [
        StockChange(product_id=line.product_id, quantity=quantity)
        for line, quantity in moving
    ]

    apply_stock_changes(
        company_id=transfer.company_id,
        warehouse=transfer.source_warehouse,
        changes=out_changes,
        movement_type=StockMovementType.TRANSFER_OUT,
        source_type=DocumentType.STOCK_TRANSFER,
        source_id=transfer.id,
        source_number=transfer.number,
    )
    apply_stock_changes(
        company_id=transfer.company_id,
        warehouse=transfer.destination_warehouse,
        changes=in_changes,
        movement_type=StockMovementType.TRANSFER_IN,
        source_type=DocumentType.STOCK_TRANSFER,
        source_id=transfer.id,
        source_number=transfer.number,
    )

    _transition(
        transfer,
        to_status=StockTransferStatus.RECEIVED,
        action="received",
        request=request,
        received_at=timezone.now(),
        changes={
            "source_warehouse_id": transfer.source_warehouse_id,
            "destination_warehouse_id": transfer.destination_warehouse_id,
            "lines": len(moving),
        },
    )

    notify_company_admins(
        company_id=transfer.company_id,
        module=STOCK_TRANSFERS,
        event_key=STOCK_TRANSFER_RECEIVED,
        payload={"stock_transfer_id": transfer.id, "number": transfer.number},
    )
    return transfer
