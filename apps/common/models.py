from __future__ import annotations

from django.db import models


class UnitOfMeasure(models.Model):
    """Predefined material units. Companies pick from this list; they do not create units.

    Seeded: liter, kg, package. Full catalog beyond those three is still open.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "unit_of_measure"

    def __str__(self) -> str:
        return self.name


class Currency(models.Model):
    """Predefined currency catalog (ISO 4217). Same pattern as UnitOfMeasure: companies pick,
    they do not create currencies.
    """

    code = models.CharField(max_length=3, unique=True, help_text="ISO 4217 code, e.g. USD, EUR")
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=8, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "currency"
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return self.code
