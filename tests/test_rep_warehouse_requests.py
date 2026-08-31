"""The rep app's warehouse-requests screen (طلباتي).

The rep asks the company warehouse for goods, promises a pickup window, and later
confirms receipt. Two things are pinned here beyond the existing state machine:
the pickup window is information and never a rule — a transfer does not expire —
and the money on these cards is the shelf value of the goods, not a charge. A
transfer moves stock between two warehouses of one company; nobody is billed.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_rep
from apps.orders.models import StockTransfer, StockTransferStatus
from apps.orders.services.transfers import (
    approve_transfer,
    create_stock_transfer,
    receive_transfer,
)
from apps.products.services.stock import available_quantity


def client_for(rep) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    return client


def stocked_company_warehouse(company, warehouse, *products, quantity="100"):
    from apps.products.models import StockMovementType
    from apps.products.services.stock import StockChange, apply_stock_changes

    apply_stock_changes(
        company_id=company.id,
        warehouse=warehouse,
        changes=[
            StockChange(product_id=product.id, quantity=Decimal(quantity))
            for product in products
        ],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    return warehouse


# ---------------------------------------------------------------------------
# Sending a request
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_rep_sends_a_request_with_a_pickup_window(
    company, rep, rep_warehouse, company_warehouse, product, other_product, currency
):
    response = client_for(rep).post(
        "/api/reps/stock-transfers/",
        {
            "lines": [
                {"product_id": product.id, "quantity": "24"},
                {"product_id": other_product.id, "quantity": "40"},
            ],
            "pickup_within_hours": 3,
        },
        format="json",
    )
    transfer = response.json()["data"]["transfer"]

    assert response.status_code == 201
    assert transfer["status"] == "pending"
    assert transfer["pickup_within_hours"] == 3
    assert transfer["line_count"] == 2

    # "مهلة الاستلام 3 ساعة · حتى 14:30" — the deadline is requested_at + window.
    row = StockTransfer.objects.get(id=transfer["id"])
    assert row.pickup_deadline == row.requested_at + timedelta(hours=3)


@pytest.mark.django_db
def test_the_pickup_window_is_optional(
    company, rep, rep_warehouse, company_warehouse, product
):
    response = client_for(rep).post(
        "/api/reps/stock-transfers/",
        {"lines": [{"product_id": product.id, "quantity": "5"}]},
        format="json",
    )
    transfer = response.json()["data"]["transfer"]

    assert response.status_code == 201
    assert transfer["pickup_within_hours"] is None
    assert transfer["pickup_deadline"] is None


@pytest.mark.django_db
def test_an_absurd_pickup_window_is_rejected(
    company, rep, rep_warehouse, company_warehouse, product
):
    client = client_for(rep)
    body = {"lines": [{"product_id": product.id, "quantity": "5"}]}

    assert (
        client.post(
            "/api/reps/stock-transfers/", {**body, "pickup_within_hours": 0},
            format="json",
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/reps/stock-transfers/", {**body, "pickup_within_hours": 200},
            format="json",
        ).status_code
        == 400
    )


@pytest.mark.django_db
def test_sending_a_request_moves_no_stock(
    company, rep, rep_warehouse, company_warehouse, product
):
    """Nothing moves until the rep taps "received" — not on request, not on approval."""
    stocked_company_warehouse(company, company_warehouse, product)
    before = available_quantity(company_warehouse.id, product.id)

    client_for(rep).post(
        "/api/reps/stock-transfers/",
        {"lines": [{"product_id": product.id, "quantity": "10"}], "pickup_within_hours": 2},
        format="json",
    )

    assert available_quantity(company_warehouse.id, product.id) == before
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("0")


# ---------------------------------------------------------------------------
# The history cards
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_history_card_shows_its_lines_priced_and_totalled(
    company, rep, rep_warehouse, company_warehouse, product, other_product, currency
):
    create_stock_transfer(
        company_id=company.id,
        rep=rep,
        lines=[(product, Decimal("24")), (other_product, Decimal("40"))],
        pickup_within_hours=3,
    )

    card = client_for(rep).get("/api/reps/stock-transfers/").json()["data"]["transfers"][0]

    assert card["pickup_within_hours"] == 3
    assert card["pickup_deadline"] is not None
    # 24 x 10.00 + 40 x 5.00
    assert card["estimated_total"] == "440.00"

    by_name = {line["product_name"]: line for line in card["lines"]}
    assert by_name["Rice 1kg"]["unit_price"] == "10.00"
    assert by_name["Rice 1kg"]["line_total"] == "240.00"
    assert by_name["Sugar 1kg"]["line_total"] == "200.00"


@pytest.mark.django_db
def test_a_trimmed_line_is_valued_at_what_the_rep_actually_gets(
    company, rep, owner, rep_warehouse, company_warehouse, product, currency
):
    """An admin cutting 24 down to 10 must drop the card's total with it."""
    transfer = create_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("24"))]
    )
    from apps.orders.services.transfers import modify_transfer

    # Keyed by line id, not product id.
    modify_transfer(
        transfer, {transfer.lines.get().id: Decimal("10")}, approved_by_id=owner.id
    )

    card = client_for(rep).get("/api/reps/stock-transfers/").json()["data"]["transfers"][0]

    assert card["lines"][0]["requested_qty"] == "24.000"
    assert card["lines"][0]["approved_qty"] == "10.000"
    assert card["lines"][0]["line_total"] == "100.00"
    assert card["estimated_total"] == "100.00"


