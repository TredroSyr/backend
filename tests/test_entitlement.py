"""Tests for the entitlement service."""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
from django.utils import timezone

from apps.billing.entitlement import EntitlementService, get_entitlement_service
from apps.billing.models import (
    BillingInterval,
    Plan,
    PlanFeature,
    PlanLimit,
    Subscription,
    SubscriptionStatus,
)
from apps.companies.models import Company, SubUser


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
    """Create a free plan with limits."""
    plan = Plan.objects.create(
        name="Free",
        price=0,
        billing_interval=BillingInterval.MONTHLY,
        is_active=True,
    )
    
    # Add limits
    PlanLimit.objects.create(plan=plan, resource_key="reps", max_value=5)
    PlanLimit.objects.create(plan=plan, resource_key="products", max_value=50)
    PlanLimit.objects.create(plan=plan, resource_key="subusers", max_value=3)
    PlanLimit.objects.create(plan=plan, resource_key="warehouses", max_value=2)
    
    # Add features
    PlanFeature.objects.create(plan=plan, feature_key="excel_import", enabled=False)
    PlanFeature.objects.create(
        plan=plan, feature_key="advanced_reports", enabled=False
    )
    
    return plan


@pytest.fixture
def pro_plan(db):
    """Create a pro plan with higher limits."""
    plan = Plan.objects.create(
        name="Pro",
        price=99.99,
        billing_interval=BillingInterval.MONTHLY,
        is_active=True,
    )
    
    # Add limits (higher than free)
    PlanLimit.objects.create(plan=plan, resource_key="reps", max_value=20)
    PlanLimit.objects.create(plan=plan, resource_key="products", max_value=500)
    PlanLimit.objects.create(plan=plan, resource_key="subusers", max_value=10)
    PlanLimit.objects.create(plan=plan, resource_key="warehouses", max_value=10)
    
    # Add features (all enabled)
    PlanFeature.objects.create(plan=plan, feature_key="excel_import", enabled=True)
    PlanFeature.objects.create(
        plan=plan, feature_key="advanced_reports", enabled=True
    )
    
    return plan


@pytest.fixture
def enterprise_plan(db):
    """Create an enterprise plan with unlimited resources."""
    plan = Plan.objects.create(
        name="Enterprise",
        price=499.99,
        billing_interval=BillingInterval.YEARLY,
        is_active=True,
    )
    
    # Add limits (NULL = unlimited)
    PlanLimit.objects.create(plan=plan, resource_key="reps", max_value=None)
    PlanLimit.objects.create(plan=plan, resource_key="products", max_value=None)
    PlanLimit.objects.create(plan=plan, resource_key="subusers", max_value=None)
    PlanLimit.objects.create(plan=plan, resource_key="warehouses", max_value=None)
    
    # Add all features
    PlanFeature.objects.create(plan=plan, feature_key="excel_import", enabled=True)
    PlanFeature.objects.create(
        plan=plan, feature_key="advanced_reports", enabled=True
    )
    
    return plan


@pytest.fixture
def active_subscription(company, free_plan):
    """Create an active subscription for the company."""
    now = timezone.now()
    return Subscription.objects.create(
        company=company,
        plan=free_plan,
        status=SubscriptionStatus.ACTIVE,
        current_period_start=now,
        current_period_end=now + timedelta(days=30),
    )


