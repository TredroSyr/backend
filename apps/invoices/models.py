from __future__ import annotations

from django.db import models


class InvoiceType(models.TextChoices):
    INCOMING = "incoming", "Incoming"
    RETURN = "return", "Return"


class Invoice(models.Model):
    """Incoming (stock receipt) or Return. Immutable after insert — no updated_at.

    Payment timing is §7 — no paid_at. Corrections are new rows; no parent FK yet.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="invoices",
    )
    invoice_type = models.CharField(max_length=16, choices=InvoiceType.choices)
    warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="invoices",
    )
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        help_text="Set for return invoices initiated by a rep.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice"
        indexes = [
            models.Index(fields=["company"], name="invoice_company_idx"),
            models.Index(fields=["invoice_type"], name="invoice_type_idx"),
            models.Index(fields=["warehouse"], name="invoice_warehouse_idx"),
        ]


class InvoiceItem(models.Model):
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="invoice_items",
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        "products.Product",
        on_delete=models.PROTECT,
        related_name="invoice_items",
    )
    unit = models.ForeignKey(
        "products.UnitOfMeasure",
        on_delete=models.PROTECT,
        related_name="invoice_items",
        help_text="Snapshot of Product.unit at line creation.",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "invoice_item"
        indexes = [
            models.Index(fields=["company"], name="invoice_item_company_idx"),
            models.Index(fields=["invoice"], name="invoice_item_invoice_idx"),
        ]
