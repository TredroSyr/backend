"""Entitlement service for checking SaaS plan limits and features."""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import Count, Q

from apps.billing.models import SubscriptionStatus

if TYPE_CHECKING:
    from apps.billing.models import Plan, Subscription
    from apps.companies.models import Company


class EntitlementCheckResult:
    """Result of an entitlement check."""
    
    def __init__(
        self,
        allowed: bool,
        current: int | None = None,
        max_value: int | None = None,
        message: str = "",
    ):
        self.allowed = allowed
        self.current = current
        self.max_value = max_value
        self.message = message
    
    def __bool__(self) -> bool:
        """Allow using the result in boolean context."""
        return self.allowed
    
    def __repr__(self) -> str:
        return (
            f"EntitlementCheckResult(allowed={self.allowed}, "
            f"current={self.current}, max={self.max_value})"
        )


class EntitlementService:
    """
    Service for checking SaaS plan entitlements.
    
    Core principle: Never hardcode plan names or tier checks in business logic.
    Always resolve through PlanLimit/PlanFeature lookups.
    """
    
    def __init__(self, company: Company):
        """Initialize entitlement service for a company."""
        self.company = company
        self._subscription = None
        self._plan = None
    
    @property
    def subscription(self) -> Subscription | None:
        """Get the company's active subscription (cached)."""
        if self._subscription is None:
            from apps.billing.models import Subscription
            
            try:
                self._subscription = Subscription.objects.select_related("plan").get(
                    company=self.company,
                    status__in=[
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAST_DUE,
                    ],
                )
            except Subscription.DoesNotExist:
                return None
        
        return self._subscription
    
    @property
    def plan(self) -> Plan | None:
        """Get the company's current plan (cached)."""
        if self._plan is None and self.subscription:
            self._plan = self.subscription.plan
        return self._plan
    
    def can_create(self, resource_key: str) -> EntitlementCheckResult:
        """
        Check if the company can create a new instance of a resource.
        
        Args:
            resource_key: e.g., 'reps', 'products', 'subusers', 'warehouses'
        
        Returns:
            EntitlementCheckResult with allowed status and current/max counts
        """
        if not self.plan:
            # No active subscription - deny by default
            return EntitlementCheckResult(
                allowed=False,
                message="No active subscription found",
            )
        
        # Get the limit for this resource
        try:
            limit = self.plan.limits.get(resource_key=resource_key)
            max_value = limit.max_value
        except Exception:
            # No limit defined = unlimited by default
            max_value = None
        
        # Count current usage
        current_count = self._count_resource(resource_key)
        
        # Check if limit is reached
        if max_value is None:
            # Unlimited
            return EntitlementCheckResult(
                allowed=True,
                current=current_count,
                max_value=None,
                message="",
            )
        
        if current_count >= max_value:
            return EntitlementCheckResult(
                allowed=False,
                current=current_count,
                max_value=max_value,
                message=f"Maximum {resource_key} limit reached ({max_value})",
            )
        
        return EntitlementCheckResult(
            allowed=True,
            current=current_count,
            max_value=max_value,
            message="",
        )
    
    def has_feature(self, feature_key: str) -> bool:
        """
        Check if the company has access to a specific feature.
        
        Args:
            feature_key: e.g., 'excel_import', 'advanced_reports', 'multi_warehouse'
        
        Returns:
            bool: True if feature is enabled for the company's plan
        """
        if not self.plan:
            # No active subscription - deny by default
            return False
        
        try:
            feature = self.plan.features.get(feature_key=feature_key)
            return feature.enabled
        except Exception:
            # Feature not defined = disabled by default
            return False
    
    def get_limit(self, resource_key: str) -> int | None:
        """
        Get the maximum limit for a resource.
        
        Returns:
            int: The maximum value, or None for unlimited
        """
        if not self.plan:
            return 0
        
        try:
            limit = self.plan.limits.get(resource_key=resource_key)
            return limit.max_value
        except Exception:
            return None  # Unlimited
    
    def get_usage(self, resource_key: str) -> int:
        """
        Get current usage count for a resource.
        
        Args:
            resource_key: e.g., 'reps', 'products', 'subusers', 'warehouses'
        
        Returns:
            int: Current count of resources
        """
        return self._count_resource(resource_key)
    
    def _count_resource(self, resource_key: str) -> int:
        """
        Count current usage of a resource for the company.
        
        This method queries the database to get actual counts.
        """
        # Map resource keys to model counts
        if resource_key == "reps":
            from apps.reps.models import Rep
            return Rep.objects.filter(company=self.company, is_active=True).count()
        
        elif resource_key == "products":
            from apps.products.models import Product
            return Product.objects.filter(company=self.company).count()
        
        elif resource_key == "subusers":
            from apps.companies.models import SubUser
            return SubUser.objects.filter(company=self.company, is_active=True).count()
        
        elif resource_key == "warehouses":
            from apps.products.models import Warehouse
            return Warehouse.objects.filter(company=self.company).count()
        
        elif resource_key == "customers":
            # Customers are global, but we might limit per-company assignments
            # For now, return 0 (unlimited)
            return 0
        
        else:
            # Unknown resource type
            return 0


def get_entitlement_service(company: Company) -> EntitlementService:
    """Factory function to get entitlement service for a company."""
    return EntitlementService(company)


def require_entitlement(resource_key: str):
    """
    Decorator that checks entitlement before allowing resource creation.
    
    Usage:
        @require_entitlement('reps')
        def create_rep(company_id, ...):
            ...
    """
    def decorator(func):
        def wrapper(*args, **kwargs):
            # Extract company from arguments (typically first arg or in kwargs)
            company = None
            if args and hasattr(args[0], "company"):
                company = args[0].company
            elif "company" in kwargs:
                company = kwargs["company"]
            elif "company_id" in kwargs:
                from apps.companies.models import Company
                company = Company.objects.get(id=kwargs["company_id"])
            
            if company is None:
                raise ValueError("Company not found for entitlement check")
            
            # Check entitlement
            service = get_entitlement_service(company)
            result = service.can_create(resource_key)
            
            if not result.allowed:
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied(
                    result.message or f"Plan limit reached for {resource_key}"
                )
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator
