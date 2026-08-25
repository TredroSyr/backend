from __future__ import annotations

from django.db import models
from django.db.models import Q

from apps.common.models import Currency, UnitOfMeasure


class WarehouseOwnerType(models.TextChoices):
    COMPANY = "company", "Company"
    REP = "rep", "Rep"


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


class ProductCategory(models.Model):
    """Optional company-scoped, self-referencing category tree for products."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="product_categories",
    )
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_category"
        verbose_name_plural = "product categories"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "parent", "name"],
                name="product_category_company_parent_name_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="product_cat_company_idx"),
            models.Index(fields=["parent"], name="product_cat_parent_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="products",
    )
    category = models.ForeignKey(
        ProductCategory,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="products",
    )
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    sku = models.CharField(max_length=64, blank=True, default="")
    barcode = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="GTIN / UPC / EAN, if applicable.",
    )
    brand = models.CharField(max_length=128, blank=True, default="")
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="products",
        help_text="Required. Pick from the predefined catalog, not free text.",
    )
    image = models.FileField(upload_to="products/", null=True, blank=True)

    # Physical attributes, useful for warehousing/shipping.
    weight = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    weight_unit = models.CharField(max_length=8, blank=True, default="")
    length = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    width = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    height = models.DecimalField(max_digits=10, decimal_places=3, null=True, blank=True)
    dimension_unit = models.CharField(max_length=8, blank=True, default="")

    # Inventory planning.
    reorder_point = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)
    reorder_quantity = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    # Commercial flags. Pricing itself lives in ProductPrice (multi-currency).
    is_taxable = models.BooleanField(default=True)
    tax_rate = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True,
        help_text="Percentage, e.g. 21.00 for 21%.",
    )
    is_sellable = models.BooleanField(default=True)
    is_purchasable = models.BooleanField(default=True)

    external_reference = models.CharField(
        max_length=128, blank=True, default="",
        help_text="ID in an external/legacy system, for integrations.",
    )
    notes = models.TextField(blank=True, default="")

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
            models.Index(fields=["category"], name="product_category_idx"),
            models.Index(fields=["barcode"], name="product_barcode_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class PriceType(models.TextChoices):
    STANDARD = "standard", "Standard"
    WHOLESALE = "wholesale", "Wholesale"
    COST = "cost", "Cost"


class ProductPrice(models.Model):
    """Multi-currency pricing. A product can have several prices, one per
    (currency, price_type) combination.

    customer_category is optional:
    - null -> the general price for that currency/price_type.
    - set  -> overrides the general price for every customer in that category
      (e.g. a wholesale price for all customers in the 'Wholesale' category).
    """

    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="prices")
    currency = models.ForeignKey(
        Currency, on_delete=models.PROTECT, related_name="product_prices"
    )
    price_type = models.CharField(
        max_length=16, choices=PriceType.choices, default=PriceType.STANDARD
    )
    customer_category = models.ForeignKey(
        "customers.CustomerCategory",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="product_prices",
        help_text="Leave blank for the general price. Set to override for that customer category.",
    )
    price = models.DecimalField(max_digits=12, decimal_places=2)
    is_default = models.BooleanField(
        default=False,
        help_text="Marks the default currency to show/use for this product's general price.",
    )
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_price"
        constraints = [
            # One general (no customer category) price per product/currency/price_type.
            models.UniqueConstraint(
                fields=["product", "currency", "price_type"],
                condition=Q(customer_category__isnull=True),
                name="product_price_general_uniq",
            ),
            # One price per product/currency/price_type/customer_category when set.
            models.UniqueConstraint(
                fields=["product", "currency", "price_type", "customer_category"],
                condition=Q(customer_category__isnull=False),
                name="product_price_customer_category_uniq",
            ),
            models.UniqueConstraint(
                fields=["product"],
                condition=Q(is_default=True, customer_category__isnull=True),
                name="product_price_one_default",
            ),
        ]
        indexes = [
            models.Index(fields=["product"], name="product_price_product_idx"),
            models.Index(fields=["currency"], name="product_price_currency_idx"),
            models.Index(
                fields=["customer_category"], name="product_price_cust_cat_idx"
            ),
        ]

    def __str__(self) -> str:
        suffix = f" [{self.customer_category}]" if self.customer_category_id else ""
        return f"{self.product} - {self.price} {self.currency_id}{suffix}"


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


# ---------------------------------------------------------------------------
# Dynamic custom fields (EAV)
#
# Kept intentionally lean: no field types, no validation rules, no filtering
# support. A CustomFieldDefinition is the reusable "attribute" a company
# defines once (e.g. "Warranty months"); CustomFieldValue is the value a
# specific product has for that attribute. Splitting these two, rather than
# a flat key/value on Product, avoids typo'd/duplicate keys and lets a
# company list and reuse the fields it has defined.
# ---------------------------------------------------------------------------


class CustomFieldDefinition(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="product_custom_field_definitions",
    )
    key = models.SlugField(max_length=64, help_text="Machine name, e.g. 'warranty_months'.")
    label = models.CharField(max_length=128, help_text="Display name shown in the UI.")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "custom_field_definition"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "key"], name="custom_field_def_company_key_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="cfd_company_idx"),
        ]

    def __str__(self) -> str:
        return self.label


class CustomFieldValue(models.Model):
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="custom_field_values"
    )
    definition = models.ForeignKey(
        CustomFieldDefinition, on_delete=models.CASCADE, related_name="values"
    )
    value = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "custom_field_value"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "definition"], name="custom_field_value_uniq"
            ),
        ]
        indexes = [
            models.Index(fields=["product"], name="cfv_product_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.definition.key} = {self.value}"