"""Views for rep-specific operations."""

from __future__ import annotations

from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.customers.models import Customer
from apps.customers.serializers import CustomerSerializer
from apps.reps.models import RepCustomerAssignment
from apps.reps.permissions import IsRep
from apps.reps.serializers import CustomerLocationWorkDaysUpdateSerializer
from core.responses import error_response, success_response


class RepCustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for reps to view and manage their assigned customers.
    
    Reps can:
    - List customers assigned to them
    - View customer details
    - Update customer location and work days
    - Filter by active status
    
    Endpoints:
    - GET /api/reps/customers - List assigned customers
    - GET /api/reps/customers/{id} - Get customer details
    - PATCH /api/reps/customers/{id} - Update customer location and work days
    - GET /api/reps/customers/stats - Get customer statistics
    """
    
    permission_classes = [IsAuthenticated, IsRep]
    serializer_class = CustomerSerializer
    http_method_names = ['get', 'patch', 'head', 'options']
    
    def get_queryset(self):
        """Return customers assigned to the authenticated rep."""
        # Get rep_id from token payload
        token_payload = getattr(self.request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        if not rep_id:
            return Customer.objects.none()
        
        # Get customers assigned to this rep
        return Customer.objects.filter(
            assigned_reps__id=rep_id
        ).prefetch_related("assigned_reps").distinct()
    
    def list(self, request, *args, **kwargs):
        """List all customers assigned to the rep."""
        queryset = self.get_queryset()
        
        # Optional filter by active status
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        # Optional search by name or phone
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search) | models.Q(phone__icontains=search)
            )
        
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={
                "customers": serializer.data,
                "total": queryset.count()
            },
            status_code=status.HTTP_200_OK,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get details of a specific customer."""
        # Check if customer is assigned to this rep
        instance = self.get_object()
        
        # Get rep_id from token payload
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        if not instance.assigned_reps.filter(id=rep_id).exists():
            return error_response(
                message="غير مصرح لك بالوصول إلى هذا العميل",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"customer": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """
        Update customer location and work days.
        
        PATCH /api/reps/customers/{id}/
        {
            "latitude": 33.513805,
            "longitude": 36.276527,
            "work_days": ["sunday", "monday", "tuesday"]
        }
        """
        customer = self.get_object()
        
        # Get rep_id from token payload
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        # Check if customer is assigned to this rep
        if not customer.assigned_reps.filter(id=rep_id).exists():
            return error_response(
                message="غير مصرح لك بتعديل هذا العميل",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Validate request data
        serializer = CustomerLocationWorkDaysUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        validated_data = serializer.validated_data
        
        # Update customer location if provided
        location_updated = False
        if 'latitude' in validated_data and 'longitude' in validated_data:
            customer.latitude = validated_data['latitude']
            customer.longitude = validated_data['longitude']
            customer.save(update_fields=['latitude', 'longitude', 'updated_at'])
            location_updated = True
        
        # Update work days for this assignment if provided
        work_days_updated = False
        if 'work_days' in validated_data:
            try:
                assignment = RepCustomerAssignment.objects.get(
                    rep_id=rep_id,
                    customer=customer
                )
                assignment.work_days = validated_data['work_days']
                assignment.save(update_fields=['work_days', 'updated_at'])
                work_days_updated = True
            except RepCustomerAssignment.DoesNotExist:
                return error_response(
                    message="التعيين غير موجود",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
        
        # Build response message
        updates = []
        if location_updated:
            updates.append("الموقع")
        if work_days_updated:
            updates.append("أيام العمل")
        
        message = f"تم تحديث {' و '.join(updates)} بنجاح" if updates else "لم يتم إجراء أي تحديث"
        
        return success_response(
            data={"customer": CustomerSerializer(customer).data},
            message=message,
            status_code=status.HTTP_200_OK,
        )
    
    @action(detail=False, methods=["get"], url_path="stats")
    def stats(self, request):
        """
        Get statistics about the rep's customers.
        
        GET /api/reps/customers/stats/
        
        Returns:
        {
            "total_customers": 50,
            "active_customers": 45,
            "inactive_customers": 5
        }
        """
        # Get rep_id from token payload
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        if not rep_id:
            return error_response(
                message="معلومات المندوب غير موجودة",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        base_queryset = Customer.objects.filter(assigned_reps__id=rep_id)
        
        stats = {
            "total_customers": base_queryset.count(),
            "active_customers": base_queryset.filter(is_active=True).count(),
            "inactive_customers": base_queryset.filter(is_active=False).count(),
        }
        
        return success_response(
            data=stats,
            status_code=status.HTTP_200_OK,
        )



class RepProfileViewSet(viewsets.ViewSet):
    """
    ViewSet for rep to view and update their own profile.
    
    Endpoints:
    - GET /api/reps/profile - Get rep's own profile
    - PATCH /api/reps/profile - Update rep's own work days
    """
    
    permission_classes = [IsAuthenticated, IsRep]
    
    def list(self, request):
        """
        Get rep's own profile information.
        
        GET /api/reps/profile/
        """
        from apps.reps.models import Rep
        
        # Get rep_id from token payload
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        if not rep_id:
            return error_response(
                message="معلومات المندوب غير موجودة",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        try:
            rep = Rep.objects.select_related('company').get(id=rep_id)
        except Rep.DoesNotExist:
            return error_response(
                message="المندوب غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        profile_data = {
            "id": rep.id,
            "name": rep.name,
            "phone": rep.phone,
            "referral_code": rep.referral_code,
            "work_days": rep.work_days,
            "is_active": rep.is_active,
            "company": {
                "id": rep.company.id,
                "name": rep.company.name,
            },
            "created_at": rep.created_at,
            "updated_at": rep.updated_at,
        }
        
        return success_response(
            data={"profile": profile_data},
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, pk=None):
        """
        Update rep's own work days.
        
        PATCH /api/reps/profile/
        {
            "work_days": ["sunday", "monday", "tuesday", "wednesday"]
        }
        """
        from apps.reps.models import Rep
        from apps.reps.serializers import RepCustomerAssignmentSerializer
        
        # Get rep_id from token payload
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        if not rep_id:
            return error_response(
                message="معلومات المندوب غير موجودة",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        try:
            rep = Rep.objects.get(id=rep_id)
        except Rep.DoesNotExist:
            return error_response(
                message="المندوب غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Validate work_days
        work_days = request.data.get('work_days')
        if work_days is None:
            return error_response(
                message="أيام العمل مطلوبة",
                errors={"work_days": ["يجب تقديم أيام العمل"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Use serializer for validation
        serializer = RepCustomerAssignmentSerializer(data={"rep_id": rep_id, "work_days": work_days})
        if not serializer.is_valid():
            return error_response(
                message="أيام العمل غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Update rep's work_days
        rep.work_days = serializer.validated_data['work_days']
        rep.save(update_fields=['work_days', 'updated_at'])
        
        return success_response(
            data={
                "profile": {
                    "id": rep.id,
                    "name": rep.name,
                    "work_days": rep.work_days,
                }
            },
            message="تم تحديث أيام العمل بنجاح",
            status_code=status.HTTP_200_OK,
        )
