"""Stock Transfer state machine (spec §3.2, flow §4.2).

The rule under test throughout: stock moves on `received` and nowhere else.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_rep, generate_tokens_for_subuser
from apps.common.models import AuditLog
from apps.notifications.models import Notification
from apps.orders.models import StockTransferStatus
from apps.orders.services.transfers import (
    approve_transfer,
    cancel_transfer,
    create_stock_transfer,
    dispatch_stock_transfer,
    modify_transfer,
    receive_transfer,
    rep_confirm_transfer,
)
from apps.products.models import StockMovementType, Warehouse, WarehouseOwnerType
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


# ---------------------------------------------------------------------------
# Office-initiated dispatch: goods the rep never asked for.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_dispatch_opens_already_confirmed_and_tells_the_rep(
    company, rep, stocked_company_warehouse, rep_warehouse, product, owner
):
    transfer = dispatch_stock_transfer(
        company_id=company.id,
        rep=rep,
        lines=[(product, Decimal("10"))],
        dispatched_by_id=owner.id,
    )

    # No `pending` hop: the office asked and answered in one act.
    assert transfer.status == StockTransferStatus.CONFIRMED
    assert transfer.number.startswith("TRF-")
    assert transfer.approved_at is not None
    assert transfer.approved_by_id == owner.id
    # Pre-approved, so the quantity is settled the moment the document exists.
    assert transfer.lines.get().approved_qty == Decimal("10.000")
    assert transfer.lines.get().effective_qty == Decimal("10.000")
    assert Notification.objects.filter(
        event_key="stock_transfer.dispatched", recipient_actor_id=rep.id
    ).exists()


@pytest.mark.django_db
def test_dispatch_moves_no_stock_until_the_rep_receives(
    company, rep, stocked_company_warehouse, rep_warehouse, product, owner
):
    """The rule the whole module rests on holds for the office's origin too."""
    transfer = dispatch_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("10"))]
    )

    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("50.000")
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")

    receive_transfer(transfer)
    transfer.refresh_from_db()

    assert transfer.status == StockTransferStatus.RECEIVED
    assert available_quantity(stocked_company_warehouse.id, product.id) == Decimal("40.000")
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("10.000")


@pytest.mark.django_db
def test_a_rep_can_refuse_a_dispatch(
    company, rep, stocked_company_warehouse, rep_warehouse, product
):
    """`confirmed -> cancelled` is already legal, so refusal needs no new path."""
    transfer = dispatch_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("10"))]
    )
    cancel_transfer(transfer, action="rep_rejected")
    transfer.refresh_from_db()

    assert transfer.status == StockTransferStatus.CANCELLED
    with pytest.raises(InvalidTransition):
        receive_transfer(transfer)
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_a_dispatch_cannot_be_approved_again(
    company, rep, stocked_company_warehouse, rep_warehouse, product
):
    """There is no second approval to give — it opened at `confirmed`."""
    transfer = dispatch_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("10"))]
    )
    with pytest.raises(InvalidTransition):
        approve_transfer(transfer)
    with pytest.raises(InvalidTransition):
        modify_transfer(transfer, {transfer.lines.get().id: Decimal("4")})


@pytest.mark.django_db
def test_dispatch_validates_warehouses_and_lines(
    company, rep, other_rep, stocked_company_warehouse, rep_warehouse, product
):
    with pytest.raises(DomainError):
        dispatch_stock_transfer(company_id=company.id, rep=rep, lines=[])

    with pytest.raises(DomainError):
        dispatch_stock_transfer(
            company_id=company.id, rep=rep, lines=[(product, Decimal("0"))]
        )

    # A van belonging to somebody else is not a destination for this rep.
    other_van = Warehouse.objects.create(
        company=company,
        rep=other_rep,
        owner_type=WarehouseOwnerType.REP,
        name="مستودع آخر",
    )
    with pytest.raises(DomainError):
        dispatch_stock_transfer(
            company_id=company.id,
            rep=rep,
            lines=[(product, Decimal("1"))],
            destination_warehouse=other_van,
        )


