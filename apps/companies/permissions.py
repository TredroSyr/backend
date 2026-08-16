"""Permission classes and decorators for role-based access control."""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable

from rest_framework import permissions
from rest_framework.exceptions import PermissionDenied

if TYPE_CHECKING:
    from django.http import HttpRequest
    from rest_framework.request import Request
    from rest_framework.views import APIView


class IsOwner(permissions.BasePermission):
    """Permission class that checks if the user is a company owner."""
    
    message = "Only company owners can perform this action."
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if the authenticated user is a company owner."""
        return getattr(request, "is_owner", False)


class IsSubUser(permissions.BasePermission):
    """Permission class that checks if the user is a SubUser (company staff)."""
    
    message = "This action requires company user authentication."
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if the authenticated user is a SubUser."""
        return getattr(request, "actor_type", None) == "subuser"


class IsRep(permissions.BasePermission):
    """Permission class that checks if the user is a Rep."""
    
    message = "This action requires sales representative authentication."
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if the authenticated user is a Rep."""
        return getattr(request, "actor_type", None) == "rep"


class IsCustomer(permissions.BasePermission):
    """Permission class that checks if the user is a Customer."""
    
    message = "This action requires customer authentication."
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if the authenticated user is a Customer."""
        return getattr(request, "actor_type", None) == "customer"


class HasModulePermission(permissions.BasePermission):
    """
    Permission class that checks module-level permissions.
    Views should set `required_module` and `required_permission` attributes.
    """
    
    def has_permission(self, request: Request, view: APIView) -> bool:
        """Check if the user has the required module permission."""
        # Get required module and permission from view
        required_module = getattr(view, "required_module", None)
        required_permission = getattr(view, "required_permission", "can_view")
        
        if not required_module:
            # No module requirement, allow access
            return True
        
        # Owners have full access
        is_owner = getattr(request, "is_owner", False)
        if is_owner:
            return True
        
        # Only SubUsers have module permissions (not Reps or Customers)
        actor_type = getattr(request, "actor_type", None)
        if actor_type != "subuser":
            return False
        
        # Check user's module permissions
        user_permissions = getattr(request, "user_permissions", {})
        module_perm = user_permissions.get(required_module, {})
        
        has_permission = module_perm.get(required_permission, False)
        
        if not has_permission:
            self.message = (
                f"You don't have permission to {required_permission} {required_module}"
            )
            return False
        
        return True


def require_module_permission(module: str, permission: str = "can_view"):
    """
    Decorator that checks if the user has a specific module permission.
    
    Usage:
        @require_module_permission("products", "can_action")
        def create_product(request):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(request: HttpRequest, *args, **kwargs):
            # Owners have full access
            is_owner = getattr(request, "is_owner", False)
            if is_owner:
                return func(request, *args, **kwargs)
            
            # Check module permission
            user_permissions = getattr(request, "user_permissions", {})
            module_perm = user_permissions.get(module, {})
            has_permission = module_perm.get(permission, False)
            
            if not has_permission:
                raise PermissionDenied(
                    f"You don't have permission to {permission} {module}"
                )
            
            return func(request, *args, **kwargs)
        
        return wrapper
    return decorator


def owner_required(func: Callable) -> Callable:
    """
    Decorator that requires the user to be a company owner.
    
    Usage:
        @owner_required
        def delete_company(request):
            ...
    """
    @wraps(func)
    def wrapper(request: HttpRequest, *args, **kwargs):
        is_owner = getattr(request, "is_owner", False)
        
        if not is_owner:
            raise PermissionDenied("Only company owners can perform this action")
        
        return func(request, *args, **kwargs)
    
    return wrapper


def load_user_permissions_middleware(get_response):
    """
    Middleware that loads user permissions from the database and attaches them to the request.
    This runs after TenantScopingMiddleware and JWT authentication.
    """
    def middleware(request: HttpRequest):
        # Only load permissions for authenticated SubUsers
        actor_type = getattr(request, "actor_type", None)
        
        if actor_type == "subuser":
            # Import here to avoid circular imports
            from apps.authentication.utils import get_permissions_for_subuser
            from apps.companies.models import SubUser
            
            # Get user_id from token
            token_payload = getattr(request, "token_payload", {})
            user_id = token_payload.get("user_id")
            
            if user_id:
                try:
                    subuser = SubUser.objects.select_related("role").get(id=user_id)
                    permissions = get_permissions_for_subuser(subuser)
                    request.user_permissions = permissions
                    request.subuser = subuser
                except SubUser.DoesNotExist:
                    request.user_permissions = {}
                    request.subuser = None
            else:
                request.user_permissions = {}
                request.subuser = None
        else:
            request.user_permissions = {}
            request.subuser = None
        
        response = get_response(request)
        return response
    
    return middleware
