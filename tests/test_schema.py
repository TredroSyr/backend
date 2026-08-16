from __future__ import annotations

import pytest
from django.db import IntegrityError

from apps.companies.models import Company
from apps.products.models import UnitOfMeasure, Warehouse, WarehouseOwnerType
from apps.reps.models import Rep


@pytest.mark.django_db
def test_unit_of_measure_seed_contains_agreed_units() -> None:
    codes = set(UnitOfMeasure.objects.values_list("code", flat=True))
    assert {"liter", "kg", "package"}.issubset(codes)


@pytest.mark.django_db
def test_company_can_be_created() -> None:
    company = Company.objects.create(name="Acme", slug="acme", currency="USD")
    assert company.pk is not None
    assert company.is_active is True


@pytest.mark.django_db
def test_warehouse_rep_owner_requires_rep() -> None:
    company = Company.objects.create(name="Acme", slug="acme-wh", currency="USD")
    with pytest.raises(IntegrityError):
        Warehouse.objects.create(
            company=company,
            name="Rep bin",
            owner_type=WarehouseOwnerType.REP,
            rep=None,
        )


@pytest.mark.django_db
def test_company_warehouse_cannot_have_rep() -> None:
    company = Company.objects.create(name="Acme", slug="acme-wh2", currency="USD")
    rep = Rep.objects.create(
        company=company,
        name="Sam",
        phone="+10000000001",
        password="hashed",
        referral_code="SAM001",
    )
    with pytest.raises(IntegrityError):
        Warehouse.objects.create(
            company=company,
            name="Main",
            owner_type=WarehouseOwnerType.COMPANY,
            rep=rep,
        )
