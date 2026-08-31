"""Views for rep-specific operations."""

from __future__ import annotations

from django.db import models
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.companies.mixins import PaginatedListMixin
from apps.customers.models import Customer
from apps.customers.serializers import CustomerSerializer
from apps.invoices.serializers import ReturnInvoiceSerializer, SalesInvoiceSerializer
from apps.products.models import Product, ProductWarehouseStock
from apps.products.services.images import primary_image_prefetch
from apps.products.services.pricing import general_prices_by_product
from apps.reps.models import RepCustomerAssignment
from apps.reps.permissions import IsRep
from apps.reps.serializers import (
    MY_ASSIGNMENTS_ATTR,
    CustomerLocationWorkDaysUpdateSerializer,
    RepCustomerSerializer,
    RepInventoryItemSerializer,
    RepProductSerializer,
)
from apps.reps.services.customers import customer_balances
from apps.reps.services.dashboard import (
    parse_period,
    parse_preview_limit,
    rep_dashboard,
)
from apps.reps.services.inventory import rep_warehouse, van_stock_queryset, van_totals
from core.responses import decimal_string, error_response, success_response


class RepCustomerViewSet(viewsets.ModelViewSet):
    """
    ViewSet for reps to view and manage their assigned customers.
    
    Reps can:
    - List customers assigned to them
    - View customer details
    - Create new customers (automatically assigned to them)
    - Update customer location and work days
    - Filter by active status
    
    Each row carries what the stores screen shows beside the name: the address,
    the days this rep visits, and the store's running balance with this rep —
    invoiced, paid, still due. The balances are a rollup of the rep's own sales
    invoices, aggregated for the whole page in one query rather than per row.

    Endpoints:
    - GET /api/reps/customers - List assigned customers
    - POST /api/reps/customers - Create a new customer
    - GET /api/reps/customers/{id} - Get customer details
    - PATCH /api/reps/customers/{id} - Update customer address, location and work days
    - GET /api/reps/customers/stats - Get customer statistics
    """
    
    permission_classes = [IsAuthenticated, IsRep]
    serializer_class = RepCustomerSerializer
    http_method_names = ['get', 'post', 'patch', 'head', 'options']
    
    @property
    def rep_id(self):
        return getattr(self.request, "token_payload", {}).get("rep_id")
    
    def get_queryset(self):
        """Return customers assigned to the authenticated rep."""
        rep_id = self.rep_id
        
        if not rep_id:
            return Customer.objects.none()
        
        # This rep's own assignment is prefetched into `my_assignments` so the
        # work-day badge on every row costs no query of its own; `rep` comes
        # along because the fallback to the rep's default days reads it.
        return Customer.objects.filter(
            assigned_reps__id=rep_id
        ).prefetch_related(
            "assigned_reps",
            models.Prefetch(
                "rep_assignments",
                queryset=RepCustomerAssignment.objects.filter(
                    rep_id=rep_id
                ).select_related("rep"),
                to_attr=MY_ASSIGNMENTS_ATTR,
            ),
        ).distinct()
    
    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["rep_id"] = self.rep_id
        return context
    
    def balances_for(self, customers):
        """The money rollup for the rows about to be rendered, in one query."""
        return customer_balances(
            self.request.company_id,
            self.rep_id,
            customer_ids=[customer.id for customer in customers],
        )
    
    def list(self, request, *args, **kwargs):
        """List all customers assigned to the rep."""
        queryset = self.get_queryset()
        
        # Optional filter by active status
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        # Optional search by name, phone or address
        search = request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(phone__icontains=search)
                | models.Q(address__icontains=search)
            )
        
        # Optional filter to one visiting day — "today's route".
        #
        # Resolved through `get_effective_work_days` rather than a JSON query, so
        # the fallback to the rep's default days is the model's one definition of
        # that rule instead of a second copy that can drift from the badge each
        # row prints. One small query: a rep has assignments in the hundreds.
        work_day = request.query_params.get("work_day")
        if work_day:
            day = work_day.strip().lower()
            matching = [
                assignment.customer_id
                for assignment in RepCustomerAssignment.objects.filter(
                    rep_id=self.rep_id
                ).select_related("rep")
                if day in assignment.get_effective_work_days()
            ]
            queryset = queryset.filter(id__in=matching)
        
        customers = list(queryset)
        serializer = self.get_serializer(
            customers, many=True, context={
                **self.get_serializer_context(),
                "balances": self.balances_for(customers),
            }
        )
        
        return success_response(
            data={
                "customers": serializer.data,
                "total": len(customers)
            },
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """
        Create a new customer for the rep's company and auto-assign to this rep.
        
        POST /api/reps/customers/
        {
            "name": "أحمد محمد",
            "phone": "+963991234567",
            "email": "ahmed@example.com",  // optional
            "latitude": 33.513805,  // optional
            "longitude": 36.276527,  // optional
            "work_days": ["sunday", "monday", "tuesday"]  // optional, defaults to rep's work_days
        }
        """
        from apps.customers.serializers import CustomerCreateSerializer
        from apps.reps.models import Rep, RepCustomerAssignment
        
        # Get rep and company info from token
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        company_id = token_payload.get("company_id")
        
        if not rep_id or not company_id:
            return error_response(
                message="معلومات المندوب أو الشركة غير موجودة",
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Verify rep exists and is active
        try:
            rep = Rep.objects.get(id=rep_id, company_id=company_id, is_active=True)
        except Rep.DoesNotExist:
            return error_response(
                message="المندوب غير موجود أو غير نشط",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Extract work_days from request (optional)
        work_days = request.data.get("work_days", [])
        
        # Validate work_days if provided
        if work_days:
            serializer_validator = CustomerLocationWorkDaysUpdateSerializer(data={"work_days": work_days})
            if not serializer_validator.is_valid():
                return error_response(
                    message="أيام العمل غير صالحة",
                    errors=serializer_validator.errors,
                    status_code=status.HTTP_400_BAD_REQUEST,
                )
            work_days = serializer_validator.validated_data["work_days"]
        
        # Prepare customer data (remove work_days as it's not part of Customer model)
        customer_data = {k: v for k, v in request.data.items() if k != "work_days"}
        
        # Use the company's CustomerCreateSerializer for validation
        serializer = CustomerCreateSerializer(
            data=customer_data,
            context={"company_id": company_id}
        )
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Create customer (without assigned_rep_ids to handle manually)
        validated_data = serializer.validated_data.copy()
        validated_data.pop('assigned_rep_ids', None)
        validated_data.pop('category', None)  # Reps can't assign categories
        
        customer = Customer.objects.create(**validated_data)
        
        # Automatically assign to this rep with specified work_days
        RepCustomerAssignment.objects.create(
            rep=rep,
            customer=customer,
            work_days=work_days
        )
        
        return success_response(
            data={"customer": self.get_serializer(customer).data},
            message="تم إضافة العميل بنجاح وتعيينه لك",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get details of a specific customer.

        The store page's three header cards — إجمالي الفواتير / المدفوع /
        المتبقي — are `total_invoiced`, `paid_amount` and `balance_due` on the
        customer itself, the same fields the list row carries. The tabs below
        them are the existing document lists filtered by `?customer={id}`:
        sales-invoices, payments, return-invoices and customer-requests.
        """
        # Check if customer is assigned to this rep
        instance = self.get_object()
        
        # Get rep_id from token payload
        rep_id = self.rep_id
        
        if not instance.assigned_reps.filter(id=rep_id).exists():
            return error_response(
                message="غير مصرح لك بالوصول إلى هذا العميل",
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        serializer = self.get_serializer(
            instance,
            context={
                **self.get_serializer_context(),
                "balances": self.balances_for([instance]),
            },
        )
        
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
        
        # Update the address if provided
        address_updated = False
        if 'address' in validated_data:
            customer.address = validated_data['address']
            customer.save(update_fields=['address', 'updated_at'])
            address_updated = True
        
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
        if address_updated:
            updates.append("العنوان")
        if location_updated:
            updates.append("الموقع")
        if work_days_updated:
            updates.append("أيام العمل")
        
        message = f"تم تحديث {' و '.join(updates)} بنجاح" if updates else "لم يتم إجراء أي تحديث"
        
        return success_response(
            data={
                "customer": self.get_serializer(
                    customer,
                    context={
                        **self.get_serializer_context(),
                        "balances": self.balances_for([customer]),
                    },
                ).data
            },
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


# ---------------------------------------------------------------------------
# Home screen
#
# The two read-only screens the rep app opens on. Neither owns a number: the
# dashboard reads the documents in `apps.invoices`, and the van reads the stock
# projection in `apps.products`, so a figure shown here and the same figure on
# the document it came from cannot disagree.
# ---------------------------------------------------------------------------


class RepScopedViewMixin:
    """The authenticated rep and their company, with no extra lookup.

    `MultiActorJWTAuthentication` already resolved the `Rep` (with its company
    select_related) to satisfy the token, so `request.user` *is* the rep. The
    older viewsets in this module re-fetch by `token_payload["rep_id"]`, which is
    the same id and the same rep — one query later.
    """

    permission_classes = [IsAuthenticated, IsRep]

    @property
    def rep(self):
        return self.request.user

    @property
    def company(self):
        return self.request.user.company


class RepDashboardView(RepScopedViewMixin, APIView):
    """`GET /api/reps/dashboard/` — everything the home screen renders, in one call.

    Query params:

    * `date=YYYY-MM-DD` — the day picker's shorthand, expanded to the whole day.
    * `date_from` / `date_to` — the general form, same vocabulary as the invoice
      lists; a bare date is widened to cover its whole day.
    * `limit` — rows returned inline per section (default 10, max 50).

    **No date parameters means no period filter**, which is what clearing the
    picker does. The `sales` and `returns` cards then cover all time, while
    `receivables` always does — see `services.dashboard` for why those two
    windows are deliberately different.

    The inline lists are a first page, not the whole set. Beyond `limit`, the
    client reads `/api/reps/sales-invoices/` and `/api/reps/return-invoices/`,
    which page, filter and accept the same dates; the van's full contents are at
    `/api/reps/inventory/`.
    """

    permission_classes = [IsAuthenticated, IsRep]

    def get(self, request):
        date_from, date_to = parse_period(request.query_params)

        data = rep_dashboard(
            company=self.company,
            rep=self.rep,
            date_from=date_from,
            date_to=date_to,
            preview_limit=parse_preview_limit(request.query_params),
        )

        # The service returns model instances so the rows render through the same
        # serializers the document endpoints use — an invoice on the home screen
        # is byte-identical to the same invoice in its own list.
        data["sales"]["invoices"] = SalesInvoiceSerializer(
            data["sales"]["invoices"], many=True
        ).data
        data["returns"]["return_invoices"] = ReturnInvoiceSerializer(
            data["returns"]["return_invoices"], many=True
        ).data

        warehouse = data["warehouse"]
        if warehouse is not None:
            warehouse["items"] = RepInventoryItemSerializer(
                warehouse.pop("items"),
                many=True,
                context={"prices": warehouse.pop("prices"), "request": request},
            ).data

        return success_response(data=data)


class RepInventoryViewSet(
    RepScopedViewMixin, PaginatedListMixin, viewsets.GenericViewSet
):
    """`GET /api/reps/inventory/` — what is loaded in the rep's own van.

    Read-only by design. A van's quantities are the ledger's answer, moved only
    by the documents that move goods — receiving a stock transfer, writing a
    sale, taking a return — so there is nothing here to edit.

    Filters: `search` (name, SKU or barcode), `include_empty=true` to keep
    products that have run out, which the stock-take screen wants and the
    "what can I sell" screen does not.

    The response carries `warehouse`, `total_quantity` and `product_count`
    alongside the page, which is the header the van screen prints.
    """

    queryset = ProductWarehouseStock.objects.all()
    serializer_class = RepInventoryItemSerializer
    list_key = "items"

    def get_queryset(self):
        warehouse = rep_warehouse(self.company.id, self.rep.id)
        if warehouse is None:
            return self.queryset.none()

        queryset = van_stock_queryset(
            warehouse,
            include_empty=self.request.query_params.get("include_empty") == "true",
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(product__name__icontains=search)
                | models.Q(product__sku__icontains=search)
                | models.Q(product__barcode__icontains=search)
            )

        return queryset

    def get_serializer_context(self):
        """Prices for every row on the list, in one query rather than one each."""
        context = super().get_serializer_context()
        context["prices"] = general_prices_by_product(
            self.get_queryset().values_list("product_id", flat=True),
            currency_code=self.company.currency,
        )
        return context

    def list(self, request, *args, **kwargs):
        warehouse = rep_warehouse(self.company.id, self.rep.id)
        queryset = self.get_queryset()
        totals = van_totals(queryset)

        return self.paginated_response(
            queryset,
            extra={
                "warehouse": (
                    {"id": warehouse.id, "name": warehouse.name}
                    if warehouse is not None
                    else None
                ),
                "total_quantity": decimal_string(totals["total_quantity"], places=3),
                "product_count": totals["product_count"],
                "currency": self.company.currency,
            },
        )


class RepProductViewSet(RepScopedViewMixin, PaginatedListMixin, viewsets.GenericViewSet):
    """`GET /api/reps/products/` — the catalog the rep orders and sells from.

    The picker behind "طلب بضاعة جديد". It is the company's sellable catalog with
    two things a rep cannot get from `/api/companies/products/`: the shelf price,
    and `van_quantity` — how many of each they are already carrying. Ordering
    without seeing what is on board is how a rep ends up with two cartons of the
    same tea.

    Distinct from `/api/reps/inventory/`, which answers "what is in my van".
    This one answers "what exists that I could ask for", and lists products whose
    van quantity is zero — those are exactly the rows a restock screen is for.

    Filters: `search` (name, SKU or barcode), `category`.
    """

    queryset = Product.objects.all()
    serializer_class = RepProductSerializer
    list_key = "products"

    def get_queryset(self):
        queryset = (
            Product.objects.filter(
                company_id=self.company.id, is_active=True, is_sellable=True
            )
            .select_related("unit")
            .prefetch_related(primary_image_prefetch())
        )

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                models.Q(name__icontains=search)
                | models.Q(sku__icontains=search)
                | models.Q(barcode__icontains=search)
            )

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)

        return queryset.order_by("name", "id")

    def get_serializer_context(self):
        """Prices and van quantities for the page, two queries rather than 2N.

        `paginated_response` slices the page before building the serializer, so
        the rows going out are known by the time this runs.
        """
        context = super().get_serializer_context()
        page = getattr(getattr(self, "paginator", None), "page", None)
        products = list(page) if page is not None else []
        product_ids = [product.id for product in products]

        context["prices"] = general_prices_by_product(
            product_ids, currency_code=self.company.currency
        )

        warehouse = rep_warehouse(self.company.id, self.rep.id)
        context["van_quantities"] = (
            dict(
                ProductWarehouseStock.objects.filter(
                    warehouse=warehouse, product_id__in=product_ids
                ).values_list("product_id", "quantity")
            )
            if warehouse is not None and product_ids
            else {}
        )
        return context

    def list(self, request, *args, **kwargs):
        return self.paginated_response(
            self.get_queryset(), extra={"currency": self.company.currency}
        )
