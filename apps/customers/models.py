from __future__ import annotations

from django.db import models


class Customer(models.Model):
    """Global entity — no company_id. Registers once; orders from any company.

    Customer can be created manually by a company (no password set) or can sign up
    themselves. If created manually first, they can complete signup later by setting
    password without conflict.
    
    assigned_reps is a many-to-many relationship allowing customer to be assigned
    to multiple reps from different companies.
    
    referral_code_used tracks the original referral code used during signup for
    attribution/analytics, separate from assigned_reps which can be changed by admin.
    """

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, unique=True)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(
        max_length=128,
        null=True,
        blank=True,
        help_text="Only set by customer during signup, not by company"
    )
    assigned_reps = models.ManyToManyField(
        "reps.Rep",
        related_name="assigned_customers",
        blank=True,
        help_text="Reps from any company can be assigned to this customer"
    )
    referral_code_used = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        help_text="Original referral code used during signup (immutable for tracking)",
    )
    category = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        help_text="Customer category (free text, choices defined in serializer)"
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
            models.Index(fields=["referral_code_used"], name="customer_referral_code_idx"),
            models.Index(fields=["category"], name="customer_category_idx"),
        ]

    def __str__(self) -> str:
        return self.name
    
    def has_completed_signup(self) -> bool:
        """Check if customer has completed signup by setting password."""
        return bool(self.password)
    
    def can_complete_signup(self) -> bool:
        """Check if customer can complete signup (no password set yet)."""
        return not self.password
