"""Shared fixtures for the invoicing module tests.

Builds the minimum real-world setup the spec's flows need: a company with an
Invoice Settings row, one company warehouse, one rep with their own warehouse,
a customer, and a couple of priced products.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.models import Currency, UnitOfMeasure
from apps.companies.models import Company, SubUser
from apps.customers.models import Customer
from apps.products.models import Product, ProductPrice, Warehouse, WarehouseOwnerType
from apps.reps.models import Rep, RepCustomerAssignment


@pytest.fixture
def company(db) -> Company:
    return Company.objects.create(name="Tredro Foods", slug="tredro-foods", currency="SYP")


@pytest.fixture
def currency(db) -> Currency:
    currency, _ = Currency.objects.get_or_create(
        code="SYP", defaults={"name": "Syrian Pound", "symbol": "L.S"}
    )
    return currency


@pytest.fixture
def unit(db) -> UnitOfMeasure:
    unit, _ = UnitOfMeasure.objects.get_or_create(
        code="package", defaults={"name": "Package"}
    )
    return unit


@pytest.fixture
def owner(company) -> SubUser:
    return SubUser.objects.create(
        company=company,
        is_owner=True,
        name="Owner",
        phone="+963900000001",
        password="x",
    )


@pytest.fixture
def rep(company) -> Rep:
    return Rep.objects.create(
        company=company,
        name="Sami",
        phone="+963911111111",
        password="x",
        referral_code="REP-SAMI",
    )


@pytest.fixture
def other_rep(company) -> Rep:
    return Rep.objects.create(
        company=company,
        name="Nour",
        phone="+963922222222",
        password="x",
        referral_code="REP-NOUR",
    )


@pytest.fixture
def company_warehouse(company) -> Warehouse:
    return Warehouse.objects.create(
        company=company, name="Main store", owner_type=WarehouseOwnerType.COMPANY
    )


@pytest.fixture
def rep_warehouse(company, rep) -> Warehouse:
    return Warehouse.objects.create(
        company=company,
        name="Sami's van",
        owner_type=WarehouseOwnerType.REP,
        rep=rep,
    )


@pytest.fixture
def customer(db, company, rep) -> Customer:
    customer = Customer.objects.create(name="Abu Ahmad Market", phone="+963955555555")
    RepCustomerAssignment.objects.create(rep=rep, customer=customer)
    return customer


def _make_product(company, unit, currency, name, price):
    product = Product.objects.create(
        company=company, name=name, unit=unit, tax_rate=Decimal("0")
    )
    ProductPrice.objects.create(
        product=product, currency=currency, price=price, is_default=True
    )
    return product


@pytest.fixture
def product(company, unit, currency) -> Product:
    return _make_product(company, unit, currency, "Rice 1kg", Decimal("10.00"))


@pytest.fixture
def other_product(company, unit, currency) -> Product:
    return _make_product(company, unit, currency, "Sugar 1kg", Decimal("5.00"))


@pytest.fixture
def stocked_rep_warehouse(company, rep_warehouse, product, other_product):
    """Put 100 of each product in the rep's van so sales have something to sell."""
    from apps.products.models import StockMovementType
    from apps.products.services.stock import StockChange, apply_stock_changes

    apply_stock_changes(
        company_id=company.id,
        warehouse=rep_warehouse,
        changes=[
            StockChange(product_id=product.id, quantity=Decimal("100")),
            StockChange(product_id=other_product.id, quantity=Decimal("100")),
        ],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    return rep_warehouse