class TestEntitlementService:
    """Tests for EntitlementService class."""
    
    def test_service_creation(self, company):
        """Test that entitlement service can be created."""
        service = EntitlementService(company)
        assert service.company == company
    
    def test_factory_function(self, company):
        """Test the factory function."""
        service = get_entitlement_service(company)
        assert isinstance(service, EntitlementService)
        assert service.company == company
    
    def test_no_subscription(self, company):
        """Test behavior when company has no subscription."""
        service = EntitlementService(company)
        assert service.subscription is None
        assert service.plan is None
    
    def test_active_subscription(self, company, active_subscription):
        """Test that active subscription is found."""
        service = EntitlementService(company)
        assert service.subscription == active_subscription
        assert service.plan == active_subscription.plan
    
    def test_can_create_no_subscription(self, company):
        """Test that can_create denies when no subscription exists."""
        service = EntitlementService(company)
        result = service.can_create("reps")
        
        assert result.allowed is False
        assert "No active subscription" in result.message
    
    def test_can_create_within_limit(self, company, active_subscription):
        """Test that can_create allows when within limit."""
        service = EntitlementService(company)
        result = service.can_create("reps")
        
        assert result.allowed is True
        assert result.current == 0  # No reps created yet
        assert result.max_value == 5  # Free plan limit
    
    def test_can_create_at_limit(self, company, active_subscription, db):
        """Test that can_create denies when at limit."""
        from apps.reps.models import Rep
        
        # Create 5 reps (the limit)
        for i in range(5):
            Rep.objects.create(
                company=company,
                name=f"Rep {i}",
                phone=f"+96394412345{i}",
                password="hashed",
                referral_code=f"REF{i}",
            )
        
        service = EntitlementService(company)
        result = service.can_create("reps")
        
        assert result.allowed is False
        assert result.current == 5
        assert result.max_value == 5
        assert "limit reached" in result.message.lower()
    
    def test_can_create_unlimited(self, company, enterprise_plan):
        """Test that unlimited plans always allow creation."""
        # Create subscription with enterprise plan
        now = timezone.now()
        Subscription.objects.create(
            company=company,
            plan=enterprise_plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=365),
        )
        
        service = EntitlementService(company)
        result = service.can_create("reps")
        
        assert result.allowed is True
        assert result.max_value is None  # Unlimited
    
    def test_can_create_unknown_resource(self, company, active_subscription):
        """Test behavior for unknown resource type."""
        service = EntitlementService(company)
        result = service.can_create("unknown_resource")
        
        # Should default to unlimited for unknown resources
        assert result.allowed is True
        assert result.max_value is None
    
    def test_has_feature_disabled(self, company, active_subscription):
        """Test has_feature returns False for disabled features."""
        service = EntitlementService(company)
        
        # Free plan has excel_import disabled
        assert service.has_feature("excel_import") is False
        assert service.has_feature("advanced_reports") is False
    
    def test_has_feature_enabled(self, company, pro_plan):
        """Test has_feature returns True for enabled features."""
        # Create pro subscription
        now = timezone.now()
        Subscription.objects.create(
            company=company,
            plan=pro_plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        
        service = EntitlementService(company)
        
        assert service.has_feature("excel_import") is True
        assert service.has_feature("advanced_reports") is True
    
    def test_has_feature_unknown(self, company, active_subscription):
        """Test has_feature returns False for unknown features."""
        service = EntitlementService(company)
        assert service.has_feature("unknown_feature") is False
    
    def test_has_feature_no_subscription(self, company):
        """Test has_feature returns False when no subscription."""
        service = EntitlementService(company)
        assert service.has_feature("excel_import") is False
    
    def test_get_limit(self, company, active_subscription):
        """Test get_limit returns correct values."""
        service = EntitlementService(company)
        
        assert service.get_limit("reps") == 5
        assert service.get_limit("products") == 50
        assert service.get_limit("subusers") == 3
    
    def test_get_limit_unlimited(self, company, enterprise_plan):
        """Test get_limit returns None for unlimited resources."""
        now = timezone.now()
        Subscription.objects.create(
            company=company,
            plan=enterprise_plan,
            status=SubscriptionStatus.ACTIVE,
            current_period_start=now,
            current_period_end=now + timedelta(days=365),
        )
        
        service = EntitlementService(company)
        
        assert service.get_limit("reps") is None
        assert service.get_limit("products") is None
    
    def test_get_usage(self, company, active_subscription, db):
        """Test get_usage returns correct counts."""
        from apps.reps.models import Rep
        
        # Create 3 reps
        for i in range(3):
            Rep.objects.create(
                company=company,
                name=f"Rep {i}",
                phone=f"+96394412345{i}",
                password="hashed",
                referral_code=f"REF{i}",
            )
        
        service = EntitlementService(company)
        assert service.get_usage("reps") == 3
    
    def test_get_usage_subusers(self, company, active_subscription, db):
        """Test get_usage counts SubUsers correctly."""
        from apps.companies.models import Role, SubUser
        
        # Create 2 active subusers and 1 inactive
        SubUser.objects.create(
            company=company,
            name="User 1",
            phone="+963944123451",
            password="hashed",
            is_active=True,
        )
        SubUser.objects.create(
            company=company,
            name="User 2",
            phone="+963944123452",
            password="hashed",
            is_active=True,
        )
        SubUser.objects.create(
            company=company,
            name="User 3",
            phone="+963944123453",
            password="hashed",
            is_active=False,  # Inactive
        )
        
        service = EntitlementService(company)
        # Should only count active users
        assert service.get_usage("subusers") == 2
