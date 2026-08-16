from __future__ import annotations

from django.db import models
from django.db.models import Q


class Company(models.Model):
    """Tenant. Current plan is resolved via billing.Subscription, never inlined here."""

    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    currency = models.CharField(max_length=3, default="SYP")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Onboarding fields
    logo = models.FileField(upload_to="companies/logos/", null=True, blank=True)
    cover = models.FileField(upload_to="companies/covers/", null=True, blank=True)
    governorate = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(max_length=500, null=True, blank=True)
    business_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[
            ("food_products", "مواد غذائية"),
            ("electronics", "إلكترونيات"),
            ("cosmetics", "مستحضرات تجميل"),
            ("medical_supplies", "أدوية ومستلزمات طبية"),
            ("home_tools", "أدوات منزلية"),
            ("clothing", "ألبسة"),
        ],
    )
    onboarding_completed = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "company"
        indexes = [
            models.Index(fields=["slug"], name="company_slug_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class Role(models.Model):
    """Per-company role. Predefined vs custom catalogs is still §7 — no seed rows."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="roles"
    )
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "role"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="role_company_name_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="role_company_idx"),
        ]

    def __str__(self) -> str:
        return self.name


class ModulePermission(models.Model):
    """(module, can_view, can_action) per Role. module is a string key, not an enum."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="module_permissions"
    )
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="permissions"
    )
    module = models.CharField(max_length=64)
    can_view = models.BooleanField(default=False)
    can_action = models.BooleanField(default=False)

    class Meta:
        db_table = "module_permission"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "module"],
                name="modperm_role_module_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="modperm_company_idx"),
        ]


class SubUser(models.Model):
    """Company staff. The company owner is a SubUser with is_owner=True."""

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="subusers"
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="subusers",
        null=True,
        blank=True,
        help_text="Null allowed only for is_owner=True (implicit full access).",
    )
    is_owner = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subuser"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "phone"],
                name="subuser_company_phone_uniq",
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(is_owner=True),
                name="subuser_one_owner_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="subuser_company_idx"),
            models.Index(fields=["phone"], name="subuser_phone_idx"),
        ]

    def __str__(self) -> str:
        return self.name
