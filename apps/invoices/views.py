"""API surface for the invoicing module.

Views stay thin on purpose: they authenticate, scope, validate and delegate.
Every rule that matters — atomicity, stock movement, balance derivation, state
transitions, audit entries — lives in `apps.invoices.services`, so the same
operation behaves identically whichever entry point reaches it.

Three audiences, three scoping rules:

* **Admin** (`/api/companies/...`) — SubUsers, scoped by company, gated per
  document type by the Role/ModulePermission matrix (§6.7).
* **Rep** (`/api/reps/...`) — scoped to the authenticated rep's own documents.
  These are the field endpoints, so the write ones honour `Idempotency-Key`
  (§6.6).
* **Customer** — customer requests only, and those live in `apps.orders`.
"""

from __future__ import annotations

from django.db.models import Prefetch, Sum
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from apps.common.modules import INVOICES, REPORTS, SETTINGS
from apps.common.services.idempotency import IdempotentWriteMixin
from apps.companies.mixins import (
    AuditHistoryMixin,
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
)
from apps.companies.permissions import HasModulePermission, IsSubUser
from apps.invoices.models import (
    IncomingInvoice,
    IncomingInvoiceLine,
    PaymentCollection,
    PendingCustomerCredit,
    ReturnInvoice,
    ReturnInvoiceLine,
    ReturnInvoiceStatus,
    SalesInvoice,
    SalesInvoiceLine,
)
from apps.invoices.serializers import (
    AdminSalesInvoiceCreateSerializer,
    IncomingInvoiceCreateSerializer,
    IncomingInvoiceDetailSerializer,
    IncomingInvoiceSerializer,
    InvoiceSettingsSerializer,
    PaymentCollectionCreateSerializer,
    PaymentCollectionSerializer,
    PendingCustomerCreditSerializer,
    ReturnInvoiceCreateSerializer,
    ReturnInvoiceDetailSerializer,
    ReturnInvoiceIssueSerializer,
    ReturnInvoiceSerializer,
    SalesInvoiceCreateSerializer,
    SalesInvoiceDetailSerializer,
    SalesInvoiceSerializer,
)
from apps.invoices.services import credits as credit_service
from apps.invoices.services import incoming as incoming_service
from apps.invoices.services import payments as payment_service
from apps.invoices.services import reports as report_service
from apps.invoices.services import returns as return_service
from apps.invoices.services import sales as sales_service
from apps.invoices.services.documents import get_invoice_settings
from apps.products.services.images import primary_image_prefetch
from apps.reps.permissions import IsRep
from core.responses import decimal_string, success_response


class AdminDocumentViewSet(
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
    AuditHistoryMixin,
    viewsets.GenericViewSet,
):
    """Base for the company-facing document endpoints."""

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data={self.detail_key: serializer.data})


class RepDocumentViewSet(
    CompanyContextMixin,
    PaginatedListMixin,
    IdempotentWriteMixin,
    viewsets.GenericViewSet,
):
    """Base for the field endpoints, scoped to the authenticated rep."""

    permission_classes = [IsAuthenticated, IsRep]

    @property
    def rep_id(self) -> int:
        return self.request.token_payload.get("rep_id")

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(company_id=self.request.company_id, rep_id=self.rep_id)
        )

    def retrieve(self, request, *args, **kwargs):
        serializer = self.get_serializer(self.get_object())
        return success_response(data={self.detail_key: serializer.data})


class InvoiceSettingsView(APIView):
    """`GET`/`PATCH /api/companies/invoice-settings/`.

    One object per company, shared by every invoice type (§6.8) — including the
    `overdue_threshold_days` the overdue report reads (§5). It is not duplicated
    per invoice type and is created on first read.
    """

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]
    required_module = SETTINGS

    @property
    def required_permission(self) -> str:
        return "can_view" if self.request.method == "GET" else "can_action"

    def get(self, request):
        settings = get_invoice_settings(request.company_id)
        return success_response(data={"settings": InvoiceSettingsSerializer(settings).data})

    def patch(self, request):
        settings = get_invoice_settings(request.company_id)
        serializer = InvoiceSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return success_response(
            data={"settings": serializer.data},
            message="تم تحديث إعدادات الفواتير بنجاح",
        )


# ---------------------------------------------------------------------------
# Incoming invoices (admin only — §2: created by Admin)
# ---------------------------------------------------------------------------


