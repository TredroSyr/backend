from __future__ import annotations

from django.db import models


class Rep(models.Model):
    """Company-scoped sales rep. Warehouse is a products.Warehouse with owner_type=rep."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="reps",
    )
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32)
    password = models.CharField(max_length=128)
    referral_code = models.CharField(max_length=32, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rep"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "phone"],
                name="rep_company_phone_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="rep_company_idx"),
            models.Index(fields=["phone"], name="rep_phone_idx"),
            models.Index(fields=["referral_code"], name="rep_referral_code_idx"),
        ]

    def __str__(self) -> str:
        return self.name
