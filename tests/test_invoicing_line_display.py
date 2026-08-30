"""What a document line carries about its product.

A line is read far more often than the catalog behind it, so it names its own
product rather than making the client fetch one per row. The joins that make
that affordable are declared once in `views.document_lines`; these tests pin
both the payload and the query count it is supposed to hold flat.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_subuser
from apps.invoices.services.documents import LineInput
from apps.invoices.services.incoming import create_incoming_invoice
from apps.invoices.services.sales import create_sales_invoice
from apps.products.models import ProductImage


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


@pytest.fixture
def pictured_product(product):
    product.sku = "RICE-1"
    product.barcode = "6291041500213"
    product.save(update_fields=["sku", "barcode"])
    ProductImage.objects.create(
        product=product,
        image="products/rice.png",
        alt_text="Rice 1kg",
        is_primary=True,
    )
    return product


def sell(company, rep, customer, product, quantity="3"):
    return create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product,
                quantity=Decimal(quantity),
                unit_price=Decimal("10.00"),
            )
        ],
    )


def test_a_sold_line_names_its_product(
    admin_client, company, rep, customer, pictured_product, stocked_rep_warehouse
):
    invoice = sell(company, rep, customer, pictured_product)

    response = admin_client.get(f"/api/companies/sales-invoices/{invoice.id}/")

    assert response.status_code == 200
    line = response.json()["data"]["invoice"]["lines"][0]

    assert line["product_name"] == pictured_product.name
    assert line["product_sku"] == "RICE-1"
    assert line["product_barcode"] == "6291041500213"
    assert line["unit_code"] == "package"
    assert line["unit_name"] == "Package"
    assert line["product_image"]["alt_text"] == "Rice 1kg"
    assert line["product_image"]["image"].startswith("http")


def test_a_received_line_names_it_the_same_way(
    admin_client, company, pictured_product, company_warehouse
):
    """Every document type reads lines through the same shape."""
    invoice = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=[
            LineInput(
                product=pictured_product,
                quantity=Decimal("20"),
                unit_price=Decimal("8.00"),
            )
        ],
    )

    response = admin_client.get(f"/api/companies/incoming-invoices/{invoice.id}/")

    assert response.status_code == 200
    line = response.json()["data"]["invoice"]["lines"][0]

    assert line["product_barcode"] == "6291041500213"
    assert line["unit_code"] == "package"
    assert line["product_image"]["alt_text"] == "Rice 1kg"


def test_reading_a_line_costs_no_query_of_its_own(
    admin_client,
    company,
    rep,
    customer,
    pictured_product,
    other_product,
    stocked_rep_warehouse,
):
    """A second line must not add queries — the product joins are prefetched."""
    one_line = sell(company, rep, customer, pictured_product)
    two_lines = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=pictured_product,
                quantity=Decimal("2"),
                unit_price=Decimal("10.00"),
            ),
            LineInput(
                product=other_product,
                quantity=Decimal("4"),
                unit_price=Decimal("5.00"),
            ),
        ],
    )

    with CaptureQueriesContext(connection) as single:
        admin_client.get(f"/api/companies/sales-invoices/{one_line.id}/")

    with CaptureQueriesContext(connection) as double:
        response = admin_client.get(f"/api/companies/sales-invoices/{two_lines.id}/")

    assert len(response.json()["data"]["invoice"]["lines"]) == 2
    assert len(double) == len(single)
