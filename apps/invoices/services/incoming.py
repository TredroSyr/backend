"""Incoming Invoice service (invoicing spec §3.1, flow §4.1).

    Supplier / parent company -> Incoming Invoice (formal, tax fields)
                              -> + Company warehouse

Stock lands on the draft -> issued transition and nowhere else, in one atomic
transaction with the status change: the financial record and the warehouse
increment succeed or fail together (§6.1).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from django.db import transaction
from django.utils import timezone

from apps.common.models import DocumentType
from apps.common.services.audit import record_audit
from apps.common.services.numbering import next_document_number
from apps.invoices.models import (
    IncomingInvoice,
    IncomingInvoiceLine,
    IncomingInvoiceStatus,
)
from apps.invoices.services.documents import (
    LineInput,
    get_invoice_settings,
    persist_lines,
    stock_changes,
)
from apps.products.models import StockMovementType, WarehouseOwnerType
from apps.products.services.stock import apply_stock_changes
from apps.products.services.warehouses import require_warehouse
from core.domain import DomainError, InvalidTransition

if TYPE_CHECKING:
    from datetime import datetime

    from rest_framework.request import Request

    from apps.products.models import Warehouse


@transaction.atomic
def create_incoming_invoice(
    *,
    company_id: int,
    warehouse: Warehouse,
    lines: Sequence[LineInput],
    date: datetime | None = None,
    supplier_ref: str = "",
    notes: str = "",
    created_by_id: int | None = None,
    request: Request | None = None,
) -> IncomingInvoice:
    """Create the invoice as a draft. No stock moves yet."""
    require_warehouse(
        warehouse, company_id=company_id, owner_type=WarehouseOwnerType.COMPANY
    )

    settings = get_invoice_settings(company_id)
    invoice = IncomingInvoice.objects.create(
        company_id=company_id,
        number=next_document_number(company_id, DocumentType.INCOMING_INVOICE),
        date=date or timezone.now(),
        supplier_ref=supplier_ref,
        warehouse=warehouse,
        notes=notes,
        created_by_id=created_by_id,
        currency=settings.company.currency,
        **settings.as_snapshot(),
    )

    invoice.total_amount = persist_lines(
        IncomingInvoiceLine,
        company_id=company_id,
        parent_field="invoice",
        parent=invoice,
        inputs=lines,
    )
    invoice.save(update_fields=["total_amount", "updated_at"])

    record_audit(
        company_id=company_id,
        entity=invoice,
        action="created",
        request=request,
        to_status=invoice.status,
        changes={"total_amount": str(invoice.total_amount), "lines": len(lines)},
    )
    return invoice


@transaction.atomic
def issue_incoming_invoice(
    invoice: IncomingInvoice, *, request: Request | None = None
) -> IncomingInvoice:
    """Draft -> issued: increment the company warehouse for every line."""
    if invoice.status != IncomingInvoiceStatus.DRAFT:
        raise InvalidTransition(
            "لا يمكن ترحيل هذه الفاتورة إلا وهي مسودة",
            {"status": [f"Cannot issue an invoice in status '{invoice.status}'."]},
        )

    lines = list(invoice.lines.select_related("product").all())
    if not lines:
        raise DomainError("لا يمكن ترحيل فاتورة بدون بنود", {"lines": ["No lines."]})

    apply_stock_changes(
        company_id=invoice.company_id,
        warehouse=invoice.warehouse,
        changes=stock_changes(lines, outbound=False),
        movement_type=StockMovementType.INCOMING,
        source_type=DocumentType.INCOMING_INVOICE,
        source_id=invoice.id,
        source_number=invoice.number,
    )

    previous_status = invoice.status
    invoice.status = IncomingInvoiceStatus.ISSUED
    invoice.issued_at = timezone.now()
    # Re-snapshot the header: the settings may have been filled in since the draft.
    for field, value in get_invoice_settings(invoice.company_id).as_snapshot().items():
        setattr(invoice, field, value)
    invoice.save(
        update_fields=[
            "status",
            "issued_at",
            "company_name",
            "tax_registration_no",
            "updated_at",
        ]
    )

    record_audit(
        company_id=invoice.company_id,
        entity=invoice,
        action="issued",
        request=request,
        from_status=previous_status,
        to_status=invoice.status,
        changes={"warehouse_id": invoice.warehouse_id, "lines": len(lines)},
    )
    return invoice


@transaction.atomic
def cancel_incoming_invoice(
    invoice: IncomingInvoice, *, request: Request | None = None
) -> IncomingInvoice:
    """Cancel a draft.

    Issued invoices are not cancellable: their stock is already in the warehouse
    and may have been sold on. Reversing that is a correcting document, which the
    spec does not define for incoming stock — so this refuses rather than
    silently unwinding a warehouse.
    """
    if invoice.status != IncomingInvoiceStatus.DRAFT:
        raise InvalidTransition(
            "لا يمكن إلغاء فاتورة مُرحّلة",
            {"status": ["Only draft incoming invoices can be cancelled."]},
        )

    previous_status = invoice.status
    invoice.status = IncomingInvoiceStatus.CANCELLED
    invoice.cancelled_at = timezone.now()
    invoice.save(update_fields=["status", "cancelled_at", "updated_at"])

    record_audit(
        company_id=invoice.company_id,
        entity=invoice,
        action="cancelled",
        request=request,
        from_status=previous_status,
        to_status=invoice.status,
    )
    return invoice
