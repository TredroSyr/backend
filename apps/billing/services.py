"""Billing and subscription services."""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from django.utils import timezone

from apps.billing.models import BillingInterval, Plan, Subscription, SubscriptionStatus

if TYPE_CHECKING:
    from apps.companies.models import Company


def get_default_plan() -> Plan:
    """
    Get the default plan for new company signups.
    
    Returns:
        Plan: The Free plan (or first active plan if Free doesn't exist)
    """
    try:
        return Plan.objects.get(name="Free", is_active=True)
    except Plan.DoesNotExist:
        # Fallback to any active plan
        return Plan.objects.filter(is_active=True).first()


def create_trial_subscription(company: Company, plan: Plan | None = None) -> Subscription:
    """
    Create a trial subscription for a new company.
    
    Args:
        company: The company to subscribe
        plan: The plan to subscribe to (defaults to Free plan)
    
    Returns:
        Subscription: The created subscription
    """
    if plan is None:
        plan = get_default_plan()
    
    if plan is None:
        raise ValueError("No active plan available for subscription")
    
    now = timezone.now()
    
    # Determine period based on billing interval
    if plan.billing_interval == BillingInterval.MONTHLY:
        period_days = 30
    elif plan.billing_interval == BillingInterval.YEARLY:
        period_days = 365
    else:
        period_days = 30  # Default to monthly
    
    subscription = Subscription.objects.create(
        company=company,
        plan=plan,
        status=SubscriptionStatus.ACTIVE,  # Free plan is immediately active
        current_period_start=now,
        current_period_end=now + timedelta(days=period_days),
    )
    
    return subscription


def upgrade_subscription(
    company: Company,
    new_plan: Plan,
    start_immediately: bool = True,
) -> Subscription:
    """
    Upgrade (or downgrade) a company's subscription to a new plan.
    
    Args:
        company: The company to upgrade
        new_plan: The new plan to subscribe to
        start_immediately: Whether to start the new subscription immediately
    
    Returns:
        Subscription: The new subscription
    """
    # Cancel existing subscription
    try:
        old_subscription = Subscription.objects.get(
            company=company,
            status__in=[
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
            ],
        )
        old_subscription.status = SubscriptionStatus.CANCELLED
        old_subscription.cancelled_at = timezone.now()
        old_subscription.save()
    except Subscription.DoesNotExist:
        pass  # No active subscription to cancel
    
    # Create new subscription
    now = timezone.now()
    
    if new_plan.billing_interval == BillingInterval.MONTHLY:
        period_days = 30
    elif new_plan.billing_interval == BillingInterval.YEARLY:
        period_days = 365
    else:
        period_days = 30
    
    if start_immediately:
        period_start = now
    else:
        # Start at end of current period if exists
        if old_subscription:
            period_start = old_subscription.current_period_end
        else:
            period_start = now
    
    subscription = Subscription.objects.create(
        company=company,
        plan=new_plan,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=period_start,
        current_period_end=period_start + timedelta(days=period_days),
    )
    
    return subscription


def cancel_subscription(company: Company) -> None:
    """
    Cancel a company's active subscription.
    
    Args:
        company: The company whose subscription to cancel
    """
    try:
        subscription = Subscription.objects.get(
            company=company,
            status__in=[
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
            ],
        )
        subscription.status = SubscriptionStatus.CANCELLED
        subscription.cancelled_at = timezone.now()
        subscription.save()
    except Subscription.DoesNotExist:
        pass  # No active subscription to cancel


def get_active_subscription(company: Company) -> Subscription | None:
    """
    Get the active subscription for a company.
    
    Args:
        company: The company to get subscription for
    
    Returns:
        Subscription or None: The active subscription, or None if no active subscription
    """
    try:
        return Subscription.objects.select_related("plan").get(
            company=company,
            status__in=[
                SubscriptionStatus.TRIALING,
                SubscriptionStatus.ACTIVE,
                SubscriptionStatus.PAST_DUE,
            ],
        )
    except Subscription.DoesNotExist:
        return None
