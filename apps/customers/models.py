from __future__ import annotations

from django.db import models


class Customer(models.Model):
    """Global entity — no company_id. Registers once; orders from any company.

    assigned_rep is the §3 referral/admin assignment field. Per-company assignment
    vs a single global FK is still §7. Trade-license image is §7 — no column.
    """

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, unique=True)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(max_length=128)
    assigned_rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_customers",
    )
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer"
        indexes = [
            models.Index(fields=["phone"], name="customer_phone_idx"),
            models.Index(fields=["assigned_rep"], name="customer_assigned_rep_idx"),
        ]

    def __str__(self) -> str:
        return self.name
