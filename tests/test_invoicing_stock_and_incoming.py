"""Stock ledger primitives and the Incoming Invoice flow (spec §3.1, §4.1, §6.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.models import DocumentType
from apps.invoices.models import IncomingInvoiceStatus
from apps.invoices.services.documents import LineInput
from apps.invoices.services.incoming import (
    cancel_incoming_invoice,
    create_incoming_invoice,
    issue_incoming_invoice,
)
from apps.products.models import ProductWarehouseStock, StockMovement, StockMovementType
from apps.products.services.stock import (
    InsufficientStockError,
    StockChange,
    apply_stock_changes,
    available_quantity,
    ledger_balance,
)
from core.domain import DomainError, InvalidTransition


@pytest.mark.django_db
def test_stock_changes_update_projection_and_ledger_together(
    company, company_warehouse, product
):
    apply_stock_changes(
        company_id=company.id,
        warehouse=company_warehouse,
        changes=[StockChange(product_id=product.id, quantity=Decimal("12.5"))],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )

    assert available_quantity(company_warehouse.id, product.id) == Decimal("12.500")
    assert ledger_balance(company_warehouse.id, product.id) == Decimal("12.500")

    movement = StockMovement.objects.get()
    assert movement.quantity == Decimal("12.500")
    assert movement.balance_after == Decimal("12.500")


@pytest.mark.django_db
def test_repeated_product_lines_collapse_into_one_movement(
    company, company_warehouse, product
):
    apply_stock_changes(
        company_id=company.id,
        warehouse=company_warehouse,
        changes=[
            StockChange(product_id=product.id, quantity=Decimal("3")),
            StockChange(product_id=product.id, quantity=Decimal("4")),
        ],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )

    assert StockMovement.objects.count() == 1
    assert available_quantity(company_warehouse.id, product.id) == Decimal("7.000")


@pytest.mark.django_db
def test_outbound_beyond_available_is_refused(company, company_warehouse, product):
    with pytest.raises(InsufficientStockError):
        apply_stock_changes(
            company_id=company.id,
            warehouse=company_warehouse,
            changes=[StockChange(product_id=product.id, quantity=Decimal("-1"))],
            movement_type=StockMovementType.SALE_OUT,
            source_type="manual",
        )

    assert StockMovement.objects.count() == 0
    assert ProductWarehouseStock.objects.filter(quantity__lt=0).count() == 0


@pytest.mark.django_db
def test_incoming_invoice_is_created_as_draft_without_moving_stock(
    company, company_warehouse, product, owner
):
    invoice = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=[
            LineInput(product=product, quantity=Decimal("10"), unit_price=Decimal("7.50"))
        ],
        supplier_ref="Parent co.",
        created_by_id=owner.id,
    )

    assert invoice.status == IncomingInvoiceStatus.DRAFT
    assert invoice.total_amount == Decimal("75.00")
    assert invoice.number.startswith("INV-IN-")
    assert available_quantity(company_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_issuing_an_incoming_invoice_increments_the_company_warehouse(
    company, company_warehouse, product, other_product
):
    invoice = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=[
            LineInput(product=product, quantity=Decimal("10"), unit_price=Decimal("7.50")),
            LineInput(
                product=other_product, quantity=Decimal("4"), unit_price=Decimal("2.25")
            ),
        ],
    )

    issue_incoming_invoice(invoice)
    invoice.refresh_from_db()

    assert invoice.status == IncomingInvoiceStatus.ISSUED
    assert invoice.issued_at is not None
    assert available_quantity(company_warehouse.id, product.id) == Decimal("10.000")
    assert available_quantity(company_warehouse.id, other_product.id) == Decimal("4.000")

    movements = StockMovement.objects.filter(source_id=invoice.id)
    assert movements.count() == 2
    assert {m.source_type for m in movements} == {DocumentType.INCOMING_INVOICE}
    assert {m.source_number for m in movements} == {invoice.number}


@pytest.mark.django_db
def test_incoming_invoice_cannot_be_issued_twice(company, company_warehouse, product):
    invoice = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=[
            LineInput(product=product, quantity=Decimal("5"), unit_price=Decimal("1.00"))
        ],
    )
    issue_incoming_invoice(invoice)

    with pytest.raises(InvalidTransition):
        issue_incoming_invoice(invoice)

    assert available_quantity(company_warehouse.id, product.id) == Decimal("5.000")


@pytest.mark.django_db
def test_issued_incoming_invoice_cannot_be_cancelled(
    company, company_warehouse, product
):
    invoice = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=[
            LineInput(product=product, quantity=Decimal("5"), unit_price=Decimal("1.00"))
        ],
    )
    issue_incoming_invoice(invoice)

    with pytest.raises(InvalidTransition):
        cancel_incoming_invoice(invoice)


@pytest.mark.django_db
def test_incoming_invoice_rejects_a_rep_warehouse(company, rep_warehouse, product):
    """§3.1 receives into a *company* warehouse; a rep's van is not a valid target."""
    with pytest.raises(DomainError):
        create_incoming_invoice(
            company_id=company.id,
            warehouse=rep_warehouse,
            lines=[
                LineInput(
                    product=product, quantity=Decimal("5"), unit_price=Decimal("1.00")
                )
            ],
        )
