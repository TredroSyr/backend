"""Sales Invoice service (invoicing spec §3.4, flow §4.3).

    Customer creates a Customer Request (a signal, not a sale)
      -> Rep visits in person
      -> Rep creates the Sales Invoice   <- this module
           -> - Rep warehouse (per line)
           -> optionally resolves the request
      -> Rep records a Payment Collection (full, partial, or none)
      -> Status derived: fully_paid | partially_paid | deferred

Everything below happens in one transaction: the invoice, its lines, the stock
deduction, any credits applied and any cash collected on the spot commit
together or not at all (§6.1). A rep on a flaky connection can safely retry the
call — see `common.services.idempotency`.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from django.db import transaction
from django.utils import timezone

from apps.common.models import DocumentType
from apps.common.services.audit import record_audit
from apps.common.services.numbering import next_document_number
from apps.invoices.models import SalesInvoice, SalesInvoiceLine
from apps.invoices.services.balances import recompute_sales_invoice
from apps.invoices.services.credits import apply_credits, lock_credits
from apps.invoices.services.documents import (
    LineInput,
    get_invoice_settings,
    persist_lines,
    stock_changes,
)
from apps.invoices.services.payments import add_payment
from apps.orders.services.requests import fulfil_requests
from apps.products.models import StockMovementType, WarehouseOwnerType
from apps.products.services.stock import apply_stock_changes
from apps.products.services.warehouses import (
    default_company_warehouse,
    default_rep_warehouse,
    require_warehouse,
)
from core.domain import DomainError

if TYPE_CHECKING:
    from datetime import datetime

    from rest_framework.request import Request

    from apps.customers.models import Customer
    from apps.products.models import Warehouse
    from apps.reps.models import Rep


@transaction.atomic
def create_sales_invoice(
    *,
    company_id: int,
    customer: Customer,
    lines: Sequence[LineInput],
    rep: Rep | None = None,
    warehouse: Warehouse | None = None,
    date: datetime | None = None,
    notes: str = "",
    credit_ids: Sequence[int] = (),
    payment_amount: Decimal | None = None,
    payment_collected_at: datetime | None = None,
    fulfils_request_ids: Sequence[int] = (),
    currency: str = "",
    request: Request | None = None,
) -> SalesInvoice:
    """Write the sale, deduct the goods, and settle whatever was paid on the spot.

    Two shapes of sale, distinguished only by whether `rep` is given:

    * **Field sale** (`rep` set) — the spec's normal case. Goods leave that rep's
      own van, and cash collected counts toward their settlement.
    * **Company-direct sale** (`rep` omitted) — a customer buying from the company
      itself, with no rep involved. Goods leave a company warehouse and the money
      is company cash, so it stays out of every rep's reconciliation.

    Either way `warehouse` defaults sensibly, so no client needs to know warehouse
    ids. `credit_ids` and `payment_amount` are optional: an invoice with neither is
    simply `deferred`, which is a supported outcome, not an error. There is no
    credit limit (§1).

    `currency` is the code the sale is priced in, defaulting to the company's. It
    is pinned onto the invoice and never re-read, so a later change to
    `Company.currency` cannot re-denominate lines that were already priced.
    """
    if not lines:
        raise DomainError("لا يمكن إنشاء فاتورة بدون بنود", {"lines": ["No lines."]})

    if rep is not None:
        warehouse = warehouse or default_rep_warehouse(company_id, rep.id)
        require_warehouse(
            warehouse,
            company_id=company_id,
            owner_type=WarehouseOwnerType.REP,
            rep_id=rep.id,
        )
    else:
        warehouse = warehouse or default_company_warehouse(company_id)
        require_warehouse(
            warehouse,
            company_id=company_id,
            owner_type=WarehouseOwnerType.COMPANY,
        )

    settings = get_invoice_settings(company_id)
    invoice = SalesInvoice.objects.create(
        company_id=company_id,
        number=next_document_number(company_id, DocumentType.SALES_INVOICE),
        date=date or timezone.now(),
        rep=rep,
        customer=customer,
        warehouse=warehouse,
        notes=notes,
        currency=currency or settings.company.currency,
        **settings.as_snapshot(),
    )

    invoice.total_amount = persist_lines(
        SalesInvoiceLine,
        company_id=company_id,
        parent_field="invoice",
        parent=invoice,
        inputs=lines,
    )
    # balance_due starts at the full total: nothing is paid until a collection or
    # a credit says otherwise (§3.4 rule).
    invoice.balance_due = invoice.total_amount
    invoice.save(update_fields=["total_amount", "balance_due", "updated_at"])

    apply_stock_changes(
        company_id=company_id,
        warehouse=warehouse,
        changes=stock_changes(lines, outbound=True),
        movement_type=StockMovementType.SALE_OUT,
        source_type=DocumentType.SALES_INVOICE,
        source_id=invoice.id,
        source_number=invoice.number,
    )

    if credit_ids:
        apply_credits(
            invoice,
            lock_credits(company_id, customer.id, credit_ids),
            request=request,
        )

    if payment_amount:
        add_payment(
            invoice,
            amount=payment_amount,
            # Null on a direct sale: the money went into the company till, not a
            # rep's float, so it must not appear in anyone's cash settlement.
            collected_by_id=rep.id if rep is not None else None,
            collected_at=payment_collected_at or invoice.date,
            request=request,
        )

    recompute_sales_invoice(invoice)

    fulfilled = fulfil_requests(
        company_id=company_id,
        request_ids=fulfils_request_ids,
        invoice=invoice,
        customer_id=customer.id,
        request=request,
    )

    record_audit(
        company_id=company_id,
        entity=invoice,
        action="created",
        request=request,
        to_status=invoice.status,
        changes={
            "total_amount": str(invoice.total_amount),
            "balance_due": str(invoice.balance_due),
            "lines": len(lines),
            "warehouse_id": warehouse.id,
            "fulfilled_requests": fulfilled,
        },
    )
    return invoice
