"""Views for company management and onboarding."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.companies.models import Company
from apps.companies.serializers import CompanyOnboardingSerializer, CompanySerializer
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
