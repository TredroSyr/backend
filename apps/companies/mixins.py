"""View mixins for tenant-scoping and permissions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework.exceptions import PermissionDenied

if TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest


class TenantScopedViewMixin:
    """
    Mixin for views that ensures all queries are scoped to the authenticated user's company.
    Automatically filters querysets by company_id from the JWT token.
    """
    
    def get_queryset(self) -> QuerySet:
        """
        Override to automatically filter by company_id.
        Views should call super().get_queryset() to get tenant-scoped queryset.
        """
        queryset = super().get_queryset()
        
        # Get company_id from request (set by TenantScopingMiddleware)
        company_id = getattr(self.request, "company_id", None)
        
        if company_id is None:
            # No company_id means unauthenticated request
            # Return empty queryset for safety
            return queryset.none()
        
        # Filter by company_id if the model has this field
        if hasattr(queryset.model, "company_id"):
            return queryset.filter(company_id=company_id)
        elif hasattr(queryset.model, "company"):
            return queryset.filter(company=company_id)
        
        # If model doesn't have company field, return as-is
        # (e.g., Company model itself, or global entities like Customer)
        return queryset
    
    def get_company_id(self) -> int | None:
        """Get the company_id from the authenticated request."""
        return getattr(self.request, "company_id", None)
    
    def ensure_company_access(self, obj) -> None:
        """
        Ensure the authenticated user has access to the given object.
        Raises PermissionDenied if object belongs to different company.
        """
        company_id = self.get_company_id()
        
        if company_id is None:
            raise PermissionDenied("Authentication required")
        
        # Check if object belongs to the user's company
        obj_company_id = None
        if hasattr(obj, "company_id"):
            obj_company_id = obj.company_id
        elif hasattr(obj, "company"):
            obj_company_id = obj.company.id if obj.company else None
        
        if obj_company_id and obj_company_id != company_id:
            raise PermissionDenied("Access denied to this resource")


class OwnerRequiredMixin:
    """
    Mixin that requires the authenticated user to be a company owner.
    """
    
    def check_owner_permission(self) -> None:
        """Check if the authenticated user is a company owner."""
        is_owner = getattr(self.request, "is_owner", False)
        
        if not is_owner:
            raise PermissionDenied("Only company owners can perform this action")
    
    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Override dispatch to check owner permission."""
        self.check_owner_permission()
        return super().dispatch(request, *args, **kwargs)


class ModulePermissionMixin:
    """
    Mixin that checks module-level permissions (can_view, can_action).
    Views should set `required_module` and `required_permission` attributes.
    """
    
    required_module: str = None  # e.g., "products", "orders"
    required_permission: str = "can_view"  # "can_view" or "can_action"
    
    def check_module_permission(self) -> None:
        """Check if the user has the required module permission."""
        if not self.required_module:
            # No module requirement set, allow access
            return
        
        # Owners have full access
        is_owner = getattr(self.request, "is_owner", False)
        if is_owner:
            return
        
        # For staff, check their role permissions
        # This will be implemented when we add permission checking in views
        # For now, we'll load permissions from the request if available
        permissions = getattr(self.request, "user_permissions", {})
        module_perm = permissions.get(self.required_module, {})
        
        has_permission = module_perm.get(self.required_permission, False)
        
        if not has_permission:
            raise PermissionDenied(
                f"You don't have permission to {self.required_permission} {self.required_module}"
            )
    
    def dispatch(self, request: HttpRequest, *args, **kwargs):
        """Override dispatch to check module permission."""
        self.check_module_permission()
        return super().dispatch(request, *args, **kwargs)
