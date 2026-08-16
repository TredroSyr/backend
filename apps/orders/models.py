from __future__ import annotations

from django.db import models


class OrderType(models.TextChoices):
    REP_TO_COMPANY = "rep_to_company", "Rep → Company"
    CUSTOMER_TO_COMPANY = "customer_to_company", "Customer → Company"


class OrderStatus(models.TextChoices):
    """Known values from §3 only. Customer→Company states after assignment are §7."""

    PENDING_REP_ASSIGNMENT = "pending_rep_assignment", "Pending rep assignment"
    READY_FOR_PICKUP = "ready_for_pickup", "Ready for pickup"
    RECEIVED_CONFIRMED = "received_confirmed", "Received confirmed"


class StockMovementType(models.TextChoices):
    INITIAL = "initial", "Initial stock"
    INCOMING = "incoming", "Incoming invoice receipt"
    ORDER_OUT = "order_out", "Stock leaving a warehouse (order)"
    ORDER_IN = "order_in", "Stock entering a warehouse (order)"
    RETURN_IN = "return_in", "Return received into a warehouse"
    RETURN_OUT = "return_out", "Return leaving a warehouse"
    ADJUSTMENT = "adjustment", "Manual adjustment"


class Order(models.Model):
    """Both Rep→Company and Customer→Company flows. fulfilling_rep is distinct from placing_rep."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="orders",
    )
    order_type = models.CharField(max_length=32, choices=OrderType.choices)
    status = models.CharField(max_length=64)
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Set for customer→company orders.",
    )
    placing_rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="placed_orders",
        help_text="Set for rep→company orders (the 'created by' rep).",
    )
    fulfilling_rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fulfilling_orders",
        help_text="Nullable. Required to leave pending_rep_assignment.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "order"
        indexes = [
            models.Index(fields=["company"], name="order_company_idx"),
            models.Index(fields=["company", "status"], name="order_company_status_idx"),
            models.Index(fields=["status"], name="order_status_idx"),
            models.Index(fields=["customer"], name="order_customer_idx"),
            models.Index(fields=["placing_rep"], name="order_placing_rep_idx"),
            models.Index(fields=["fulfilling_rep"], name="order_fulfilling_rep_idx"),
        ]


class OrderItem(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="order_items",
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="order_items",
    )
    unit = models.ForeignKey(
        "products.UnitOfMeasure",
        on_delete=models.PROTECT,
        related_name="order_items",
        help_text="Snapshot of Product.unit at line creation.",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "order_item"
        indexes = [
            models.Index(fields=["company"], name="order_item_company_idx"),
            models.Index(fields=["order"], name="order_item_order_idx"),
        ]


class StockMovement(models.Model):
    """Append-only ledger. One row, one warehouse, signed quantity. Never UPDATE/DELETE."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="stock_movements",
    )
    warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="stock_movements",
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text="Signed, in the product's UnitOfMeasure. Positive = inbound, negative = outbound.",
    )
    movement_type = models.CharField(max_length=32, choices=StockMovementType.choices)
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    invoice = models.ForeignKey(
        "invoices.Invoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movement"
        indexes = [
            models.Index(fields=["company"], name="stock_movement_company_idx"),
            models.Index(fields=["warehouse"], name="stock_movement_wh_idx"),
            models.Index(
                fields=["warehouse", "product"],
                name="stock_movement_wh_prod_idx",
            ),
            models.Index(fields=["order"], name="stock_movement_order_idx"),
            models.Index(fields=["created_at"], name="stock_movement_created_idx"),
        ]
