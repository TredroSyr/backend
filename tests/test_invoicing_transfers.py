"""Stock Transfer state machine (spec §3.2, flow §4.2).

The rule under test throughout: stock moves on `received` and nowhere else.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.orders.models import StockTransferStatus
from apps.orders.services.transfers import (
    approve_transfer,
    cancel_transfer,
    create_stock_transfer,
    modify_transfer,
    receive_transfer,
    rep_confirm_transfer,
)
from apps.products.models import StockMovementType
from apps.products.services.stock import (
    StockChange,
    apply_stock_changes,
    available_quantity,
)
from core.domain import DomainError, InvalidTransition


@pytest.fixture
def stocked_company_warehouse(company, company_warehouse, product, other_product):
    apply_stock_changes(
        company_id=company.id,
        warehouse=company_warehouse,
        changes=[
            StockChange(product_id=product.id, quantity=Decimal("50")),
            StockChange(product_id=other_product.id, quantity=Decimal("50")),
        ],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    return company_warehouse


@pytest.fixture
def transfer(company, rep, stocked_company_warehouse, rep_warehouse, product):
    return create_stock_transfer(
        company_id=company.id,
        rep=rep,
        lines=[(product, Decimal("10"))],
    )


@pytest.mark.django_db
def test_new_transfer_starts_pending_and_notifies_the_office(
    company, rep, stocked_company_warehouse, rep_warehouse, product, owner
):
    transfer = create_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("10"))]
    )

    assert transfer.status == StockTransferStatus.PENDING
    assert transfer.number.startswith("TRF-")
    assert transfer.source_warehouse_id == stocked_company_warehouse.id
    assert transfer.destination_warehouse_id == rep_warehouse.id
    assert transfer.lines.get().approved_qty is None
    assert Notification.objects.filter(
        event_key="stock_transfer.requested", recipient_actor_id=owner.id
    ).exists()


@pytest.mark.django_db
def test_approval_confirms_without_moving_stock(
    transfer, stocked_company_warehouse, rep_warehouse, product
):
    approve_transfer(transfer)
    transfer.refresh_from_db()

    assert transfer.status == StockTransferStatus.CONFIRMED
    assert transfer.lines.get().approved_qty == Decimal("10.000")
    # Confirmation only means the rep agreed to the quantity.
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("50.000")
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_receipt_moves_stock_between_the_two_warehouses(
    transfer, stocked_company_warehouse, rep_warehouse, product
):
    approve_transfer(transfer)
    receive_transfer(transfer)
    transfer.refresh_from_db()

    assert transfer.status == StockTransferStatus.RECEIVED
    assert transfer.received_at is not None
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("40.000")
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("10.000")


@pytest.mark.django_db
def test_receipt_is_refused_before_confirmation(transfer):
    with pytest.raises(InvalidTransition):
        receive_transfer(transfer)


@pytest.mark.django_db
def test_modification_parks_the_transfer_on_the_rep(transfer, rep):
    line = transfer.lines.get()
    modify_transfer(transfer, {line.id: Decimal("4")})
    transfer.refresh_from_db()

    assert transfer.status == StockTransferStatus.PENDING_REP_CONFIRMATION
    assert transfer.lines.get().approved_qty == Decimal("4.000")
    assert Notification.objects.filter(
        event_key="stock_transfer.modified", recipient_actor_id=rep.id
    ).exists()


@pytest.mark.django_db
def test_rep_confirms_modified_quantities_and_only_those_move(
    transfer, stocked_company_warehouse, rep_warehouse, product
):
    line = transfer.lines.get()
    modify_transfer(transfer, {line.id: Decimal("4")})
    rep_confirm_transfer(transfer)
    receive_transfer(transfer)

    assert available_quantity(rep_warehouse.id, product.id) == Decimal("4.000")
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("46.000")


@pytest.mark.django_db
def test_rep_rejection_is_terminal(transfer, rep_warehouse, product):
    line = transfer.lines.get()
    modify_transfer(transfer, {line.id: Decimal("4")})
    cancel_transfer(transfer, action="rep_rejected")
    transfer.refresh_from_db()

    assert transfer.status == StockTransferStatus.CANCELLED
    with pytest.raises(InvalidTransition):
        receive_transfer(transfer)
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_approved_quantity_cannot_exceed_the_requested_one(transfer):
    line = transfer.lines.get()
    with pytest.raises(DomainError):
        modify_transfer(transfer, {line.id: Decimal("999")})


@pytest.mark.django_db
def test_modify_without_a_change_points_at_approve_instead(transfer):
    line = transfer.lines.get()
    with pytest.raises(DomainError):
        modify_transfer(transfer, {line.id: line.requested_qty})


@pytest.mark.django_db
def test_receipt_is_refused_when_the_company_warehouse_is_short(
    company, rep, company_warehouse, rep_warehouse, product
):
    """Atomicity: a failed stock move leaves the transfer un-received (§6.1)."""
    transfer = create_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("10"))]
    )
    approve_transfer(transfer)

    with pytest.raises(DomainError):
        receive_transfer(transfer)

    transfer.refresh_from_db()
    assert transfer.status == StockTransferStatus.CONFIRMED
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_every_transition_is_recorded_in_the_audit_trail(transfer):
    approve_transfer(transfer)
    receive_transfer(transfer)

    actions = list(
        AuditLog.objects.filter(
            entity_type="stock_transfer", entity_id=transfer.id
        ).values_list("action", flat=True)
    )
    assert actions == ["requested", "approved", "received"]
