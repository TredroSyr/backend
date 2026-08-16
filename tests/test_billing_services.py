"""Tests for billing services."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.billing.models import (
    BillingInterval,
    Plan,
    Subscription,
    SubscriptionStatus,
)
from apps.billing.services import (
    cancel_subscription,
    create_trial_subscription,
    get_active_subscription,
    get_default_plan,
    upgrade_subscription,
)
from apps.companies.models import Company


@pytest.fixture
def company(db):
    """Create a test company."""
    return Company.objects.create(
        name="Test Company",
        slug="test-company",
        currency="SYP",
    )


@pytest.fixture
def free_plan(db):
    """Create a free plan."""
    return Plan.objects.create(
        name="Free",
        price=0,
        billing_interval=BillingInterval.MONTHLY,
        is_active=True,
    )


@pytest.fixture
def pro_plan(db):
    """Create a pro plan."""
    return Plan.objects.create(
        name="Pro",
        price=99.99,
        billing_interval=BillingInterval.MONTHLY,
        is_active=True,
    )


class TestGetDefaultPlan:
    """Tests for get_default_plan function."""
    
    def test_get_default_plan_exists(self, free_plan):
        """Test that Free plan is returned when it exists."""
        plan = get_default_plan()
        assert plan == free_plan
        assert plan.name == "Free"
    
    def test_get_default_plan_fallback(self, pro_plan):
        """Test fallback to any active plan if Free doesn't exist."""
        plan = get_default_plan()
        assert plan == pro_plan


class TestCreateTrialSubscription:
    """Tests for create_trial_subscription function."""
    
    def test_create_subscription_with_default_plan(self, company, free_plan):
        """Test creating subscription with default plan."""
        subscription = create_trial_subscription(company)
        
        assert subscription.company == company
        assert subscription.plan == free_plan
        assert subscription.status == SubscriptionStatus.ACTIVE
        assert subscription.current_period_start is not None
        assert subscription.current_period_end is not None
    
    def test_create_subscription_with_specific_plan(self, company, pro_plan):
        """Test creating subscription with a specific plan."""
        subscription = create_trial_subscription(company, plan=pro_plan)
        
        assert subscription.company == company
        assert subscription.plan == pro_plan
        assert subscription.status == SubscriptionStatus.ACTIVE
    
    def test_subscription_period_monthly(self, company, free_plan):
        """Test that monthly subscriptions have 30-day period."""
        subscription = create_trial_subscription(company, plan=free_plan)
        
        period_length = subscription.current_period_end - subscription.current_period_start
        assert period_length.days == 30
    
    def test_subscription_period_yearly(self, company, db):
        """Test that yearly subscriptions have 365-day period."""
        yearly_plan = Plan.objects.create(
            name="Yearly",
            price=999.99,
            billing_interval=BillingInterval.YEARLY,
            is_active=True,
        )
        
        subscription = create_trial_subscription(company, plan=yearly_plan)
        
        period_length = subscription.current_period_end - subscription.current_period_start
        assert period_length.days == 365
    
    def test_create_subscription_no_plan_raises(self, company, db):
        """Test that error is raised when no active plan exists."""
        with pytest.raises(ValueError, match="No active plan available"):
            create_trial_subscription(company)


class TestGetActiveSubscription:
    """Tests for get_active_subscription function."""
    
    def test_get_active_subscription_exists(self, company, free_plan):
        """Test getting an active subscription."""
        subscription = create_trial_subscription(company, plan=free_plan)
        
        retrieved = get_active_subscription(company)
        assert retrieved == subscription
        assert retrieved.plan == free_plan
    
    def test_get_active_subscription_none(self, company):
        """Test that None is returned when no active subscription."""
        result = get_active_subscription(company)
        assert result is None
    
    def test_get_active_subscription_ignores_cancelled(self, company, free_plan):
        """Test that cancelled subscriptions are not returned."""
        now = timezone.now()
        Subscription.objects.create(
            company=company,
            plan=free_plan,
            status=SubscriptionStatus.CANCELLED,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancelled_at=now,
        )
        
        result = get_active_subscription(company)
        assert result is None


class TestUpgradeSubscription:
    """Tests for upgrade_subscription function."""
    
    def test_upgrade_from_free_to_pro(self, company, free_plan, pro_plan):
        """Test upgrading from Free to Pro plan."""
        # Create initial free subscription
        old_subscription = create_trial_subscription(company, plan=free_plan)
        
        # Upgrade to pro
        new_subscription = upgrade_subscription(company, pro_plan)
        
        assert new_subscription.company == company
        assert new_subscription.plan == pro_plan
        assert new_subscription.status == SubscriptionStatus.ACTIVE
        
        # Old subscription should be cancelled
        old_subscription.refresh_from_db()
        assert old_subscription.status == SubscriptionStatus.CANCELLED
        assert old_subscription.cancelled_at is not None
    
    def test_upgrade_without_existing_subscription(self, company, pro_plan):
        """Test upgrading when no existing subscription exists."""
        new_subscription = upgrade_subscription(company, pro_plan)
        
        assert new_subscription.company == company
        assert new_subscription.plan == pro_plan
        assert new_subscription.status == SubscriptionStatus.ACTIVE
    
    def test_upgrade_immediate_vs_delayed(self, company, free_plan, pro_plan):
        """Test immediate vs delayed upgrade start."""
        # Create initial subscription
        create_trial_subscription(company, plan=free_plan)
        
        # Immediate upgrade
        immediate_sub = upgrade_subscription(company, pro_plan, start_immediately=True)
        now = timezone.now()
        
        # Should start immediately (within a few seconds)
        time_diff = (immediate_sub.current_period_start - now).total_seconds()
        assert abs(time_diff) < 5  # Within 5 seconds


class TestCancelSubscription:
    """Tests for cancel_subscription function."""
    
    def test_cancel_active_subscription(self, company, free_plan):
        """Test cancelling an active subscription."""
        subscription = create_trial_subscription(company, plan=free_plan)
        
        cancel_subscription(company)
        
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.CANCELLED
        assert subscription.cancelled_at is not None
    
    def test_cancel_no_subscription(self, company):
        """Test that cancelling with no subscription doesn't raise error."""
        # Should not raise any exception
        cancel_subscription(company)
    
    def test_cancel_already_cancelled(self, company, free_plan):
        """Test cancelling an already cancelled subscription."""
        now = timezone.now()
        subscription = Subscription.objects.create(
            company=company,
            plan=free_plan,
            status=SubscriptionStatus.CANCELLED,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
            cancelled_at=now,
        )
        
        # Should not raise any exception
        cancel_subscription(company)
        
        # Status should remain cancelled
        subscription.refresh_from_db()
        assert subscription.status == SubscriptionStatus.CANCELLED