@pytest.mark.django_db
def test_dispatch_shortfall_leaves_the_document_confirmed(
    company, rep, company_warehouse, rep_warehouse, product, owner
):
    """Availability is still checked at receipt, not at dispatch (§6.1)."""
    transfer = dispatch_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("10"))]
    )

    with pytest.raises(DomainError):
        receive_transfer(transfer)

    transfer.refresh_from_db()
    assert transfer.status == StockTransferStatus.CONFIRMED
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


@pytest.mark.django_db
def test_the_dispatch_origin_is_visible_in_the_audit_trail(
    company, rep, stocked_company_warehouse, rep_warehouse, product, owner
):
    transfer = dispatch_stock_transfer(
        company_id=company.id,
        rep=rep,
        lines=[(product, Decimal("10"))],
        dispatched_by_id=owner.id,
    )
    receive_transfer(transfer)

    actions = list(
        AuditLog.objects.filter(
            entity_type="stock_transfer", entity_id=transfer.id
        ).values_list("action", flat=True)
    )
    # "requested" never appears: nobody requested this one.
    assert actions == ["dispatched", "received"]


# ---------------------------------------------------------------------------
# The dispatch endpoint: POST /api/companies/stock-transfers/
# ---------------------------------------------------------------------------


@pytest.fixture
def owner_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


@pytest.fixture
def rep_client(rep) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    return client


@pytest.mark.django_db
def test_the_office_can_post_goods_to_a_rep(
    owner_client, rep, stocked_company_warehouse, rep_warehouse, product
):
    response = owner_client.post(
        "/api/companies/stock-transfers/",
        {
            "rep": rep.id,
            "lines": [{"product_id": product.id, "quantity": "10"}],
            "notes": "تحميل ليلي",
        },
        format="json",
    )

    assert response.status_code == 201
    transfer = response.json()["data"]["transfer"]
    assert transfer["status"] == "confirmed"
    assert transfer["rep"] == rep.id
    # The warehouses default exactly as they do for a rep's own request.
    assert transfer["destination_warehouse"] == rep_warehouse.id
    assert transfer["source_warehouse"] == stocked_company_warehouse.id
    assert transfer["lines"][0]["approved_qty"] == "10.000"


@pytest.mark.django_db
def test_a_dispatched_transfer_reaches_the_rep_and_they_receive_it(
    owner_client, rep_client, rep, stocked_company_warehouse, rep_warehouse, product
):
    """End to end: the office posts, the rep sees it and takes custody."""
    created = owner_client.post(
        "/api/companies/stock-transfers/",
        {"rep": rep.id, "lines": [{"product_id": product.id, "quantity": "10"}]},
        format="json",
    )
    transfer_id = created.json()["data"]["transfer"]["id"]

    listing = rep_client.get("/api/reps/stock-transfers/?status=confirmed")
    assert [row["id"] for row in listing.json()["data"]["transfers"]] == [transfer_id]

    received = rep_client.post(
        f"/api/reps/stock-transfers/{transfer_id}/receive/", {}, format="json"
    )
    assert received.status_code == 200
    assert received.json()["data"]["transfer"]["status"] == "received"
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("10.000")


@pytest.mark.django_db
def test_a_rep_cannot_dispatch_to_themselves(
    rep_client, rep, stocked_company_warehouse, rep_warehouse, product
):
    """The office origin is the office's. Reps hold no module permissions."""
    response = rep_client.post(
        "/api/companies/stock-transfers/",
        {"rep": rep.id, "lines": [{"product_id": product.id, "quantity": "10"}]},
        format="json",
    )
    assert response.status_code == 403


@pytest.mark.django_db
def test_dispatch_rejects_a_rep_from_another_company(
    owner_client, company, unit, currency, stocked_company_warehouse, product
):
    """A rep id is not a licence to reach across tenants."""
    from apps.companies.models import Company
    from apps.reps.models import Rep

    other_company = Company.objects.create(
        name="Another Co", slug="another-co", currency="SYP"
    )
    outsider = Rep.objects.create(
        company=other_company,
        name="Outsider",
        phone="+963911111111",
        password="x",
        referral_code="REP-OUTSIDER",
    )

    response = owner_client.post(
        "/api/companies/stock-transfers/",
        {"rep": outsider.id, "lines": [{"product_id": product.id, "quantity": "1"}]},
        format="json",
    )
    assert response.status_code == 400
    assert "rep" in response.json()["errors"]
