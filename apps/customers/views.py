"""Views for customer management by companies."""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.customers.models import Customer
from apps.customers.serializers import (
    CustomerCreateSerializer,
    CustomerListSerializer,
    CustomerSerializer,
    CustomerUpdateSerializer,
)
from core.responses import error_response, success_response


class CustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for company managing customers.
    
    Customers are global entities (not tenant-scoped), but companies can:
    - List all customers
    - Create new customers manually
    - View customer details
    - Update customer info (including assigning to their reps)
    - Soft delete (deactivate) customers
    
    Endpoints:
    - GET /api/companies/customers - List all customers
    - POST /api/companies/customers - Create a new customer
    - GET /api/companies/customers/{id} - Get customer details
    - PATCH /api/companies/customers/{id} - Update customer
    - PUT /api/companies/customers/{id} - Full update
    - DELETE /api/companies/customers/{id} - Deactivate customer
    - POST /api/companies/customers/{id}/assign-rep - Assign customer to rep
    """
    
    permission_classes = [IsAuthenticated]
    queryset = Customer.objects.select_related("assigned_rep").all()
    
    def get_serializer_class(self):
        """Use different serializers for different actions."""
        if self.action == "list":
            return CustomerListSerializer
        elif self.action == "create":
            return CustomerCreateSerializer
        elif self.action in ["update", "partial_update"]:
            return CustomerUpdateSerializer
        return CustomerSerializer
    
    def get_serializer_context(self):
        """Add company_id to serializer context for validation."""
        context = super().get_serializer_context()
        context["company_id"] = getattr(self.request, "company_id", None)
        return context
    
    def list(self, request, *args, **kwargs):
        """List all customers with optional filtering."""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Optional filter by active status
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        # Optional filter by assigned rep from current company
        company_id = getattr(request, "company_id", None)
        if company_id and request.query_params.get("my_company_only") == "true":
            queryset = queryset.filter(assigned_rep__company_id=company_id)
        
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"customers": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create a new customer."""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        customer = serializer.save()
        
        return success_response(
            data={"customer": CustomerSerializer(customer).data},
            message="تم إضافة العميل بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get customer details."""
        instance = self.get_object()
        serializer = CustomerSerializer(instance)
        
        return success_response(
            data={"customer": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Full or partial update of customer details."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        customer = serializer.save()
        
        return success_response(
            data={"customer": CustomerSerializer(customer).data},
            message="تم تحديث بيانات العميل بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update of customer details."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete - deactivate customer instead of hard delete."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        
        return success_response(
            message="تم تعطيل العميل بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    @action(detail=True, methods=["post"], url_path="assign-rep")
    def assign_rep(self, request, pk=None):
        """
        Assign customer to a rep from the authenticated company.
        
        POST /api/companies/customers/{id}/assign-rep
        {
            "rep_id": 123
        }
        """
        customer = self.get_object()
        rep_id = request.data.get("rep_id")
        
        if not rep_id:
            return error_response(
                message="معرف المندوب مطلوب",
                errors={"rep_id": ["هذا الحقل مطلوب"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate rep belongs to company and is active
        from apps.reps.models import Rep
        
        company_id = getattr(request, "company_id", None)
        
        try:
            rep = Rep.objects.get(id=rep_id, company_id=company_id, is_active=True)
        except Rep.DoesNotExist:
            return error_response(
                message="المندوب غير موجود",
                errors={"rep_id": ["المندوب غير موجود أو غير نشط في هذه الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        customer.assigned_rep = rep
        customer.save(update_fields=["assigned_rep", "updated_at"])
        
        return success_response(
            data={"customer": CustomerSerializer(customer).data},
            message="تم تعيين المندوب للعميل بنجاح",
            status_code=status.HTTP_200_OK,
        )
