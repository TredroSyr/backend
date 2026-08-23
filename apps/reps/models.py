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
    work_days = models.JSONField(
        default=list,
        help_text="Default work days for this rep (e.g., ['sunday', 'monday', 'tuesday'])",
    )
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


class RepCustomerAssignment(models.Model):
    """
    Through table for rep-customer assignments with work days.
    
    This replaces the direct ManyToMany relationship between Customer and Rep,
    allowing us to store per-assignment metadata like work_days.
    
    work_days can be:
    - Specific days for this customer (e.g., ['sunday', 'wednesday'])
    - Empty list [] means no work days assigned (customer not active for this rep)
    - None/null defaults to rep's work_days
    """

    rep = models.ForeignKey(
        "Rep",
        on_delete=models.CASCADE,
        related_name="customer_assignments",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.CASCADE,
        related_name="rep_assignments",
    )
    work_days = models.JSONField(
        default=list,
        help_text="Work days for this customer-rep assignment (e.g., ['sunday', 'monday'])",
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rep_customer_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["rep", "customer"],
                name="rep_customer_assignment_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["rep"], name="rep_cust_assign_rep_idx"),
            models.Index(fields=["customer"], name="rep_cust_assign_customer_idx"),
            models.Index(fields=["rep", "customer"], name="rep_cust_assign_both_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.rep.name} -> {self.customer.name}"
    
    def get_effective_work_days(self) -> list[str]:
        """Return work_days for this assignment, falling back to rep's default if empty."""
        return self.work_days if self.work_days else self.rep.work_days