@pytest.mark.django_db
def test_history_filters_by_status_and_date(
    company, rep, rep_warehouse, company_warehouse, product
):
    create_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("1"))]
    )
    client = client_for(rep)
    today = timezone.localdate().isoformat()
    old = (timezone.localdate() - timedelta(days=5)).isoformat()

    def count(query):
        return len(client.get(f"/api/reps/stock-transfers/{query}").json()["data"]["transfers"])

    assert count("") == 1
    assert count("?status=pending") == 1
    assert count("?status=received") == 0
    assert count(f"?date={today}") == 1
    assert count(f"?date={old}") == 0


@pytest.mark.django_db
def test_receiving_adds_the_goods_to_the_van(
    company, rep, owner, rep_warehouse, company_warehouse, product
):
    """"أضيفت لمستودع السيارة" — the one step in the flow that moves stock."""
    stocked_company_warehouse(company, company_warehouse, product)
    transfer = create_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("24"))]
    )
    approve_transfer(transfer, approved_by_id=owner.id)

    response = client_for(rep).post(f"/api/reps/stock-transfers/{transfer.id}/receive/")

    assert response.status_code == 200
    assert response.json()["data"]["transfer"]["status"] == "received"
    assert available_quantity(rep_warehouse.id, product.id) == Decimal("24")
    assert available_quantity(company_warehouse.id, product.id) == Decimal("76")


@pytest.mark.django_db
def test_a_rep_sees_only_their_own_requests(
    company, rep, other_rep, rep_warehouse, company_warehouse, product
):
    create_stock_transfer(
        company_id=company.id, rep=rep, lines=[(product, Decimal("1"))]
    )

    assert (
        client_for(other_rep).get("/api/reps/stock-transfers/").json()["data"]["transfers"]
        == []
    )


# ---------------------------------------------------------------------------
# The product picker
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_the_picker_shows_price_and_what_is_already_in_the_van(
    company, rep, stocked_rep_warehouse, product, other_product, currency
):
    rows = client_for(rep).get("/api/reps/products/").json()["data"]["products"]
    by_name = {row["name"]: row for row in rows}

    assert by_name["Rice 1kg"]["price"] == "10.00"
    assert by_name["Rice 1kg"]["van_quantity"] == "100.000"
    assert by_name["Rice 1kg"]["unit_name"] == "Package"


@pytest.mark.django_db
def test_the_picker_lists_products_the_van_has_none_of(
    company, rep, rep_warehouse, product, other_product, currency
):
    """A restock screen exists precisely for the rows reading zero."""
    rows = client_for(rep).get("/api/reps/products/").json()["data"]["products"]

    assert len(rows) == 2
    assert {row["van_quantity"] for row in rows} == {"0.000"}


@pytest.mark.django_db
def test_the_picker_hides_unsellable_products(company, rep, rep_warehouse, unit, product):
    from apps.products.models import Product

    Product.objects.create(
        company=company, name="Internal supplies", unit=unit, is_sellable=False
    )

    names = {
        row["name"]
        for row in client_for(rep).get("/api/reps/products/").json()["data"]["products"]
    }

    assert names == {"Rice 1kg"}


@pytest.mark.django_db
def test_the_picker_searches_by_name(company, rep, rep_warehouse, product, other_product):
    rows = client_for(rep).get("/api/reps/products/?search=Sugar").json()["data"]["products"]

    assert [row["name"] for row in rows] == ["Sugar 1kg"]


@pytest.mark.django_db
def test_an_unpriced_product_reads_null_but_still_reports_a_quantity(
    company, rep, stocked_rep_warehouse, unit
):
    from apps.products.models import Product

    Product.objects.create(company=company, name="No price yet", unit=unit)

    row = next(
        r
        for r in client_for(rep).get("/api/reps/products/").json()["data"]["products"]
        if r["name"] == "No price yet"
    )

    assert row["price"] is None
    assert row["van_quantity"] == "0.000"


@pytest.mark.django_db
def test_the_warehouse_request_screens_are_rep_only(owner):
    from apps.authentication.utils import generate_tokens_for_subuser

    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )

    assert client.get("/api/reps/products/").status_code == 403
    assert client.get("/api/reps/stock-transfers/").status_code == 403
