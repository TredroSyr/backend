"""Views for company management and onboarding."""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.companies.mixins import TenantScopedViewMixin
from apps.companies.models import Company, SubUser
from apps.reps.models import Rep
from apps.companies.serializers import (
    CompanyOnboardingSerializer,
    CompanySerializer,
    CreateSubUserSerializer,
    RepListSerializer,
    RepSerializer,
    SubUserDetailSerializer,
)
from core.responses import error_response, success_response


class CompanyOnboardingView(APIView):
    """
    POST /api/companies/onboarding
    
    Complete company onboarding in one step. All fields are optional.
    Users can skip onboarding and complete it later via company profile.
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Handle company onboarding."""
        # Get company from authenticated user
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="لم يتم العثور على معلومات الشركة",
                errors={"company": ["يجب أن تكون مسجلاً كمستخدم شركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return error_response(
                message="الشركة غير موجودة",
                errors={"company": ["لم يتم العثور على الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Validate and update company data
        serializer = CompanyOnboardingSerializer(
            company,
            data=request.data,
            partial=True,  # Allow partial updates
        )
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Save the onboarding data
        serializer.save()
        
        # Return updated company data
        return success_response(
            data={"company": CompanySerializer(company).data},
            message="تم حفظ بيانات الشركة بنجاح",
            status_code=status.HTTP_200_OK,
        )


class CompanyOnboardingStatusView(APIView):
    """
    GET /api/companies/onboarding/status
    
    Get the onboarding status for the current company.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get onboarding status."""
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="لم يتم العثور على معلومات الشركة",
                errors={"company": ["يجب أن تكون مسجلاً كمستخدم شركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return error_response(
                message="الشركة غير موجودة",
                errors={"company": ["لم يتم العثور على الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Return onboarding status
        return success_response(
            data={
                "onboarding_completed": company.onboarding_completed,
                "company": CompanySerializer(company).data,
            },
            status_code=status.HTTP_200_OK,
        )


class SubUserCreateView(APIView):
    """
    POST /api/companies/subusers
    
    Create a new sub-user with module permissions.
    Only company owner can create sub-users.
    
    Request body:
    {
        "name": "User Name",
        "phone": "0912345678",
        "email": "user@example.com",  # optional
        "password": "secure_password",
        "permissions": [
            {
                "module": "customers",
                "can_view": true,
                "can_action": false
            },
            {
                "module": "orders",
                "can_view": true,
                "can_action": true
            }
        ]
    }
    """
    
    permission_classes = [IsAuthenticated]
    
    def post(self, request):
        """Create a new sub-user."""
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="لم يتم العثور على معلومات الشركة",
                errors={"company": ["يجب أن تكون مسجلاً كمستخدم شركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return error_response(
                message="الشركة غير موجودة",
                errors={"company": ["لم يتم العثور على الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Check if the current user is the company owner
        subuser_id = getattr(request, "subuser_id", None)
        if subuser_id:
            try:
                current_user = SubUser.objects.get(id=subuser_id, company=company)
                if not current_user.is_owner:
                    return error_response(
                        message="غير مصرح",
                        errors={"permission": ["فقط مالك الشركة يمكنه إضافة مستخدمين فرعيين"]},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )
            except SubUser.DoesNotExist:
                return error_response(
                    message="المستخدم غير موجود",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
        
        # Create the sub-user
        serializer = CreateSubUserSerializer(
            data=request.data,
            context={"company": company},
        )
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        sub_user = serializer.save()
        
        # Return the created sub-user with permissions
        return success_response(
            data={"subuser": SubUserDetailSerializer(sub_user).data},
            message="تم إنشاء المستخدم الفرعي بنجاح",
            status_code=status.HTTP_201_CREATED,
        )


class SubUserListView(APIView):
    """
    GET /api/companies/subusers
    
    List all sub-users for the company with their permissions.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """List all sub-users."""
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="لم يتم العثور على معلومات الشركة",
                errors={"company": ["يجب أن تكون مسجلاً كمستخدم شركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return error_response(
                message="الشركة غير موجودة",
                errors={"company": ["لم يتم العثور على الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Get all sub-users for this company
        subusers = SubUser.objects.filter(company=company).select_related("role")
        
        return success_response(
            data={"subusers": SubUserDetailSerializer(subusers, many=True).data},
            status_code=status.HTTP_200_OK,
        )


class SubUserDetailView(APIView):
    """
    PATCH /api/companies/subusers/<id>
    DELETE /api/companies/subusers/<id>
    
    Update or delete a sub-user.
    Only company owner can perform these actions.
    Owner cannot be deleted or modified through this endpoint.
    """
    
    permission_classes = [IsAuthenticated]
    
    def _get_company_and_check_owner(self, request):
        """Helper to get company and verify ownership."""
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return None, error_response(
                message="لم يتم العثور على معلومات الشركة",
                errors={"company": ["يجب أن تكون مسجلاً كمستخدم شركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        try:
            company = Company.objects.get(id=company_id)
        except Company.DoesNotExist:
            return None, error_response(
                message="الشركة غير موجودة",
                errors={"company": ["لم يتم العثور على الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Check if the current user is the company owner
        subuser_id = getattr(request, "subuser_id", None)
        if subuser_id:
            try:
                current_user = SubUser.objects.get(id=subuser_id, company=company)
                if not current_user.is_owner:
                    return None, error_response(
                        message="غير مصرح",
                        errors={"permission": ["فقط مالك الشركة يمكنه تعديل أو حذف المستخدمين الفرعيين"]},
                        status_code=status.HTTP_403_FORBIDDEN,
                    )
            except SubUser.DoesNotExist:
                return None, error_response(
                    message="المستخدم غير موجود",
                    status_code=status.HTTP_404_NOT_FOUND,
                )
        
        return company, None
    
    def patch(self, request, subuser_id):
        """Update sub-user details and permissions."""
        from apps.companies.serializers import UpdateSubUserSerializer
        
        company, error = self._get_company_and_check_owner(request)
        if error:
            return error
        
        # Get the sub-user to update
        try:
            sub_user = SubUser.objects.get(id=subuser_id, company=company)
        except SubUser.DoesNotExist:
            return error_response(
                message="المستخدم الفرعي غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Cannot modify the owner through this endpoint
        if sub_user.is_owner:
            return error_response(
                message="غير مصرح",
                errors={"permission": ["لا يمكن تعديل حساب المالك"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Update the sub-user
        serializer = UpdateSubUserSerializer(
            sub_user,
            data=request.data,
            partial=True,
            context={"company": company},
        )
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        sub_user = serializer.save()
        
        return success_response(
            data={"subuser": SubUserDetailSerializer(sub_user).data},
            message="تم تحديث المستخدم الفرعي بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def delete(self, request, subuser_id):
        """Delete a sub-user."""
        company, error = self._get_company_and_check_owner(request)
        if error:
            return error
        
        # Get the sub-user to delete
        try:
            sub_user = SubUser.objects.get(id=subuser_id, company=company)
        except SubUser.DoesNotExist:
            return error_response(
                message="المستخدم الفرعي غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Cannot delete the owner
        if sub_user.is_owner:
            return error_response(
                message="غير مصرح",
                errors={"permission": ["لا يمكن حذف حساب المالك"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Delete the sub-user (role will be kept for audit purposes)
        sub_user.delete()
        
        return success_response(
            message="تم حذف المستخدم الفرعي بنجاح",
            status_code=status.HTTP_200_OK,
        )



class RepViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing company reps.
    
    Provides CRUD operations for sales representatives:
    - GET /api/companies/reps - List all reps for the company
    - POST /api/companies/reps - Create a new rep
    - GET /api/companies/reps/{id} - Get rep details
    - PATCH /api/companies/reps/{id} - Update rep details
    - PUT /api/companies/reps/{id} - Full update of rep
    - DELETE /api/companies/reps/{id} - Delete a rep
    """
    
    permission_classes = [IsAuthenticated]
    queryset = Rep.objects.all()
    
    def get_serializer_class(self):
        """Use different serializers for list vs detail operations."""
        if self.action == "list":
            return RepListSerializer
        return RepSerializer
    
    def get_serializer_context(self):
        """Add company to serializer context."""
        context = super().get_serializer_context()
        company_id = getattr(self.request, "company_id", None)
        
        if company_id:
            try:
                context["company"] = Company.objects.get(id=company_id)
            except Company.DoesNotExist:
                pass
        
        return context
    
    def list(self, request, *args, **kwargs):
        """List all reps for the company."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"reps": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create a new rep."""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        rep = serializer.save()
        
        return success_response(
            data={"rep": RepListSerializer(rep).data},
            message="تم إضافة المندوب بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get rep details."""
        instance = self.get_object()
        serializer = RepListSerializer(instance)
        
        return success_response(
            data={"rep": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Full update of rep details."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        rep = serializer.save()
        
        return success_response(
            data={"rep": RepListSerializer(rep).data},
            message="تم تحديث بيانات المندوب بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update of rep details."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete a rep."""
        instance = self.get_object()
        instance.delete()
        
        return success_response(
            message="تم حذف المندوب بنجاح",
            status_code=status.HTTP_200_OK,
        )
