"""Views for common lookup data (global reference tables)."""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.models import Currency, UnitOfMeasure
from apps.common.modules import module_choices
from apps.common.serializers import CurrencySerializer, UnitOfMeasureSerializer
from core.responses import success_response


class UnitOfMeasureViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for UnitOfMeasure lookup data.
    
    These are global predefined units that companies pick from.
    No company scoping needed - this is reference data.
    
    Endpoints:
    - GET /api/units-of-measure/ - List all active units
    - GET /api/units-of-measure/{id}/ - Get specific unit details
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = UnitOfMeasureSerializer
    queryset = UnitOfMeasure.objects.all()
    
    def get_queryset(self):
        """Return active units, optionally all if requested."""
        queryset = super().get_queryset()
        
        # Filter by is_active unless explicitly requesting all
        show_all = self.request.query_params.get("show_all", "false").lower() == "true"
        if not show_all:
            queryset = queryset.filter(is_active=True)
        
        return queryset.order_by("name")
    
    def list(self, request, *args, **kwargs):
        """List all units of measure."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"units": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get specific unit of measure."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"unit": serializer.data},
            status_code=status.HTTP_200_OK,
        )


class CurrencyViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for Currency lookup data.
    
    These are global predefined currencies (ISO 4217) that companies pick from.
    No company scoping needed - this is reference data.
    
    Endpoints:
    - GET /api/currencies/ - List all active currencies
    - GET /api/currencies/{id}/ - Get specific currency details
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = CurrencySerializer
    queryset = Currency.objects.all()
    
    def get_queryset(self):
        """Return active currencies, optionally all if requested."""
        queryset = super().get_queryset()
        
        # Filter by is_active unless explicitly requesting all
        show_all = self.request.query_params.get("show_all", "false").lower() == "true"
        if not show_all:
            queryset = queryset.filter(is_active=True)
        
        return queryset.order_by("code")
    
    def list(self, request, *args, **kwargs):
        """List all currencies."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"currencies": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get specific currency."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"currency": serializer.data},
            status_code=status.HTTP_200_OK,
        )



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
        return success_response(
            data={"modules": module_choices()},
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