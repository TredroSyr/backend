"""Views for company management and onboarding."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.companies.models import Company, SubUser
from apps.companies.serializers import (
    CompanyOnboardingSerializer,
    CompanySerializer,
    CreateSubUserSerializer,
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


class CompanyLocationsView(APIView):
    """
    GET /api/companies/locations
    
    Get list of Syrian governorates and regions.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get locations list."""
        # Syrian governorates with their regions
        locations = [
            {
                "governorate": "دمشق",
                "regions": [
                    "المزة",
                    "المالكي",
                    "أبو رمانة",
                    "القصاع",
                    "المهاجرين",
                    "الشاغور",
                    "ساروجة",
                    "ركن الدين",
                    "القابون",
                    "برزة",
                    "دمر",
                    "كفرسوسة",
                ],
            },
            {
                "governorate": "ريف دمشق",
                "regions": [
                    "دوما",
                    "الزبداني",
                    "يبرود",
                    "النبك",
                    "القطيفة",
                    "التل",
                    "صيدنايا",
                    "جرمانا",
                    "عربين",
                    "حرستا",
                    "داريا",
                    "المليحة",
                    "القدم",
                ],
            },
            {
                "governorate": "حلب",
                "regions": [
                    "حلب المدينة",
                    "منبج",
                    "عفرين",
                    "جرابلس",
                    "إعزاز",
                    "الباب",
                    "عين العرب",
                    "السفيرة",
                    "اعزاز",
                ],
            },
            {
                "governorate": "حمص",
                "regions": [
                    "حمص المدينة",
                    "تدمر",
                    "الرستن",
                    "القصير",
                    "تلبيسة",
                    "الحولة",
                    "مخرم",
                    "صدد",
                ],
            },
            {
                "governorate": "حماة",
                "regions": [
                    "حماة المدينة",
                    "السلمية",
                    "المحردة",
                    "صوران",
                    "مصياف",
                    "السقيلبية",
                    "تل سلحب",
                ],
            },
            {
                "governorate": "اللاذقية",
                "regions": [
                    "اللاذقية المدينة",
                    "جبلة",
                    "القرداحة",
                    "الحفة",
                ],
            },
            {
                "governorate": "طرطوس",
                "regions": [
                    "طرطوس المدينة",
                    "بانياس",
                    "دريكيش",
                    "الشيخ بدر",
                    "صافيتا",
                ],
            },
            {
                "governorate": "إدلب",
                "regions": [
                    "إدلب المدينة",
                    "جسر الشغور",
                    "أريحا",
                    "معرة النعمان",
                    "سراقب",
                    "حارم",
                ],
            },
            {
                "governorate": "درعا",
                "regions": [
                    "درعا المدينة",
                    "إزرع",
                    "الصنمين",
                    "نوى",
                    "الشيخ مسكين",
                    "طفس",
                ],
            },
            {
                "governorate": "السويداء",
                "regions": [
                    "السويداء المدينة",
                    "صلخد",
                    "شقا",
                    "القريا",
                    "المزرعة",
                ],
            },
            {
                "governorate": "القنيطرة",
                "regions": [
                    "القنيطرة المدينة",
                    "فيق",
                    "خان أرنبة",
                ],
            },
            {
                "governorate": "دير الزور",
                "regions": [
                    "دير الزور المدينة",
                    "الميادين",
                    "البوكمال",
                    "القورية",
                    "العشارة",
                ],
            },
            {
                "governorate": "الرقة",
                "regions": [
                    "الرقة المدينة",
                    "تل أبيض",
                    "الثورة",
                    "السبخة",
                ],
            },
            {
                "governorate": "الحسكة",
                "regions": [
                    "الحسكة المدينة",
                    "القامشلي",
                    "رأس العين",
                    "المالكية",
                    "القحطانية",
                    "الشدادي",
                ],
            },
        ]
        
        return success_response(
            data={"locations": locations},
            status_code=status.HTTP_200_OK,
        )


class CompanyBusinessTypesView(APIView):
    """
    GET /api/companies/business-types
    
    Get list of available business types.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get business types list."""
        # Business types from Company model choices
        business_types = [
            {"value": "food_products", "label": "مواد غذائية"},
            {"value": "electronics", "label": "إلكترونيات"},
            {"value": "cosmetics", "label": "مستحضرات تجميل"},
            {"value": "medical_supplies", "label": "أدوية ومستلزمات طبية"},
            {"value": "home_tools", "label": "أدوات منزلية"},
            {"value": "clothing", "label": "ألبسة"},
        ]
        
        return success_response(
            data={"business_types": business_types},
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


class ModuleListView(APIView):
    """
    GET /api/companies/modules
    
    Get list of available modules for permission assignment.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get available modules."""
        modules = [
            {
                "value": "customers",
                "label": "العملاء",
                "label_en": "Customers",
            },
            {
                "value": "invoices",
                "label": "الفواتير",
                "label_en": "Invoices",
            },
            {
                "value": "orders",
                "label": "الطلبات",
                "label_en": "Orders",
            },
            {
                "value": "products",
                "label": "المنتجات",
                "label_en": "Products",
            },
            {
                "value": "reps",
                "label": "المندوبين",
                "label_en": "Representatives",
            },
            {
                "value": "notifications",
                "label": "الإشعارات",
                "label_en": "Notifications",
            },
        ]
        
        return success_response(
            data={"modules": modules},
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
