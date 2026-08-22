from __future__ import annotations

from django.db import models


class CustomerCategory(models.Model):
    """Customer category choices. Can be global defaults (company=NULL) or company-specific.
    
    Global defaults like 'تاجر جملة', 'تاجر مفرق' are seeded via migration.
    Each company can also define their own custom categories.
    """
    
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customer_categories",
        null=True,
        blank=True,
        help_text="NULL = global default category, otherwise company-specific"
    )
    name = models.CharField(max_length=100)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_category"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="customer_category_company_name_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="customer_category_company_idx"),
            models.Index(fields=["is_active"], name="customer_category_active_idx"),
        ]
        verbose_name_plural = "Customer Categories"

    def __str__(self) -> str:
        return self.name


class CustomerCategoryAssignment(models.Model):
    """
    Through table to track which category a company has assigned to a customer.
    
    Since customers are global but companies are separate tenants, the same customer
    can have different categories from different companies.
    
    Example:
    - Company A assigns customer #123 as "تاجر جملة"
    - Company B assigns the same customer #123 as "مطاعم"
    """
    
    customer = models.ForeignKey(
        "Customer",
        on_delete=models.CASCADE,
        related_name="category_assignments"
    )
    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customer_category_assignments"
    )
    category = models.ForeignKey(
        CustomerCategory,
        on_delete=models.CASCADE,
        related_name="assignments"
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer_category_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["customer", "company"],
                name="customer_category_assignment_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "company"], name="cust_cat_assign_cust_comp_idx"),
            models.Index(fields=["company"], name="cust_cat_assign_company_idx"),
            models.Index(fields=["category"], name="cust_cat_assign_category_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.customer.name} - {self.company.name}: {self.category.name}"


class Customer(models.Model):
    """Global entity — no company_id. Registers once; orders from any company.

    Customer can be created manually by a company (no password set) or can sign up
    themselves. If created manually first, they can complete signup later by setting
    password without conflict.
    
    assigned_reps is a many-to-many relationship allowing customer to be assigned
    to multiple reps from different companies.
    
    referral_code_used tracks the original referral code used during signup for
    attribution/analytics, separate from assigned_reps which can be changed by admin.
    
    Categories are tracked per company via CustomerCategoryAssignment.
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
        ]

    def __str__(self) -> str:
        return self.name
    
    def has_completed_signup(self) -> bool:
        """Check if customer has completed signup by setting password."""
        return bool(self.password)
    
    def can_complete_signup(self) -> bool:
        """Check if customer can complete signup (no password set yet)."""
        return not self.password
    
    def get_category_for_company(self, company_id: int):
        """Get the category assigned by a specific company."""
        try:
            assignment = self.category_assignments.select_related('category').get(
                company_id=company_id
            )
            return assignment.category
        except CustomerCategoryAssignment.DoesNotExist:
            return None
    
    def set_category_for_company(self, company_id: int, category_id: int):
        """Set or update the category for a specific company."""
        assignment, created = CustomerCategoryAssignment.objects.update_or_create(
            customer=self,
            company_id=company_id,
            defaults={'category_id': category_id}
        )
        return assignment
    
    def remove_category_for_company(self, company_id: int):
        """Remove category assignment for a specific company."""
        self.category_assignments.filter(company_id=company_id).delete()
