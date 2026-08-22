"""Views for customer management by companies."""

from __future__ import annotations

from django.http import HttpResponse
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.customers.excel_import import generate_template, parse_excel_file
from apps.customers.models import Customer, CustomerCategory, CustomerCategoryAssignment
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
        
        # Optional filter by category (for current company)
        category_id = request.query_params.get("category_id")
        if category_id and company_id:
            # Filter customers that have this category assigned by the current company
            from apps.customers.models import CustomerCategoryAssignment
            customer_ids = CustomerCategoryAssignment.objects.filter(
                company_id=company_id,
                category_id=category_id
            ).values_list('customer_id', flat=True)
            queryset = queryset.filter(id__in=customer_ids)
        
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
    
    @action(detail=False, methods=["post"], url_path="bulk-action")
    def bulk_action(self, request):
        """
        Perform bulk actions on multiple customers.
        
        POST /api/companies/customers/bulk-action/
        {
            "action": "assign_rep" | "assign_category" | "remove_rep" | "remove_category" | "delete",
            "customer_ids": [1, 2, 3, ...],
            "rep_id": 123,  // required for assign_rep, remove_rep
            "category_id": 456  // required for assign_category, optional for remove_category (null = remove all)
        }
        
        Supported actions:
        - assign_rep: Assign a rep to multiple customers
        - assign_category: Assign a category to multiple customers
        - remove_rep: Remove a rep from multiple customers
        - remove_category: Remove category assignment from multiple customers
        - delete: Soft delete (deactivate) multiple customers
        
        Returns:
        {
            "success": true,
            "message": "تم تنفيذ العملية على 10 عملاء بنجاح",
            "data": {
                "total": 10,
                "successful": 10,
                "failed": 0,
                "failed_ids": []
            }
        }
        """
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="معلومات الشركة غير موجودة",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate request data
        action = request.data.get("action")
        customer_ids = request.data.get("customer_ids", [])
        
        if not action:
            return error_response(
                message="نوع العملية مطلوب",
                errors={"action": ["يجب تحديد نوع العملية"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        if not customer_ids or not isinstance(customer_ids, list):
            return error_response(
                message="قائمة العملاء مطلوبة",
                errors={"customer_ids": ["يجب تقديم قائمة من معرفات العملاء"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate customers exist
        customers = Customer.objects.filter(id__in=customer_ids, is_active=True)
        if customers.count() != len(customer_ids):
            return error_response(
                message="بعض العملاء غير موجودين",
                errors={"customer_ids": ["بعض العملاء غير موجودين أو غير نشطين"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Execute action based on type
        if action == "assign_rep":
            return self._bulk_assign_rep(request, customers, company_id)
        elif action == "assign_category":
            return self._bulk_assign_category(request, customers, company_id)
        elif action == "remove_rep":
            return self._bulk_remove_rep(request, customers, company_id)
        elif action == "remove_category":
            return self._bulk_remove_category(request, customers, company_id)
        elif action == "delete":
            return self._bulk_delete(request, customers)
        else:
            return error_response(
                message="نوع العملية غير صحيح",
                errors={"action": [f"العملية '{action}' غير مدعومة"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
    
    def _bulk_assign_rep(self, request, customers, company_id):
        """Assign a rep to multiple customers."""
        rep_id = request.data.get("rep_id")
        
        if not rep_id:
            return error_response(
                message="معرف المندوب مطلوب",
                errors={"rep_id": ["يجب تحديد معرف المندوب"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate rep exists and belongs to company
        from apps.reps.models import Rep
        
        try:
            rep = Rep.objects.get(id=rep_id, company_id=company_id, is_active=True)
        except Rep.DoesNotExist:
            return error_response(
                message="المندوب غير موجود",
                errors={"rep_id": ["المندوب غير موجود أو غير نشط في هذه الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Assign rep to all customers
        successful = 0
        failed = 0
        failed_ids = []
        
        for customer in customers:
            try:
                customer.assigned_reps.add(rep)
                successful += 1
            except Exception:
                failed += 1
                failed_ids.append(customer.id)
        
        return success_response(
            message=f"تم تعيين المندوب لـ {successful} عميل بنجاح",
            data={
                "total": len(customers),
                "successful": successful,
                "failed": failed,
                "failed_ids": failed_ids,
            },
            status_code=status.HTTP_200_OK,
        )
    
    def _bulk_assign_category(self, request, customers, company_id):
        """Assign a category to multiple customers."""
        category_id = request.data.get("category_id")
        
        if not category_id:
            return error_response(
                message="معرف التصنيف مطلوب",
                errors={"category_id": ["يجب تحديد معرف التصنيف"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate category exists and is available to company
        from django.db.models import Q
        
        category_exists = CustomerCategory.objects.filter(
            Q(company__isnull=True) | Q(company_id=company_id),
            id=category_id,
            is_active=True
        ).exists()
        
        if not category_exists:
            return error_response(
                message="التصنيف غير موجود",
                errors={"category_id": ["التصنيف غير موجود أو غير متاح"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Assign category to all customers
        successful = 0
        failed = 0
        failed_ids = []
        
        for customer in customers:
            try:
                customer.set_category_for_company(company_id, category_id)
                successful += 1
            except Exception:
                failed += 1
                failed_ids.append(customer.id)
        
        return success_response(
            message=f"تم تعيين التصنيف لـ {successful} عميل بنجاح",
            data={
                "total": len(customers),
                "successful": successful,
                "failed": failed,
                "failed_ids": failed_ids,
            },
            status_code=status.HTTP_200_OK,
        )
    
    def _bulk_remove_rep(self, request, customers, company_id):
        """Remove a rep from multiple customers."""
        rep_id = request.data.get("rep_id")
        
        if not rep_id:
            return error_response(
                message="معرف المندوب مطلوب",
                errors={"rep_id": ["يجب تحديد معرف المندوب"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate rep exists and belongs to company
        from apps.reps.models import Rep
        
        try:
            rep = Rep.objects.get(id=rep_id, company_id=company_id)
        except Rep.DoesNotExist:
            return error_response(
                message="المندوب غير موجود",
                errors={"rep_id": ["المندوب غير موجود في هذه الشركة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Remove rep from all customers
        successful = 0
        failed = 0
        failed_ids = []
        
        for customer in customers:
            try:
                customer.assigned_reps.remove(rep)
                successful += 1
            except Exception:
                failed += 1
                failed_ids.append(customer.id)
        
        return success_response(
            message=f"تم إزالة المندوب من {successful} عميل بنجاح",
            data={
                "total": len(customers),
                "successful": successful,
                "failed": failed,
                "failed_ids": failed_ids,
            },
            status_code=status.HTTP_200_OK,
        )
    
    def _bulk_remove_category(self, request, customers, company_id):
        """Remove category assignment from multiple customers."""
        # Category ID is optional - if not provided, remove all category assignments
        
        successful = 0
        failed = 0
        failed_ids = []
        
        for customer in customers:
            try:
                customer.remove_category_for_company(company_id)
                successful += 1
            except Exception:
                failed += 1
                failed_ids.append(customer.id)
        
        return success_response(
            message=f"تم إزالة التصنيف من {successful} عميل بنجاح",
            data={
                "total": len(customers),
                "successful": successful,
                "failed": failed,
                "failed_ids": failed_ids,
            },
            status_code=status.HTTP_200_OK,
        )
    
    def _bulk_delete(self, request, customers):
        """Soft delete (deactivate) multiple customers."""
        successful = 0
        failed = 0
        failed_ids = []
        
        for customer in customers:
            try:
                customer.is_active = False
                customer.save(update_fields=["is_active", "updated_at"])
                successful += 1
            except Exception:
                failed += 1
                failed_ids.append(customer.id)
        
        return success_response(
            message=f"تم تعطيل {successful} عميل بنجاح",
            data={
                "total": len(customers),
                "successful": successful,
                "failed": failed,
                "failed_ids": failed_ids,
            },
            status_code=status.HTTP_200_OK,
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


class CustomerCategoryViewSet(viewsets.ModelViewSet):
    """
    ViewSet for managing customer categories.
    
    Companies can:
    - List all available categories (global defaults + their custom categories)
    - Create custom categories for their company
    - Update their custom categories
    - Delete their custom categories (cannot modify global defaults)
    
    Endpoints:
    - GET /api/companies/customer-categories - List available categories
    - POST /api/companies/customer-categories - Create custom category
    - PATCH /api/companies/customer-categories/{id} - Update custom category
    - DELETE /api/companies/customer-categories/{id} - Delete custom category
    """
    
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete"]
    
    def get_queryset(self):
        """Return global defaults + company-specific categories."""
        company_id = getattr(self.request, "company_id", None)
        
        if not company_id:
            # Return only global defaults if no company context
            return CustomerCategory.objects.filter(company__isnull=True, is_active=True)
        
        # Return global defaults AND company-specific categories
        from django.db.models import Q
        return CustomerCategory.objects.filter(
            Q(company__isnull=True) | Q(company_id=company_id),
            is_active=True
        ).order_by("company_id", "name")  # Global first, then company-specific
    
    def list(self, request, *args, **kwargs):
        """List all available categories (global + company custom)."""
        queryset = self.get_queryset()
        
        categories_data = [
            {
                "id": cat.id,
                "name": cat.name,
                "is_global": cat.company_id is None,
                "is_custom": cat.company_id is not None,
                "created_at": cat.created_at,
            }
            for cat in queryset
        ]
        
        return success_response(
            data={"categories": categories_data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create a custom category for the company."""
        company_id = getattr(request, "company_id", None)
        
        if not company_id:
            return error_response(
                message="معلومات الشركة غير موجودة",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        name = request.data.get("name", "").strip()
        
        if not name:
            return error_response(
                message="اسم التصنيف مطلوب",
                errors={"name": ["اسم التصنيف مطلوب"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Check if category already exists for this company
        if CustomerCategory.objects.filter(company_id=company_id, name=name).exists():
            return error_response(
                message="هذا التصنيف موجود مسبقاً",
                errors={"name": ["يوجد تصنيف بنفس الاسم"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Create category
        category = CustomerCategory.objects.create(
            company_id=company_id,
            name=name,
            is_active=True
        )
        
        return success_response(
            data={
                "category": {
                    "id": category.id,
                    "name": category.name,
                    "is_global": False,
                    "is_custom": True,
                    "created_at": category.created_at,
                }
            },
            message="تم إنشاء التصنيف بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Update a custom category (only company-owned)."""
        company_id = getattr(request, "company_id", None)
        
        try:
            category = CustomerCategory.objects.get(pk=kwargs.get("pk"))
        except CustomerCategory.DoesNotExist:
            return error_response(
                message="التصنيف غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Cannot modify global categories
        if category.company_id is None:
            return error_response(
                message="لا يمكن تعديل التصنيفات الافتراضية",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Can only modify own company categories
        if category.company_id != company_id:
            return error_response(
                message="غير مصرح بتعديل هذا التصنيف",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        name = request.data.get("name", "").strip()
        
        if name and name != category.name:
            # Check for duplicate name
            if CustomerCategory.objects.filter(
                company_id=company_id, name=name
            ).exclude(pk=category.pk).exists():
                return error_response(
                    message="يوجد تصنيف آخر بنفس الاسم",
                    errors={"name": ["يوجد تصنيف آخر بنفس الاسم"]},
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            
            category.name = name
            category.save(update_fields=["name", "updated_at"])
        
        return success_response(
            data={
                "category": {
                    "id": category.id,
                    "name": category.name,
                    "is_global": False,
                    "is_custom": True,
                    "created_at": category.created_at,
                }
            },
            message="تم تحديث التصنيف بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete a custom category (only company-owned)."""
        company_id = getattr(request, "company_id", None)
        
        try:
            category = CustomerCategory.objects.get(pk=kwargs.get("pk"))
        except CustomerCategory.DoesNotExist:
            return error_response(
                message="التصنيف غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Cannot delete global categories
        if category.company_id is None:
            return error_response(
                message="لا يمكن حذف التصنيفات الافتراضية",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Can only delete own company categories
        if category.company_id != company_id:
            return error_response(
                message="غير مصرح بحذف هذا التصنيف",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Soft delete
        category.is_active = False
        category.save(update_fields=["is_active", "updated_at"])
        
        # Note: Customers with this category will have category=NULL due to SET_NULL
        
        return success_response(
            message="تم حذف التصنيف بنجاح",
            status_code=status.HTTP_200_OK,
        )
