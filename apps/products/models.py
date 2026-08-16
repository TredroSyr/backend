from __future__ import annotations

from django.db import models
from django.db.models import Q


class WarehouseOwnerType(models.TextChoices):
    COMPANY = "company", "Company"
    REP = "rep", "Rep"


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


class Warehouse(models.Model):
    """Belongs to a Company. Rep warehouses reuse this table (plan §2 default; §7 still open)."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="warehouses",
    )
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, default="")
    kind = models.CharField(max_length=64, blank=True, default="")
    owner_type = models.CharField(max_length=16, choices=WarehouseOwnerType.choices)
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="warehouses",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "warehouse"
        constraints = [
            models.CheckConstraint(
                condition=(
                    Q(owner_type=WarehouseOwnerType.COMPANY, rep__isnull=True)
                    | Q(owner_type=WarehouseOwnerType.REP, rep__isnull=False)
                ),
                name="warehouse_owner_matches_rep",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="warehouse_company_idx"),
            models.Index(fields=["rep"], name="warehouse_rep_idx"),
            models.Index(
                fields=["company", "owner_type"],
                name="wh_company_owner_type_idx",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, blank=True, default="")
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="products",
        help_text="Required. Pick from the predefined catalog, not free text.",
    )
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    image = models.FileField(upload_to="products/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"],
                condition=~Q(sku=""),
                name="product_company_sku_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="product_company_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class ProductWarehouseStock(models.Model):
    """M2M assignment plus a quantity projection of StockMovement — not a second source of truth."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="product_warehouse_stocks",
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="warehouse_stocks"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="product_stocks"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_warehouse_stock"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "warehouse"],
                name="product_warehouse_stock_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="pws_company_idx"),
            models.Index(fields=["warehouse"], name="pws_warehouse_idx"),
        ]