class IncomingInvoiceViewSet(AdminDocumentViewSet):
    """`/api/companies/incoming-invoices/`

    Create leaves the invoice as a draft; `POST {id}/issue/` is what increments
    the company warehouse, atomically with the status change (§3.1).

    Filters: `status`, `warehouse`, `search` (number or supplier).
    """

    required_module = INVOICES
    queryset = IncomingInvoice.objects.all()
    list_key = "invoices"
    detail_key = "invoice"

    def get_serializer_class(self):
        if self.action == "create":
            return IncomingInvoiceCreateSerializer
        if self.action == "list":
            return IncomingInvoiceSerializer
        return IncomingInvoiceDetailSerializer

    def get_queryset(self):
        queryset = super().get_queryset().select_related("warehouse")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        warehouse = self.request.query_params.get("warehouse")
        if warehouse:
            queryset = queryset.filter(warehouse_id=warehouse)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(number__icontains=search)

        if self.action in {"retrieve", "issue", "cancel"}:
            queryset = queryset.prefetch_related(
                document_lines(IncomingInvoiceLine.objects.all())
            )

        return queryset.order_by("-date", "-id")

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invoice = incoming_service.create_incoming_invoice(
            company_id=self.company.id,
            warehouse=data["warehouse"],
            lines=data["line_inputs"],
            date=data.get("date"),
            supplier_ref=data.get("supplier_ref", ""),
            notes=data.get("notes", ""),
            created_by_id=request.user.id,
            currency=data.get("currency", ""),
            request=request,
        )

        return success_response(
            data={"invoice": IncomingInvoiceDetailSerializer(invoice).data},
            message="تم إنشاء فاتورة الوارد كمسودة",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def issue(self, request, *args, **kwargs):
        invoice = incoming_service.issue_incoming_invoice(
            self.get_object(), request=request
        )
        return success_response(
            data={"invoice": IncomingInvoiceDetailSerializer(invoice).data},
            message="تم ترحيل الفاتورة وتحديث المستودع",
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        invoice = incoming_service.cancel_incoming_invoice(
            self.get_object(), request=request
        )
        return success_response(
            data={"invoice": IncomingInvoiceDetailSerializer(invoice).data},
            message="تم إلغاء الفاتورة",
        )


# ---------------------------------------------------------------------------
# Sales invoices
# ---------------------------------------------------------------------------


def document_lines(line_queryset) -> Prefetch:
    """A document's lines carrying every relation `LineReadSerializer` reads.

    All three document types render lines the same way, so the joins are
    declared once; a missing one here is a query per line on every detail read.
    """
    return Prefetch(
        "lines",
        queryset=line_queryset.select_related("product", "unit").prefetch_related(
            primary_image_prefetch("product__images")
        ),
    )


def sales_invoice_queryset(base):
    """Shared prefetching and filtering for both sales-invoice audiences."""
    return base.select_related("rep", "customer", "warehouse")


def annotated_sales_lines():
    """Sold lines carrying how much of each has already come back.

    Lets the rep app show "3 of 10 returned" without a query per line.
    """
    return document_lines(
        SalesInvoiceLine.objects.annotate(
            returned_quantity=Sum("return_lines__quantity")
        )
    )


class SalesInvoiceFilterMixin:
    """Query params shared by the admin and rep sales-invoice lists."""

    def apply_sales_filters(self, queryset):
        params = self.request.query_params

        status_filter = params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        customer = params.get("customer")
        if customer:
            queryset = queryset.filter(customer_id=customer)

        if params.get("outstanding") == "true":
            queryset = queryset.filter(balance_due__gt=0)

        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(date__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            queryset = queryset.filter(date__lte=date_to)

        search = params.get("search")
        if search:
            queryset = queryset.filter(number__icontains=search)

        return queryset.order_by("-date", "-id")


class SalesInvoiceViewSet(SalesInvoiceFilterMixin, AdminDocumentViewSet):
    """`/api/companies/sales-invoices/`

    Most sales are written in the field by the rep who delivered (§2), but a
    customer can also buy directly from the company — a walk-in collecting from
    the warehouse, with no rep involved. `POST` here covers that: omit `rep` for a
    direct sale, or supply one to record a sale on that rep's behalf.

    Admins can also record a payment against any invoice, for a customer settling
    at the office rather than on a visit.

    Filters: `status`, `rep`, `customer`, `outstanding=true`, `date_from`,
    `date_to`, `search`.
    """

    required_module = INVOICES
    queryset = SalesInvoice.objects.all()
    list_key = "invoices"
    detail_key = "invoice"

    def get_serializer_class(self):
        if self.action == "create":
            return AdminSalesInvoiceCreateSerializer
        return (
            SalesInvoiceSerializer
            if self.action == "list"
            else SalesInvoiceDetailSerializer
        )

    def create(self, request, *args, **kwargs):
        """Create a company-direct sale, or record one on a rep's behalf.

        Same service call as the rep app, so the stock deduction, credit
        application, payment and audit trail behave identically — only the
        warehouse and the rep attribution differ.
        """
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invoice = sales_service.create_sales_invoice(
            company_id=self.company.id,
            rep=data.get("rep"),
            customer=data["customer"],
            lines=data["line_inputs"],
            warehouse=data.get("warehouse"),
            date=data.get("date"),
            notes=data.get("notes", ""),
            credit_ids=data.get("credit_ids", []),
            payment_amount=data.get("payment_amount"),
            payment_collected_at=data.get("payment_collected_at"),
            fulfils_request_ids=data.get("fulfils_request_ids", []),
            currency=data.get("currency", ""),
            request=request,
        )

        return success_response(
            data={"invoice": SalesInvoiceDetailSerializer(invoice).data},
            message="تم إنشاء فاتورة المبيعات بنجاح",
            status_code=status.HTTP_201_CREATED,
        )

    def get_queryset(self):
        queryset = self.apply_sales_filters(sales_invoice_queryset(super().get_queryset()))

        rep = self.request.query_params.get("rep")
        if rep:
            queryset = queryset.filter(rep_id=rep)

        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                annotated_sales_lines(), "payments__collected_by", "returns"
            )

        return queryset

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    @action(detail=True, methods=["post"], url_path="payments")
    def record_payment(self, request, *args, **kwargs):
        """Record a collection against this invoice (§3.6)."""
        invoice = self.get_object()
        serializer = PaymentCollectionCreateSerializer(
            data={**request.data, "sales_invoice": invoice.id},
            context=self.get_serializer_context(),
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        collected_by = data.get("collected_by")

        payment, invoice = payment_service.collect_payment(
            company_id=self.company.id,
            invoice_id=invoice.id,
            amount=data["amount"],
            collected_by_id=collected_by.id if collected_by else None,
            collected_at=data.get("collected_at"),
            note=data.get("note", ""),
            request=request,
        )

        return success_response(
            data={
                "payment": PaymentCollectionSerializer(payment).data,
                "invoice": SalesInvoiceSerializer(invoice).data,
            },
            message="تم تسجيل الدفعة بنجاح",
            status_code=status.HTTP_201_CREATED,
        )


class RepSalesInvoiceViewSet(SalesInvoiceFilterMixin, RepDocumentViewSet):
    """`/api/reps/sales-invoices/` — the rep writes the real transaction here.

    `POST` accepts the whole visit in one call: lines, credits to apply, and any
    cash collected on the spot. Send an `Idempotency-Key` header; a retry after a
    dropped connection then replays the first response instead of invoicing the
    customer twice or double-deducting the van (§6.6).

    Listing is scoped to the authenticated rep. Filters: `status`, `customer`,
    `outstanding=true`, `date_from`, `date_to`, `search`.
    """

    queryset = SalesInvoice.objects.all()
    list_key = "invoices"
    detail_key = "invoice"

    def get_serializer_class(self):
        if self.action == "create":
            return SalesInvoiceCreateSerializer
        return (
            SalesInvoiceSerializer
            if self.action == "list"
            else SalesInvoiceDetailSerializer
        )

    def get_queryset(self):
        queryset = self.apply_sales_filters(sales_invoice_queryset(super().get_queryset()))

        if self.action == "retrieve":
            queryset = queryset.prefetch_related(
                annotated_sales_lines(), "payments", "returns"
            )

        return queryset

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def create(self, request, *args, **kwargs):
        return self.idempotent(
            request, "sales_invoice.create", lambda: self._create(request)
        )

    def _create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        invoice = sales_service.create_sales_invoice(
            company_id=self.company.id,
            rep=request.user,
            customer=data["customer"],
            lines=data["line_inputs"],
            warehouse=data.get("warehouse"),
            date=data.get("date"),
            notes=data.get("notes", ""),
            credit_ids=data.get("credit_ids", []),
            payment_amount=data.get("payment_amount"),
            payment_collected_at=data.get("payment_collected_at"),
            fulfils_request_ids=data.get("fulfils_request_ids", []),
            currency=data.get("currency", ""),
            request=request,
        )

        return success_response(
            data={"invoice": SalesInvoiceDetailSerializer(invoice).data},
            message="تم إنشاء فاتورة المبيعات بنجاح",
            status_code=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Return invoices
# ---------------------------------------------------------------------------


class ReturnInvoiceWriteMixin:
    """Create and issue, shared by the admin and rep return endpoints.

    Both audiences can issue credit notes — a rep in the field, an admin when
    defective goods are pulled back to a company warehouse (§2) — and the rules
    are identical, so the handlers are too.
    """

    def create_return(self, request, *, rep_id=None):
        serializer = ReturnInvoiceCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        sales_invoice = data["sales_invoice"]

        return_invoice = return_service.create_return_invoice(
            company_id=self.company.id,
            sales_invoice=sales_invoice,
            requested_lines=data["requested_lines"],
            rep_id=rep_id or sales_invoice.rep_id,
            warehouse=data.get("warehouse"),
            date=data.get("date"),
            notes=data.get("notes", ""),
            refund_method=data.get("refund_method", ""),
            request=request,
        )

        return success_response(
            data={"return_invoice": self.serialize_return(return_invoice)},
            message="تم إنشاء فاتورة الإرجاع كمسودة",
            status_code=status.HTTP_201_CREATED,
        )

    def issue_return(self, request, return_invoice):
        """`refund_method` may arrive here rather than at creation: the rep only
        learns whether cash is going back once the overage is known (§3.5 rule 3).
        """
        serializer = ReturnInvoiceIssueSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refund_method = serializer.validated_data.get("refund_method")

        if refund_method:
            return_invoice.refund_method = refund_method
            return_invoice.save(update_fields=["refund_method", "updated_at"])

        return_invoice = return_service.issue_return_invoice(
            return_invoice, request=request
        )

        return success_response(
            data={
                "return_invoice": self.serialize_return(return_invoice),
                "invoice": SalesInvoiceSerializer(return_invoice.sales_invoice).data,
            },
            message="تم ترحيل فاتورة الإرجاع",
        )

    @staticmethod
    def serialize_return(return_invoice):
        data = ReturnInvoiceDetailSerializer(return_invoice).data
        if return_invoice.status == ReturnInvoiceStatus.DRAFT:
            data["projected_overage_amount"] = return_service.projected_overage(
                return_invoice
            )
        return data


def return_invoice_queryset(base, *, detailed: bool):
    queryset = base.select_related("sales_invoice", "rep", "warehouse")
    if detailed:
        queryset = queryset.prefetch_related(
            document_lines(ReturnInvoiceLine.objects.all())
        )
    return queryset


class ReturnInvoiceViewSet(ReturnInvoiceWriteMixin, AdminDocumentViewSet):
    """`/api/companies/return-invoices/`

    Filters: `status`, `rep`, `customer`, `sales_invoice`, `search`.

    A return carries no customer of its own — it is always a credit note against
    one sale — so `customer` filters through the parent invoice.
    """

    required_module = INVOICES
    queryset = ReturnInvoice.objects.all()
    list_key = "return_invoices"
    detail_key = "return_invoice"

    def get_serializer_class(self):
        return (
            ReturnInvoiceSerializer
            if self.action == "list"
            else ReturnInvoiceDetailSerializer
        )

    def get_queryset(self):
        queryset = return_invoice_queryset(
            super().get_queryset(), detailed=self.action != "list"
        )
        params = self.request.query_params

        for param, field in (
            ("status", "status"),
            ("rep", "rep_id"),
            ("customer", "sales_invoice__customer_id"),
            ("sales_invoice", "sales_invoice_id"),
        ):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        search = params.get("search")
        if search:
            queryset = queryset.filter(number__icontains=search)

        return queryset.order_by("-date", "-id")

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def create(self, request, *args, **kwargs):
        return self.create_return(request)

    @action(detail=True, methods=["post"])
    def issue(self, request, *args, **kwargs):
        return self.issue_return(request, self.get_object())


class RepReturnInvoiceViewSet(ReturnInvoiceWriteMixin, RepDocumentViewSet):
    """`/api/reps/return-invoices/` — credit notes written during a visit.

    Scoped to the authenticated rep. Filters: `status`, `customer`,
    `sales_invoice`.
    """

    queryset = ReturnInvoice.objects.all()
    list_key = "return_invoices"
    detail_key = "return_invoice"

    def get_serializer_class(self):
        return (
            ReturnInvoiceSerializer
            if self.action == "list"
            else ReturnInvoiceDetailSerializer
        )

    def get_queryset(self):
        queryset = return_invoice_queryset(
            super().get_queryset(), detailed=self.action != "list"
        )

        params = self.request.query_params

        for param, field in (
            ("status", "status"),
            ("customer", "sales_invoice__customer_id"),
            ("sales_invoice", "sales_invoice_id"),
        ):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        return queryset.order_by("-date", "-id")

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def create(self, request, *args, **kwargs):
        return self.idempotent(
            request,
            "return_invoice.create",
            lambda: self.create_return(request, rep_id=self.rep_id),
        )

    @action(detail=True, methods=["post"])
    def issue(self, request, *args, **kwargs):
        return_invoice = self.get_object()
        return self.idempotent(
            request,
            "return_invoice.issue",
            lambda: self.issue_return(request, return_invoice),
        )


# ---------------------------------------------------------------------------
# Payment collections
# ---------------------------------------------------------------------------


class PaymentCollectionFilterMixin:
    def apply_payment_filters(self, queryset):
        params = self.request.query_params

        for param, field in (
            ("sales_invoice", "sales_invoice_id"),
            ("customer", "sales_invoice__customer_id"),
            ("source", "source"),
        ):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        date_from = params.get("date_from")
        if date_from:
            queryset = queryset.filter(collected_at__gte=date_from)

        date_to = params.get("date_to")
        if date_to:
            queryset = queryset.filter(collected_at__lte=date_to)

        return queryset.select_related("sales_invoice", "collected_by").order_by(
            "-collected_at", "-id"
        )


class PaymentCollectionViewSet(
    PaymentCollectionFilterMixin,
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
    viewsets.GenericViewSet,
):
    """`/api/companies/payment-collections/` — read-only audit of what came in.

    Payments are appended through the invoice they belong to
    (`POST /companies/sales-invoices/{id}/payments/`), never edited here: they are
    immutable records and the invoice balance is derived from them (§3.6).

    Filters: `rep` (who collected), `customer` (through the paid invoice),
    `sales_invoice`, `source`, `date_from`, `date_to`.
    """

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]
    required_module = INVOICES
    queryset = PaymentCollection.objects.all()
    serializer_class = PaymentCollectionSerializer
    list_key = "payments"

    def get_queryset(self):
        queryset = self.apply_payment_filters(super().get_queryset())

        rep = self.request.query_params.get("rep")
        if rep:
            queryset = queryset.filter(collected_by_id=rep)

        return queryset

    def list(self, request, *args, **kwargs):
        totals = self.get_queryset().aggregate(total=Sum("amount"))
        return self.paginated_response(
            self.get_queryset(),
            extra={"total_amount": decimal_string(totals["total"])},
        )


class RepPaymentCollectionViewSet(
    PaymentCollectionFilterMixin,
    CompanyContextMixin,
    PaginatedListMixin,
    IdempotentWriteMixin,
    viewsets.GenericViewSet,
):
    """`/api/reps/payments/` — record a collection during a visit.

    Retry-safe with an `Idempotency-Key` header: a dropped response must not turn
    one collected payment into two (§6.6).

    Listing is scoped to the authenticated rep. Filters: `customer`,
    `sales_invoice`, `source`, `date_from`, `date_to`.
    """

    permission_classes = [IsAuthenticated, IsRep]
    queryset = PaymentCollection.objects.all()
    serializer_class = PaymentCollectionSerializer
    list_key = "payments"

    @property
    def rep_id(self) -> int:
        return self.request.token_payload.get("rep_id")

    def get_queryset(self):
        return self.apply_payment_filters(
            super()
            .get_queryset()
            .filter(company_id=self.request.company_id, collected_by_id=self.rep_id)
        )

    def list(self, request, *args, **kwargs):
        totals = self.get_queryset().aggregate(total=Sum("amount"))
        return self.paginated_response(
            self.get_queryset(),
            extra={"total_amount": decimal_string(totals["total"])},
        )

    def create(self, request, *args, **kwargs):
        return self.idempotent(
            request, "payment_collection.create", lambda: self._create(request)
        )

    def _create(self, request):
        serializer = PaymentCollectionCreateSerializer(
            data=request.data, context=self.get_serializer_context()
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        payment, invoice = payment_service.collect_payment(
            company_id=self.company.id,
            invoice_id=data["sales_invoice"].id,
            amount=data["amount"],
            collected_by_id=self.rep_id,
            collected_at=data.get("collected_at"),
            note=data.get("note", ""),
            request=request,
        )

        return success_response(
            data={
                "payment": PaymentCollectionSerializer(payment).data,
                "invoice": SalesInvoiceSerializer(invoice).data,
            },
            message="تم تسجيل الدفعة بنجاح",
            status_code=status.HTTP_201_CREATED,
        )


# ---------------------------------------------------------------------------
# Pending customer credits
# ---------------------------------------------------------------------------


class CustomerCreditFilterMixin:
    def apply_credit_filters(self, queryset):
        params = self.request.query_params

        # A credit has no rep of its own; it inherits the one from the return that
        # created it, which is null for a company-direct sale.
        for param, field in (
            ("status", "status"),
            ("customer", "customer_id"),
            ("rep", "source_return_invoice__rep_id"),
        ):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        return queryset.select_related("customer", "source_return_invoice").order_by(
            "-created_at", "-id"
        )


class CustomerCreditViewSet(
    CustomerCreditFilterMixin,
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
    viewsets.GenericViewSet,
):
    """`/api/companies/customer-credits/`

    Credits are created only by the `deferred_customer_credit` refund path and
    are applied manually against a new sale — this is a tracked list, not an
    auto-applying ledger (§3.7, §7). An admin can write one off with
    `POST {id}/cancel/`.

    Filters: `status`, `customer`, `rep` (the rep on the return that raised it).
    """

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]
    required_module = INVOICES
    queryset = PendingCustomerCredit.objects.all()
    serializer_class = PendingCustomerCreditSerializer
    list_key = "credits"

    def get_queryset(self):
        return self.apply_credit_filters(super().get_queryset())

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        credit = credit_service.cancel_credit(self.get_object(), request=request)
        return success_response(
            data={"credit": PendingCustomerCreditSerializer(credit).data},
            message="تم إلغاء الرصيد",
        )


class RepCustomerCreditViewSet(
    CustomerCreditFilterMixin,
    CompanyContextMixin,
    PaginatedListMixin,
    viewsets.GenericViewSet,
):
    """`/api/reps/customer-credits/?customer=<id>`

    What the rep app calls before writing a new invoice, so it can ask "this
    customer has a pending credit of X — apply it?" rather than applying one
    silently (§3.7 rule 1).
    """

    permission_classes = [IsAuthenticated, IsRep]
    queryset = PendingCustomerCredit.objects.all()
    serializer_class = PendingCustomerCreditSerializer
    list_key = "credits"

    def get_queryset(self):
        return self.apply_credit_filters(
            super().get_queryset().filter(company_id=self.request.company_id)
        )

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        totals = queryset.aggregate(total=Sum("amount"))
        return self.paginated_response(
            queryset, extra={"total_amount": decimal_string(totals["total"])}
        )


# ---------------------------------------------------------------------------
# Reports (§5)
# ---------------------------------------------------------------------------


class ReportView(APIView):
    """Shared auth/gating for the admin report endpoints."""

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]
    required_module = REPORTS
    required_permission = "can_view"

    @staticmethod
    def _int_param(request, name):
        value = request.query_params.get(name)
        return int(value) if value else None


class OverdueDebtReportView(ReportView):
    """`GET /api/companies/reports/overdue-debts/`

    Computed on read, not a cached table and not a push alert — v1 is pull-only
    (§5, §7). Grouped by rep and by customer, both required by the spec, and
    intended to hang off the existing rep-activity monitoring screen rather than
    a new module.

    Query params: `threshold_days` (defaults to the company's Invoice Settings
    value), `rep`, `customer`.
    """

    def get(self, request):
        report = report_service.overdue_debt_report(
            request.company_id,
            threshold_days=self._int_param(request, "threshold_days"),
            rep_id=self._int_param(request, "rep"),
            customer_id=self._int_param(request, "customer"),
        )
        return success_response(data={"report": report})


class RepCashReconciliationView(ReportView):
    """`GET /api/companies/reports/rep-cash/`

    Cash each rep collected, less any they refunded on the spot through the
    `cash_refunded_by_rep` path (§3.5 rule 3) — the figure that path needs
    deducted from their expected cash-in.

    Query params: `rep`, `date_from`, `date_to`.
    """

    def get(self, request):
        report = report_service.rep_cash_reconciliation(
            request.company_id,
            rep_id=self._int_param(request, "rep"),
            date_from=request.query_params.get("date_from"),
            date_to=request.query_params.get("date_to"),
        )
        return success_response(data={"report": report})
