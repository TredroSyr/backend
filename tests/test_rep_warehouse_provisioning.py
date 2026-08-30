"""A rep gets their van the moment they are created.

Every field document — sale, return, incoming transfer — defaults its warehouse
to `default_rep_warehouse`, which raises when the rep has none. So a rep created
without a warehouse is not merely incomplete: they cannot sell at all until an
admin notices and creates one by hand. These tests pin that the API closes that
gap, and that it does so without ever minting a second van.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_subuser
from apps.invoices.services.documents import LineInput
from apps.invoices.services.sales import create_sales_invoice
from apps.products.models import (
    StockMovementType,
    Warehouse,
    WarehouseOwnerType,
)
from apps.products.services.stock import StockChange, apply_stock_changes
from apps.products.services.warehouses import (
    default_rep_warehouse,
    ensure_rep_warehouse,
)
from apps.reps.models import Rep


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


def create_rep_over_api(client, **overrides):
    payload = {
        "name": "Kamal",
        "phone": "+963933333333",
        "password": "RepPass123",
        "referral_code": "REP-KAMAL",
        **overrides,
    }
    return client.post("/api/companies/reps/", payload, format="json")


def rep_warehouses(rep: Rep):
    return Warehouse.objects.filter(rep=rep, owner_type=WarehouseOwnerType.REP)


# ---------------------------------------------------------------------------
# The API path
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_creating_a_rep_over_the_api_creates_their_warehouse(admin_client, company):
    response = create_rep_over_api(admin_client)

    assert response.status_code == 201, response.data
    rep = Rep.objects.get(id=response.data["data"]["rep"]["id"])
    warehouse = rep_warehouses(rep).get()

    assert warehouse.company_id == company.id
    assert warehouse.is_active
    assert rep.name in warehouse.name


@pytest.mark.django_db
def test_a_brand_new_rep_can_sell_immediately(
    admin_client, company, customer, product, unit
):
    """The point of the whole change: no manual warehouse step in between."""
    response = create_rep_over_api(admin_client)
    rep = Rep.objects.get(id=response.data["data"]["rep"]["id"])

    apply_stock_changes(
        company_id=company.id,
        warehouse=default_rep_warehouse(company.id, rep.id),
        changes=[StockChange(product_id=product.id, quantity=Decimal("20"))],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )

    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(product=product, quantity=Decimal("3"), unit_price=Decimal("10.00"))
        ],
    )

    assert invoice.total_amount == Decimal("30.00")


@pytest.mark.django_db
def test_a_rejected_rep_leaves_no_orphan_warehouse(admin_client, company, rep):
    """Rep and warehouse share a transaction, so a validation failure after the
    insert cannot leave a van belonging to a rep that was never created.
    """
    before = Warehouse.objects.count()

    response = create_rep_over_api(admin_client, phone=rep.phone)

    assert response.status_code == 400
    assert Warehouse.objects.count() == before


# ---------------------------------------------------------------------------
# ensure_rep_warehouse itself
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_ensure_is_idempotent(company, rep, rep_warehouse):
    assert ensure_rep_warehouse(rep) == rep_warehouse
    assert ensure_rep_warehouse(rep) == rep_warehouse
    assert rep_warehouses(rep).count() == 1


@pytest.mark.django_db
def test_ensure_does_not_replace_a_deactivated_warehouse(company, rep, rep_warehouse):
    """An admin deactivated this van on purpose. Minting a fresh one would route
    around that decision instead of honouring it.
    """
    rep_warehouse.is_active = False
    rep_warehouse.save(update_fields=["is_active"])

    assert ensure_rep_warehouse(rep) == rep_warehouse
    assert rep_warehouses(rep).count() == 1


@pytest.mark.django_db
def test_ensure_ignores_the_company_warehouse(company, rep, company_warehouse):
    """A company store is not a substitute for a van — the rep still needs one."""
    warehouse = ensure_rep_warehouse(rep)

    assert warehouse != company_warehouse
    assert warehouse.owner_type == WarehouseOwnerType.REP
    assert warehouse.rep_id == rep.id


@pytest.mark.django_db
def test_ensure_accepts_an_explicit_name(company, rep):
    assert ensure_rep_warehouse(rep, name="Van 7").name == "Van 7"
