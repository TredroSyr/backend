"""Return Invoice / Credit Note service (invoicing spec §3.5, flow §4.4).

A return is a credit note *against* an existing sale, never a standalone
document — the same pattern SAP, QuickBooks, Zoho and Odoo use. On issue it:

1. adds the goods back to whichever warehouse they physically landed in (the
   rep's van by default; an admin can route defective stock to the company
   warehouse instead — it is a field, not a hardcoded rule);
2. recomputes the parent invoice's `returned_amount`, `balance_due` and `status`
   from the *full* set of its returns, since one sale can accumulate several
   over successive visits;
3. resolves any overage, where returns plus payments now exceed the invoice
   total. The balance floors at zero and both resolution paths are implemented:

   * `cash_refunded_by_rep` — the rep handed cash back. No new document; the
     overage is deducted from the rep's expected cash-in at their next
     reconciliation (`RepCashAdjustment`).
   * `deferred_customer_credit` — nothing changed hands; a `PendingCustomerCredit`
     row is created and applied manually against a future sale.

Overage is measured as the *increment* this return creates, not the invoice's
cumulative excess. On a second return against an already-overpaid invoice the
cumulative figure would re-refund money the first return already gave back.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.common.models import DocumentType
from apps.common.services.audit import record_audit
from apps.common.services.numbering import next_document_number
from apps.invoices.models import (
    MONEY_ZERO,
    RefundMethod,
    RepCashAdjustment,
    ReturnInvoice,
    ReturnInvoiceLine,
    ReturnInvoiceStatus,
    SalesInvoiceLine,
)
from apps.invoices.services.balances import (
    lock_sales_invoice,
    overage_for,
    paid_total,
    recompute_sales_invoice,
    returned_total,
)
from apps.invoices.services.credits import create_credit_from_return
from apps.invoices.services.documents import (
    LineInput,
    default_rep_warehouse,
    get_invoice_settings,
    persist_lines,
    require_warehouse,
    stock_changes,
)
from apps.products.models import StockMovementType
from apps.products.services.stock import apply_stock_changes
from core.domain import DomainError, InvalidTransition

if TYPE_CHECKING:
    from datetime import datetime

    from rest_framework.request import Request

    from apps.invoices.models import SalesInvoice
    from apps.products.models import Warehouse

CASH_REFUND_REASON = "return_overage_cash_refund"


def returned_quantity_by_line(
    sales_invoice_id: int, *, exclude_return_id: int | None = None
) -> dict[int, Decimal]:
    """How much of each sold line has already been credited by issued returns.

    `exclude_return_id` leaves one return out of the tally, so a draft can be
    re-checked against everything *other* than itself at issue time.
    """
    rows = ReturnInvoiceLine.objects.filter(
        return_invoice__sales_invoice_id=sales_invoice_id,
        return_invoice__status=ReturnInvoiceStatus.ISSUED,
    )
    if exclude_return_id is not None:
        rows = rows.exclude(return_invoice_id=exclude_return_id)

    return {
        row["sales_invoice_line_id"]: row["total"]
        for row in rows.values("sales_invoice_line_id").annotate(total=Sum("quantity"))
    }


def build_return_lines(
    sales_invoice: SalesInvoice, requested: Sequence[tuple[int, Decimal]]
) -> list[LineInput]:
    """Resolve `(sales_invoice_line_id, quantity)` pairs into priced return lines.

    Unit price is copied from the original sold line rather than re-entered
    (§3.5 schema), and the already-returned quantity caps what is still
    creditable — a customer cannot return more than they bought.
    """
    sold_lines = {
        line.id: line
        for line in SalesInvoiceLine.objects.select_related("product").filter(
            invoice=sales_invoice
        )
    }
    already_returned = returned_quantity_by_line(sales_invoice.id)

    lines: list[LineInput] = []
    for line_id, quantity in requested:
        sold = sold_lines.get(line_id)
        if sold is None:
            raise DomainError(
                "أحد البنود لا ينتمي إلى الفاتورة الأصلية",
                {"lines": [f"Sales invoice line {line_id} is not on this invoice."]},
            )

        if quantity <= MONEY_ZERO:
            raise DomainError(
                "كمية الإرجاع يجب أن تكون أكبر من صفر",
                {"lines": [f"Line {line_id}: quantity must be positive."]},
            )

        remaining = sold.quantity - already_returned.get(line_id, MONEY_ZERO)
        if quantity > remaining:
            raise DomainError(
                f"كمية الإرجاع تتجاوز الكمية المتبقية للمنتج: {sold.product.name}",
                {
                    "lines": [f"Line {line_id}: only {remaining} remain returnable."],
                },
            )

        lines.append(
            LineInput(
                product=sold.product,
                quantity=quantity,
                unit_price=sold.unit_price,
                tax_rate=sold.tax_rate,
                extra={"sales_invoice_line": sold},
            )
        )

    return lines


@transaction.atomic
def create_return_invoice(
    *,
    company_id: int,
    sales_invoice: SalesInvoice,
    requested_lines: Sequence[tuple[int, Decimal]],
    rep_id: int | None = None,
    warehouse: Warehouse | None = None,
    date: datetime | None = None,
    notes: str = "",
    refund_method: str = "",
    request: Request | None = None,
) -> ReturnInvoice:
    """Create the credit note as a draft. Nothing moves until it is issued.

    `rep_id` defaults to the rep who made the sale; `warehouse` to that rep's own
    warehouse, which an admin can override to pull defective goods out of
    circulation.
    """
    if not requested_lines:
        raise DomainError("لا يمكن إنشاء إرجاع بدون بنود", {"lines": ["No lines."]})

    rep_id = rep_id or sales_invoice.rep_id
    warehouse = warehouse or default_rep_warehouse(company_id, rep_id)
    require_warehouse(warehouse, company_id=company_id)

    lines = build_return_lines(sales_invoice, requested_lines)
    settings = get_invoice_settings(company_id)

    return_invoice = ReturnInvoice.objects.create(
        company_id=company_id,
        number=next_document_number(company_id, DocumentType.RETURN_INVOICE),
        date=date or timezone.now(),
        sales_invoice=sales_invoice,
        rep_id=rep_id,
        warehouse=warehouse,
        notes=notes,
        refund_method=refund_method,
        **settings.as_snapshot(),
    )

    return_invoice.amount = persist_lines(
        ReturnInvoiceLine,
        company_id=company_id,
        parent_field="return_invoice",
        parent=return_invoice,
        inputs=lines,
    )
    return_invoice.save(update_fields=["amount", "updated_at"])

    record_audit(
        company_id=company_id,
        entity=return_invoice,
        action="created",
        request=request,
        to_status=return_invoice.status,
        changes={
            "sales_invoice": sales_invoice.number,
            "amount": str(return_invoice.amount),
            "lines": len(lines),
        },
    )
    return return_invoice


def _assert_still_returnable(
    return_invoice: ReturnInvoice, lines: Sequence[ReturnInvoiceLine]
) -> None:
    """Re-check the returnable cap at issue time, not just at draft time.

    Two drafts raised against the same sold line can each look fine on their own
    and together exceed what was sold. The parent invoice is already locked by
    the caller, so whichever is issued second fails here rather than crediting
    goods the customer never bought.
    """
    already_returned = returned_quantity_by_line(
        return_invoice.sales_invoice_id, exclude_return_id=return_invoice.id
    )
    sold_lines = {
        line.id: line
        for line in SalesInvoiceLine.objects.filter(
            invoice_id=return_invoice.sales_invoice_id
        )
    }

    for line in lines:
        sold = sold_lines[line.sales_invoice_line_id]
        remaining = sold.quantity - already_returned.get(
            line.sales_invoice_line_id, MONEY_ZERO
        )
        if line.quantity > remaining:
            raise DomainError(
                f"كمية الإرجاع تتجاوز الكمية المتبقية للمنتج: {line.product.name}",
                {
                    "lines": [
                        f"Line {line.sales_invoice_line_id}: only {remaining} "
                        "remain returnable; another return was issued first."
                    ]
                },
            )


def projected_overage(return_invoice: ReturnInvoice) -> Decimal:
    """Overage this draft return would create if issued right now.

    The increment between the invoice's overage before and after this return, so
    stacked returns each only account for the money they personally push over.
    """
    sales_invoice = return_invoice.sales_invoice
    paid = paid_total(sales_invoice.id)
    returned_before = returned_total(sales_invoice.id)

    before = overage_for(
        total=sales_invoice.total_amount, paid=paid, returned=returned_before
    )
    after = overage_for(
        total=sales_invoice.total_amount,
        paid=paid,
        returned=returned_before + return_invoice.amount,
    )
    return after - before


@transaction.atomic
def issue_return_invoice(
    return_invoice: ReturnInvoice, *, request: Request | None = None
) -> ReturnInvoice:
    """Draft -> issued: move the goods, recompute the sale, resolve any overage."""
    if return_invoice.status != ReturnInvoiceStatus.DRAFT:
        raise InvalidTransition(
            "لا يمكن ترحيل هذا الإرجاع إلا وهو مسودة",
            {"status": [f"Cannot issue a return in status '{return_invoice.status}'."]},
        )

    # Lock the parent first: a concurrent payment on the same sale would
    # otherwise change the numbers between the overage check and the recompute.
    sales_invoice = lock_sales_invoice(
        return_invoice.sales_invoice_id, return_invoice.company_id
    )
    return_invoice.sales_invoice = sales_invoice

    lines = list(return_invoice.lines.select_related("product").all())
    if not lines:
        raise DomainError("لا يمكن ترحيل إرجاع بدون بنود", {"lines": ["No lines."]})

    _assert_still_returnable(return_invoice, lines)

    overage = projected_overage(return_invoice)
    if overage > MONEY_ZERO and not return_invoice.refund_method:
        raise DomainError(
            "يجب تحديد طريقة رد المبلغ الزائد قبل ترحيل الإرجاع",
            {
                "refund_method": ["Required when the return creates an overage."],
                "overage_amount": [str(overage)],
            },
        )

    apply_stock_changes(
        company_id=return_invoice.company_id,
        warehouse=return_invoice.warehouse,
        changes=stock_changes(lines, outbound=False),
        movement_type=StockMovementType.RETURN_IN,
        source_type=DocumentType.RETURN_INVOICE,
        source_id=return_invoice.id,
        source_number=return_invoice.number,
    )

    previous_status = return_invoice.status
    return_invoice.status = ReturnInvoiceStatus.ISSUED
    return_invoice.issued_at = timezone.now()
    return_invoice.overage_amount = overage
    for field, value in get_invoice_settings(return_invoice.company_id).as_snapshot().items():
        setattr(return_invoice, field, value)
    return_invoice.save(
        update_fields=[
            "status",
            "issued_at",
            "overage_amount",
            "company_name",
            "tax_registration_no",
            "updated_at",
        ]
    )

    recompute_sales_invoice(sales_invoice)

    if overage > MONEY_ZERO:
        _resolve_overage(return_invoice, overage, request=request)

    record_audit(
        company_id=return_invoice.company_id,
        entity=return_invoice,
        action="issued",
        request=request,
        from_status=previous_status,
        to_status=return_invoice.status,
        changes={
            "amount": str(return_invoice.amount),
            "overage_amount": str(overage),
            "refund_method": return_invoice.refund_method,
            "warehouse_id": return_invoice.warehouse_id,
            "sales_invoice_balance_due": str(sales_invoice.balance_due),
        },
    )
    return return_invoice


def _resolve_overage(
    return_invoice: ReturnInvoice, overage: Decimal, *, request: Request | None
) -> None:
    """Route the overage down whichever path the rep chose (§3.5 rule 3).

    Either way the sale itself is already closed at `balance_due = 0` — the money
    owed now lives on the rep's cash position or on a customer credit, not on the
    invoice.
    """
    if return_invoice.refund_method == RefundMethod.CASH_REFUNDED_BY_REP:
        RepCashAdjustment.objects.create(
            company_id=return_invoice.company_id,
            rep_id=return_invoice.rep_id,
            amount=-overage,
            reason=CASH_REFUND_REASON,
            return_invoice=return_invoice,
            note=f"Cash refunded to the customer against {return_invoice.number}",
        )
        return

    if return_invoice.refund_method == RefundMethod.DEFERRED_CUSTOMER_CREDIT:
        create_credit_from_return(return_invoice, amount=overage, request=request)
        return

    raise DomainError(
        "طريقة رد المبلغ الزائد غير صالحة",
        {"refund_method": [f"Unsupported refund method '{return_invoice.refund_method}'."]},
    )
