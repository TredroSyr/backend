"""View mixins for tenant-scoping and permissions."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework import permissions
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied

from apps.common.models import AuditLog
from apps.common.serializers import AuditLogSerializer
from core.responses import success_response

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


class ModuleScopedViewMixin(TenantScopedViewMixin):
    """Tenant scoping plus module permissions that follow the HTTP method.

    Reading a document needs `can_view` on its module; changing one needs
    `can_action`. Declaring the module once per viewset avoids the two attributes
    drifting apart, and matches the invoicing spec's rule (§6.7) that every
    document type is permissioned independently.
    """

    required_module: str = None

    @property
    def required_permission(self) -> str:
        method = getattr(self.request, "method", "GET")
        return "can_view" if method in permissions.SAFE_METHODS else "can_action"


class PaginatedListMixin:
    """Consistent, always-paginated list responses.

    Invoice and payment lists grow without bound, so list endpoints page by
    default rather than returning a whole table. The envelope matches the rest of
    the API: `{success, message, data: {<key>: [...], pagination: {...}}}`.
    """

    #: Key the rows appear under in `data`.
    list_key = "results"

    def paginated_response(
        self,
        queryset,
        *,
        serializer_class=None,
        key: str | None = None,
        message: str = "",
        extra: dict | None = None,
    ):
        serializer_class = serializer_class or self.get_serializer_class()
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset

        serializer = serializer_class(
            rows, many=True, context=self.get_serializer_context()
        )
        data = {key or self.list_key: serializer.data, **(extra or {})}

        if page is not None:
            paginator = self.paginator.page.paginator
            data["pagination"] = {
                "count": paginator.count,
                "page": self.paginator.page.number,
                "page_size": paginator.per_page,
                "total_pages": paginator.num_pages,
            }

        return success_response(data=data, message=message)


class CompanyContextMixin:
    """Exposes the authenticated company and passes it to serializers.

    Write serializers need the `Company` (not just its id) to scope product
    lookups and resolve catalog prices. The authenticator already loaded it onto
    the actor, so this costs no extra query.
    """

    @property
    def company(self):
        return self.request.user.company

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["company"] = self.company
        return context


class AuditHistoryMixin:
    """`GET {detail}/history/` — the document's immutable trail (§6.4)."""

    @action(detail=True, methods=["get"], url_path="history")
    def history(self, request, *args, **kwargs):
        document = self.get_object()
        entries = AuditLog.objects.filter(
            company_id=document.company_id,
            entity_type=document._meta.db_table,
            entity_id=document.pk,
        ).order_by("-created_at", "-id")

        return success_response(
            data={"history": AuditLogSerializer(entries, many=True).data}
        )
