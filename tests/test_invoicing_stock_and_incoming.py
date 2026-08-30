"""Stock ledger primitives and the Incoming Invoice flow (spec §3.1, §4.1, §6.1)."""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_subuser
from apps.common.models import Currency, DocumentType
from apps.invoices.models import IncomingInvoice, IncomingInvoiceStatus
from apps.invoices.services.documents import LineInput
from apps.invoices.services.incoming import (
    cancel_incoming_invoice,
    create_incoming_invoice,
    issue_incoming_invoice,
)
from apps.products.models import (
    PriceType,
    ProductPrice,
    ProductWarehouseStock,
    StockMovement,
    StockMovementType,
)
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


# ---------------------------------------------------------------------------
# Which price list an omitted `unit_price` reads
# ---------------------------------------------------------------------------


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


@pytest.fixture
def product_with_a_cost_price(product, currency) -> ProductPrice:
    """The conftest product sells for 10.00; here it costs 6.00.

    Far enough apart that a line priced from the wrong list cannot pass by
    coincidence.
    """
    return ProductPrice.objects.create(
        product=product,
        currency=currency,
        price_type=PriceType.COST,
        price=Decimal("6.00"),
    )


def post_incoming(client, warehouse, product, **overrides):
    payload = {
        "warehouse": warehouse.id,
        "lines": [{"product_id": product.id, "quantity": "5"}],
        **overrides,
    }
    return client.post("/api/companies/incoming-invoices/", payload, format="json")


@pytest.mark.django_db
def test_an_omitted_unit_price_is_read_from_the_cost_list(
    admin_client, company_warehouse, product, product_with_a_cost_price
):
    response = post_incoming(admin_client, company_warehouse, product)

    assert response.status_code == 201, response.data
    invoice = response.data["data"]["invoice"]
    assert [line["unit_price"] for line in invoice["lines"]] == ["6.00"]
    assert invoice["total_amount"] == "30.00"


@pytest.mark.django_db
def test_a_missing_cost_price_is_refused_rather_than_sold_at_retail(
    admin_client, company_warehouse, product
):
    """The product has a sale price and no cost price. Booking the bill at what
    the goods are *sold* for would look deliberate and be wrong, so the write is
    rejected and the price asked for instead.
    """
    response = post_incoming(admin_client, company_warehouse, product)

    assert response.status_code == 400, response.data
    assert IncomingInvoice.objects.count() == 0


@pytest.mark.django_db
def test_an_explicit_unit_price_still_wins(
    admin_client, company_warehouse, product, product_with_a_cost_price
):
    response = post_incoming(
        admin_client,
        company_warehouse,
        product,
        lines=[{"product_id": product.id, "quantity": "5", "unit_price": "7.25"}],
    )

    assert response.status_code == 201, response.data
    assert response.data["data"]["invoice"]["total_amount"] == "36.25"


@pytest.mark.django_db
def test_the_cost_list_is_read_in_the_documents_own_currency(
    admin_client, company_warehouse, product, product_with_a_cost_price
):
    """A USD bill must read the USD cost row, not the SYP one."""
    usd, _ = Currency.objects.get_or_create(
        code="USD", defaults={"name": "US Dollar", "symbol": "$"}
    )
    ProductPrice.objects.create(
        product=product,
        currency=usd,
        price_type=PriceType.COST,
        price=Decimal("0.30"),
    )

    response = post_incoming(admin_client, company_warehouse, product, currency="USD")

    assert response.status_code == 201, response.data
    assert response.data["data"]["invoice"]["total_amount"] == "1.50"


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_search_matches_the_supplier_as_well_as_the_number(
    admin_client, company, company_warehouse, product
):
    lines = [LineInput(product=product, quantity=Decimal("1"), unit_price=Decimal("1.00"))]
    wanted = create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=lines,
        supplier_ref="Damascus Trading Co.",
    )
    create_incoming_invoice(
        company_id=company.id,
        warehouse=company_warehouse,
        lines=lines,
        supplier_ref="Aleppo Wholesale",
    )

    response = admin_client.get("/api/companies/incoming-invoices/?search=Damascus")

    assert response.status_code == 200, response.data
    assert [row["id"] for row in response.data["data"]["invoices"]] == [wanted.id]
