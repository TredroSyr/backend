"""The derived fields the product catalog screens read.

Stock totals, counts and the cover image are computed rather than stored, and
each one is served from a different place depending on the endpoint — a
subquery annotation on the list, a prefetch on the detail, a plain query when
the serializer is handed a freshly saved instance. These tests pin the values
so those three paths cannot drift apart.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_subuser
from apps.products.models import (
    CustomFieldDefinition,
    CustomFieldValue,
    PriceType,
    Product,
    ProductCategory,
    ProductImage,
    ProductPrice,
    StockMovementType,
)
from apps.products.services.stock import StockChange, apply_stock_changes


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


@pytest.fixture
def catalogued_product(company, product, currency, company_warehouse, rep_warehouse):
    """One product carrying every relation the display fields read.

    Stock is split across two warehouses on purpose: a total that only looks at
    the first row would still pass with a single warehouse.
    """
    category = ProductCategory.objects.create(company=company, name="Grains")
    subcategory = ProductCategory.objects.create(
        company=company, name="Rice", parent=category
    )
    product.category = subcategory
    product.reorder_point = Decimal("50")
    product.save(update_fields=["category", "reorder_point"])

    ProductPrice.objects.create(
        product=product,
        currency=currency,
        price=Decimal("9.00"),
        price_type=PriceType.WHOLESALE,
    )

    for warehouse, quantity in ((company_warehouse, "30"), (rep_warehouse, "12.5")):
        apply_stock_changes(
            company_id=company.id,
            warehouse=warehouse,
            changes=[StockChange(product_id=product.id, quantity=Decimal(quantity))],
            movement_type=StockMovementType.INITIAL,
            source_type="manual",
        )

    definition = CustomFieldDefinition.objects.create(
        company=company, key="warranty_months", label="Warranty (months)"
    )
    CustomFieldValue.objects.create(
        product=product, definition=definition, value="12"
    )
    return product


def test_list_reports_stock_totals_and_counts(admin_client, catalogued_product):
    """The list row carries everything a product card shows."""
    response = admin_client.get("/api/companies/products/")

    assert response.status_code == 200
    row = next(
        item
        for item in response.json()["data"]["products"]
        if item["id"] == catalogued_product.id
    )

    assert Decimal(row["total_stock"]) == Decimal("42.5")
    assert row["is_low_stock"] is True  # 42.5 sits under the reorder point of 50
    assert row["prices_count"] == 2
    assert row["images_count"] == 0
    assert row["unit_code"] == "package"
    assert row["category_name"] == "Rice"
    assert row["default_price"]["currency_code"] == "SYP"
    assert Decimal(row["default_price"]["price"]) == Decimal("10.00")


def test_list_totals_stay_independent_per_product(
    admin_client, catalogued_product, other_product
):
    """A join-based aggregate would inflate these; the subqueries must not."""
    response = admin_client.get("/api/companies/products/")

    rows = {item["id"]: item for item in response.json()["data"]["products"]}

    assert Decimal(rows[catalogued_product.id]["total_stock"]) == Decimal("42.5")
    assert Decimal(rows[other_product.id]["total_stock"]) == Decimal("0")
    assert rows[other_product.id]["prices_count"] == 1
    # No reorder point set on this one: "not tracked" is not "stock is fine".
    assert rows[other_product.id]["is_low_stock"] is None


def test_detail_breaks_stock_down_per_warehouse(
    admin_client, catalogued_product, company_warehouse, rep_warehouse, rep
):
    response = admin_client.get(f"/api/companies/products/{catalogued_product.id}/")

    assert response.status_code == 200
    product = response.json()["data"]["product"]

    assert Decimal(product["total_stock"]) == Decimal("42.5")
    assert product["is_low_stock"] is True

    stocks = {row["warehouse"]: row for row in product["warehouse_stocks"]}
    assert Decimal(stocks[company_warehouse.id]["quantity"]) == Decimal("30")
    assert stocks[company_warehouse.id]["warehouse_owner_type"] == "company"
    assert stocks[company_warehouse.id]["rep"] is None

    assert Decimal(stocks[rep_warehouse.id]["quantity"]) == Decimal("12.5")
    assert stocks[rep_warehouse.id]["warehouse_owner_type"] == "rep"
    assert stocks[rep_warehouse.id]["rep_name"] == rep.name


def test_detail_labels_categories_and_custom_fields(admin_client, catalogued_product):
    """Names and labels travel with the ids, so no screen needs a second call."""
    response = admin_client.get(f"/api/companies/products/{catalogued_product.id}/")

    product = response.json()["data"]["product"]

    assert product["category_name"] == "Rice"
    assert product["category_parent_name"] == "Grains"
    assert product["unit_name"] == "Package"
    assert product["status_display"] == "Published"

    assert product["custom_fields"] == {"warranty_months": "12"}
    assert product["custom_field_values"] == [
        {
            "id": product["custom_field_values"][0]["id"],
            "definition": product["custom_field_values"][0]["definition"],
            "key": "warranty_months",
            "label": "Warranty (months)",
            "value": "12",
        }
    ]

    prices = {price["price_type"]: price for price in product["prices"]}
    assert prices["wholesale"]["currency_symbol"] == "L.S"
    assert prices["wholesale"]["price_type_display"] == "Wholesale"


def test_create_response_carries_the_same_derived_fields(admin_client, company, unit):
    """The POST response is built from an unprefetched instance — same numbers."""
    response = admin_client.post(
        "/api/companies/products/",
        {"name": "Lentils 1kg", "unit": unit.id},
        format="json",
    )

    assert response.status_code == 201
    product = response.json()["data"]["product"]

    assert Decimal(product["total_stock"]) == Decimal("0")
    assert product["is_low_stock"] is None
    assert product["images_count"] == 0
    assert product["prices_count"] == 0
    assert product["primary_image"] is None
    assert product["default_price"] is None
    assert product["warehouse_stocks"] == []


def test_warehouse_stock_endpoint_names_the_product_and_its_unit(
    admin_client, catalogued_product, company_warehouse
):
    response = admin_client.get(
        f"/api/companies/products/{catalogued_product.id}/warehouse-stock/"
    )

    assert response.status_code == 200
    rows = {row["warehouse"]: row for row in response.json()["data"]["stock"]}

    row = rows[company_warehouse.id]
    assert row["product_name"] == catalogued_product.name
    assert row["unit_code"] == "package"
    assert row["warehouse_name"] == company_warehouse.name
    assert Decimal(row["reorder_point"]) == Decimal("50")
    # 30 in this one warehouse is below the reorder point, even though it is
    # only part of the 42.5 the product holds overall.
    assert row["is_low_stock"] is True


def test_list_query_count_does_not_grow_with_the_catalogue(
    admin_client, company, unit, currency, company_warehouse
):
    """The totals and cover image come from annotations and prefetches.

    Reading them off each product instead would add queries per row, which is
    exactly what a growing catalogue would turn into a slow page.
    """

    def build(count):
        for index in range(count):
            product = Product.objects.create(
                company=company, name=f"Item {index}", unit=unit
            )
            ProductPrice.objects.create(
                product=product,
                currency=currency,
                price=Decimal("1.00"),
                is_default=True,
            )
            ProductImage.objects.create(
                product=product, image="products/x.png", is_primary=True
            )
            apply_stock_changes(
                company_id=company.id,
                warehouse=company_warehouse,
                changes=[StockChange(product_id=product.id, quantity=Decimal("1"))],
                movement_type=StockMovementType.INITIAL,
                source_type="manual",
            )

    build(2)
    with CaptureQueriesContext(connection) as small:
        assert admin_client.get("/api/companies/products/").status_code == 200

    build(8)
    with CaptureQueriesContext(connection) as large:
        response = admin_client.get("/api/companies/products/")

    assert len(response.json()["data"]["products"]) == 10
    assert len(large) == len(small)
