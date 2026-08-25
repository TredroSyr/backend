"""Views for common app."""

from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from core.responses import success_response


class LocationsView(APIView):
    """
    GET /api/locations
    
    Get list of Syrian governorates and regions.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get locations list."""
        # Syrian governorates with their regions
        locations = [
            # {
            #     "governorate": "دمشق",
            #     "regions": [
            #         "المزة",
            #         "المالكي",
            #         "أبو رمانة",
            #         "القصاع",
            #         "المهاجرين",
            #         "الشاغور",
            #         "ساروجة",
            #         "ركن الدين",
            #         "القابون",
            #         "برزة",
            #         "دمر",
            #         "كفرسوسة",
            #     ],
            # },
            # {
            #     "governorate": "ريف دمشق",
            #     "regions": [
            #         "دوما",
            #         "الزبداني",
            #         "يبرود",
            #         "النبك",
            #         "القطيفة",
            #         "التل",
            #         "صيدنايا",
            #         "جرمانا",
            #         "عربين",
            #         "حرستا",
            #         "داريا",
            #         "المليحة",
            #         "القدم",
            #     ],
            # },
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
                    "مارع",
                    "أخترين",
                    "تل رفعت",
                    "دابق",
                    "سوران",
                    "الراعي",
                    "جنديرس",
                    "شران",
                    "الغندورة",
                    "حريتان",
                    "قباسين",
                ],
            },
            # {
            #     "governorate": "حمص",
            #     "regions": [
            #         "حمص المدينة",
            #         "تدمر",
            #         "الرستن",
            #         "القصير",
            #         "تلبيسة",
            #         "الحولة",
            #         "مخرم",
            #         "صدد",
            #     ],
            # },
            # {
            #     "governorate": "حماة",
            #     "regions": [
            #         "حماة المدينة",
            #         "السلمية",
            #         "المحردة",
            #         "صوران",
            #         "مصياف",
            #         "السقيلبية",
            #         "تل سلحب",
            #     ],
            # },
            # {
            #     "governorate": "اللاذقية",
            #     "regions": [
            #         "اللاذقية المدينة",
            #         "جبلة",
            #         "القرداحة",
            #         "الحفة",
            #     ],
            # },
            {
                "governorate": "طرطوس",
                "regions": [
                    "طرطوس المدينة",
                    "بانياس",
                    "دريكيش",
                    "الشيخ بدر",
                    "صافيتا",
                    "القدموس",
                    "مشتى الحلو",
                    "الصفصافة",
                    "حمام واصل",
                    "الريحانية",
                    "عين الزرقا",
                    "عين الشرقية",
                    "كفرون",
                    "الزهيرية",
                ],
            },
            # {
            #     "governorate": "إدلب",
            #     "regions": [
            #         "إدلب المدينة",
            #         "جسر الشغور",
            #         "أريحا",
            #         "معرة النعمان",
            #         "سراقب",
            #         "حارم",
            #     ],
            # },
            # {
            #     "governorate": "درعا",
            #     "regions": [
            #         "درعا المدينة",
            #         "إزرع",
            #         "الصنمين",
            #         "نوى",
            #         "الشيخ مسكين",
            #         "طفس",
            #     ],
            # },
            # {
            #     "governorate": "السويداء",
            #     "regions": [
            #         "السويداء المدينة",
            #         "صلخد",
            #         "شقا",
            #         "القريا",
            #         "المزرعة",
            #     ],
            # },
            # {
            #     "governorate": "القنيطرة",
            #     "regions": [
            #         "القنيطرة المدينة",
            #         "فيق",
            #         "خان أرنبة",
            #     ],
            # },
            # {
            #     "governorate": "دير الزور",
            #     "regions": [
            #         "دير الزور المدينة",
            #         "الميادين",
            #         "البوكمال",
            #         "القورية",
            #         "العشارة",
            #     ],
            # },
            # {
            #     "governorate": "الرقة",
            #     "regions": [
            #         "الرقة المدينة",
            #         "تل أبيض",
            #         "الثورة",
            #         "السبخة",
            #     ],
            # },
            # {
            #     "governorate": "الحسكة",
            #     "regions": [
            #         "الحسكة المدينة",
            #         "القامشلي",
            #         "رأس العين",
            #         "المالكية",
            #         "القحطانية",
            #         "الشدادي",
            #     ],
            # },
        ]
        
        return success_response(
            data={"locations": locations},
            status_code=status.HTTP_200_OK,
        )


class BusinessTypesView(APIView):
    """
    GET /api/business-types
    
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


class ModulesView(APIView):
    """
    GET /api/modules
    
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

class ApkVersionView(APIView):
    """
    GET /api/apk-version
    
    Get the latest APK version for update checking.
    """
    
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get the latest APK version."""
        return success_response(
            data={"version": 3},
            status_code=status.HTTP_200_OK,
        )