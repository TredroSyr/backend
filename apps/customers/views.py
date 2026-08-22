"""Views for customer management by companies."""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.customers.excel_import import generate_template, parse_excel_file
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
    - Create new customers manually (without password)
    - View customer details
    - Update customer info (including assigning to their reps)
    - Soft delete (deactivate) customers
    
    Note: Password is only set by customer during signup, not by company.
    
    Endpoints:
    - GET /api/companies/customers - List all customers
    - POST /api/companies/customers - Create a new customer
    - GET /api/companies/customers/{id} - Get customer details
    - PATCH /api/companies/customers/{id} - Update customer
    - PUT /api/companies/customers/{id} - Full update
    - DELETE /api/companies/customers/{id} - Deactivate customer
    - POST /api/companies/customers/{id}/assign-reps - Assign customer to reps
    - POST /api/companies/customers/{id}/remove-reps - Remove rep assignments
    """
    
    permission_classes = [IsAuthenticated]
    queryset = Customer.objects.prefetch_related("assigned_reps").all()
    
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
        
        # Optional filter by assigned to any rep from current company
        company_id = getattr(request, "company_id", None)
        if company_id and request.query_params.get("my_company_only") == "true":
            queryset = queryset.filter(assigned_reps__company_id=company_id).distinct()
        
        # Optional filter by category
        category = request.query_params.get("category")
        if category:
            queryset = queryset.filter(category__iexact=category)
        
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"customers": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create a new customer (without password - company created)."""
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
    
    @action(detail=True, methods=["post"], url_path="assign-reps")
    def assign_reps(self, request, pk=None):
        """
        Assign customer to one or more reps from the authenticated company.
        
        POST /api/companies/customers/{id}/assign-reps
        {
            "rep_ids": [123, 456]
        }
        """
        customer = self.get_object()
        rep_ids = request.data.get("rep_ids", [])
        
        if not rep_ids or not isinstance(rep_ids, list):
            return error_response(
                message="قائمة معرفات المندوبين مطلوبة",
                errors={"rep_ids": ["يجب تقديم قائمة من معرفات المندوبين"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate reps belong to company and are active
        from apps.reps.models import Rep
        
        company_id = getattr(request, "company_id", None)
        
        reps = Rep.objects.filter(
            id__in=rep_ids,
            company_id=company_id,
            is_active=True
        )
        
        if reps.count() != len(rep_ids):
            return error_response(
                message="بعض المندوبين غير موجودين",
                errors={"rep_ids": ["بعض المندوبين غير موجودين أو غير نشطين في هذه الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Add reps to customer (doesn't remove existing)
        customer.assigned_reps.add(*reps)
        
        return success_response(
            data={"customer": CustomerSerializer(customer).data},
            message="تم تعيين المندوبين للعميل بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    @action(detail=True, methods=["post"], url_path="remove-reps")
    def remove_reps(self, request, pk=None):
        """
        Remove rep assignments from customer for the authenticated company.
        
        POST /api/companies/customers/{id}/remove-reps
        {
            "rep_ids": [123, 456]  // optional, removes all company reps if not provided
        }
        """
        customer = self.get_object()
        rep_ids = request.data.get("rep_ids")
        
        company_id = getattr(request, "company_id", None)
        
        if rep_ids:
            # Remove specific reps
            if not isinstance(rep_ids, list):
                return error_response(
                    message="قائمة معرفات المندوبين يجب أن تكون قائمة",
                    errors={"rep_ids": ["يجب أن تكون قائمة"]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            
            from apps.reps.models import Rep
            reps = Rep.objects.filter(
                id__in=rep_ids,
                company_id=company_id
            )
            customer.assigned_reps.remove(*reps)
        else:
            # Remove all reps from this company
            company_reps = customer.assigned_reps.filter(company_id=company_id)
            customer.assigned_reps.remove(*company_reps)
        
        return success_response(
            data={"customer": CustomerSerializer(customer).data},
            message="تم إزالة تعيين المندوبين بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    @action(detail=False, methods=["get"], url_path="download-template")
    def download_template(self, request):
        """
        Download Excel template for bulk customer import.
        
        GET /api/companies/customers/download-template/
        
        Returns an Excel file with:
        - Predefined columns with Arabic headers
        - Sample data rows
        - Notes sheet with instructions
        """
        try:
            excel_file = generate_template()
            
            response = HttpResponse(
                excel_file.getvalue(),
                content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
            response["Content-Disposition"] = 'attachment; filename="customers_import_template.xlsx"'
            
            return response
            
        except Exception as e:
            return error_response(
                message="فشل في إنشاء القالب",
                errors={"template": [str(e)]},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
    
    @action(detail=False, methods=["post"], url_path="import-excel")
    def import_excel(self, request):
        """
        Import customers from Excel file with partial success handling.
        
        POST /api/companies/customers/import-excel/
        Content-Type: multipart/form-data
        
        Request:
        - file: Excel file upload
        
        Response:
        {
            "success": true,
            "message": "تم استيراد 45 عميل بنجاح، فشل 5",
            "data": {
                "total_rows": 50,
                "successful": 45,
                "failed": 5,
                "created_customers": [
                    {"id": 1, "name": "أحمد", "phone": "+963991234567", "row": 2},
                    ...
                ],
                "errors": [
                    {
                        "row": 3,
                        "data": {"name": "", "phone": "123"},
                        "errors": {
                            "name": ["الاسم مطلوب"],
                            "phone": ["رقم الهاتف غير صحيح"]
                        }
                    },
                    ...
                ]
            }
        }
        
        Note: Process continues even when individual rows fail.
        Returns both successful imports and detailed errors for failed rows.
        """
        # Validate file upload
        if "file" not in request.FILES:
            return error_response(
                message="يرجى رفع ملف Excel",
                errors={"file": ["ملف Excel مطلوب"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        file = request.FILES["file"]
        
        # Validate file extension
        if not file.name.endswith((".xlsx", ".xls")):
            return error_response(
                message="صيغة الملف غير صحيحة",
                errors={"file": ["يجب أن يكون الملف بصيغة Excel (.xlsx أو .xls)"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Get company_id from request context
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="معلومات الشركة غير موجودة",
                errors={"company": ["لا يمكن تحديد الشركة"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Process Excel file
        try:
            results = parse_excel_file(file, company_id)
            
            # Determine response status
            if results["successful"] == 0 and results["failed"] > 0:
                # All failed
                return error_response(
                    message=f"فشل استيراد جميع الصفوف ({results['failed']} صف)",
                    errors={"import": ["جميع الصفوف فشلت في التحقق"], "details": results},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            elif results["successful"] > 0 and results["failed"] == 0:
                # All succeeded
                return success_response(
                    message=f"تم استيراد {results['successful']} عميل بنجاح",
                    data=results,
                    status_code=status.HTTP_201_CREATED,
                )
            else:
                # Partial success
                return success_response(
                    message=f"تم استيراد {results['successful']} عميل بنجاح، فشل {results['failed']} صف",
                    data=results,
                    status_code=status.HTTP_207_MULTI_STATUS,
                )
        
        except Exception as e:
            return error_response(
                message="فشل في معالجة الملف",
                errors={"file": [f"خطأ غير متوقع: {str(e)}"]},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
