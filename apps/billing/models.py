from __future__ import annotations

from django.db import models
from django.db.models import Q


class BillingInterval(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELLED = "cancelled", "Cancelled"


class Plan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_interval = models.CharField(max_length=16, choices=BillingInterval.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "plan"

    def __str__(self) -> str:
        return self.name


class PlanLimit(models.Model):
    """Generic numeric cap. Adding a newly-limited resource is a row, not a migration.

    max_value NULL = unlimited.
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="limits")
    resource_key = models.CharField(max_length=64)
    max_value = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "plan_limit"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "resource_key"],
                name="plan_limit_plan_res_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["resource_key"], name="plan_limit_res_key_idx"),
        ]


class PlanFeature(models.Model):
    """Generic boolean feature gate. Same shape as PlanLimit."""

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="features")
    feature_key = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "plan_feature"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "feature_key"],
                name="plan_feat_plan_feat_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["feature_key"], name="plan_feat_feat_key_idx"),
        ]


class Subscription(models.Model):
    """Company subscription instance, decoupled from the Plan catalog.

    Historical rows are kept. At most one non-cancelled subscription per company.
    Billing-provider IDs omitted — §7. No downgrade/grace schema — §7.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="subscriptions",
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(max_length=16, choices=SubscriptionStatus.choices)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription"
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(
                    status__in=[
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAST_DUE,
                    ]
                ),
                name="sub_one_current_per_company",
            ),
        ]
        indexes = [
            models.Index(
                fields=["company", "status"], name="sub_company_status_idx"
            ),
            models.Index(fields=["current_period_end"], name="sub_period_end_idx"),
        ]
