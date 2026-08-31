"""API surface for stock transfers and customer requests.

Same shape as the invoices views: authenticate, scope, validate, delegate. The
state machine and the stock movement live in `apps.orders.services.transfers`,
so an illegal transition is rejected identically whichever endpoint asks for it.

Who can do what follows the spec's flows rather than a generic CRUD split:

* a **rep** raises a transfer, accepts or rejects modified quantities, and
  confirms physical receipt;
* an **admin** approves as-is, modifies quantities, or cancels;
* a **customer** raises and withdraws their own requests.
"""

from __future__ import annotations

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.common.modules import CUSTOMER_REQUESTS, STOCK_TRANSFERS
from apps.common.services.idempotency import IdempotentWriteMixin
from apps.common.services.periods import filter_by_period
from apps.companies.mixins import (
    AuditHistoryMixin,
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
)
from apps.companies.permissions import HasModulePermission, IsCustomer, IsSubUser
from apps.orders.models import CustomerRequest, StockTransfer
from apps.orders.serializers import (
    CustomerRequestCreateSerializer,
    CustomerRequestDetailSerializer,
    CustomerRequestSerializer,
    StockTransferCreateSerializer,
    StockTransferDetailSerializer,
    StockTransferDispatchSerializer,
    StockTransferModifySerializer,
    StockTransferSerializer,
)
from apps.orders.services import requests as request_service
from apps.orders.services.pricing import price_requests, price_transfers
from apps.orders.services import transfers as transfer_service
from apps.reps.permissions import IsRep
from core.responses import success_response


def transfer_queryset(base, *, detailed: bool):
    """Transfers carrying what every audience renders.

    Lines are prefetched either way — `detailed` only decides whether their
    product and unit come too — because even a summary row prints `line_count`.
    """
    queryset = base.select_related("rep", "source_warehouse", "destination_warehouse")
    if detailed:
        return queryset.prefetch_related("lines__product", "lines__unit")
    return queryset.prefetch_related("lines")


def request_queryset(base, *, detailed: bool):
    """Requests carrying what every audience renders.

    Lines are prefetched either way: `detailed` decides whether their product and
    unit come too, but even a summary row prints `line_count`, and reading that
    per row is the difference between one query and one per request.
    """
    queryset = base.select_related("customer", "rep", "fulfilled_by_invoice")
    if detailed:
        return queryset.prefetch_related("lines__product", "lines__unit")
    return queryset.prefetch_related("lines")


class StockTransferViewSet(
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
    AuditHistoryMixin,
    viewsets.GenericViewSet,
):
    """`/api/companies/stock-transfers/` — the admin side of §3.2.

    `approve` accepts the requested quantities as they stand; `modify` cuts them
    down and hands the transfer back to the rep for confirmation. Neither moves
    stock — only the rep's `receive` does.

    `POST` is the office's own origin for the same document: goods sent to a rep
    who never asked. It lands at `confirmed`, so the rep receives it exactly as
    they would one they raised themselves.

    Filters: `status`, `rep`, `search`.
    """

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]
    required_module = STOCK_TRANSFERS
    queryset = StockTransfer.objects.all()
    list_key = "transfers"
    detail_key = "transfer"

    def get_serializer_class(self):
        if self.action == "create":
            return StockTransferDispatchSerializer
        return (
            StockTransferSerializer
            if self.action == "list"
            else StockTransferDetailSerializer
        )

    def get_queryset(self):
        queryset = transfer_queryset(
            super().get_queryset(), detailed=self.action != "list"
        )
        params = self.request.query_params

        status_filter = params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        rep = params.get("rep")
        if rep:
            queryset = queryset.filter(rep_id=rep)

        search = params.get("search")
        if search:
            queryset = queryset.filter(number__icontains=search)

        return queryset.order_by("-requested_at", "-id")

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def retrieve(self, request, *args, **kwargs):
        return success_response(
            data={"transfer": self.get_serializer(self.get_object()).data}
        )

    def _respond(self, transfer, message):
        return success_response(
            data={"transfer": StockTransferDetailSerializer(transfer).data},
            message=message,
        )

    def create(self, request, *args, **kwargs):
        """Send a rep goods they did not request."""
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        transfer = transfer_service.dispatch_stock_transfer(
            company_id=self.company.id,
            rep=data["rep_instance"],
            lines=data["product_lines"],
            source_warehouse=data.get("source_warehouse"),
            destination_warehouse=data.get("destination_warehouse"),
            notes=data.get("notes", ""),
            dispatched_by_id=request.user.id,
            request=request,
        )

        return success_response(
            data={"transfer": StockTransferDetailSerializer(transfer).data},
            message="تم إرسال البضاعة بانتظار استلام المندوب",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def approve(self, request, *args, **kwargs):
        transfer = transfer_service.approve_transfer(
            self.get_object(), approved_by_id=request.user.id, request=request
        )
        return self._respond(transfer, "تمت الموافقة على الطلب")

    @action(detail=True, methods=["post"])
    def modify(self, request, *args, **kwargs):
        serializer = StockTransferModifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        transfer = transfer_service.modify_transfer(
            self.get_object(),
            serializer.validated_data["lines"],
            approved_by_id=request.user.id,
            request=request,
        )
        return self._respond(transfer, "تم تعديل الكميات بانتظار موافقة المندوب")

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        transfer = transfer_service.cancel_transfer(self.get_object(), request=request)
        return self._respond(transfer, "تم إلغاء الطلب")


class RepStockTransferViewSet(
    CompanyContextMixin,
    PaginatedListMixin,
    IdempotentWriteMixin,
    viewsets.GenericViewSet,
):
    """`/api/reps/stock-transfers/` — the rep side of §3.2.

    `receive` is the only action in the whole flow that moves stock, and it is
    idempotent: a rep tapping "received" twice on a bad connection must not
    transfer the goods twice.
    """

    permission_classes = [IsAuthenticated, IsRep]
    queryset = StockTransfer.objects.all()
    serializer_class = StockTransferDetailSerializer
    list_key = "transfers"
    detail_key = "transfer"

    @property
    def rep_id(self) -> int:
        return self.request.token_payload.get("rep_id")

    def get_serializer_class(self):
        if self.action == "create":
            return StockTransferCreateSerializer
        return StockTransferDetailSerializer

    def get_queryset(self):
        queryset = transfer_queryset(
            super().get_queryset().filter(
                company_id=self.request.company_id, rep_id=self.rep_id
            ),
            detailed=True,
        )

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        return filter_by_period(queryset, self.request.query_params,
                                field="requested_at").order_by("-requested_at", "-id")

    def get_serializer_context(self):
        """Shelf prices for the page being rendered.

        `paginated_response` slices the page before it builds the serializer, so
        by the time this runs the rows going out are known and can be priced in
        one batch. Detail and action responses have no page and pass their own
        context through `priced()`.
        """
        context = super().get_serializer_context()
        page = getattr(getattr(self, "paginator", None), "page", None)
        context["product_prices"] = price_transfers(
            list(page) if page is not None else [], company=self.company
        )
        return context

    def priced(self, transfers):
        return {
            **super().get_serializer_context(),
            "product_prices": price_transfers(transfers, company=self.company),
        }

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def retrieve(self, request, *args, **kwargs):
        transfer = self.get_object()
        return success_response(
            data={
                "transfer": self.get_serializer(
                    transfer, context=self.priced([transfer])
                ).data
            }
        )

    def create(self, request, *args, **kwargs):
        return self.idempotent(
            request, "stock_transfer.create", lambda: self._create(request)
        )

    def _create(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        transfer = transfer_service.create_stock_transfer(
            company_id=self.company.id,
            rep=request.user,
            lines=data["product_lines"],
            source_warehouse=data.get("source_warehouse"),
            destination_warehouse=data.get("destination_warehouse"),
            notes=data.get("notes", ""),
            pickup_within_hours=data.get("pickup_within_hours"),
            request=request,
        )

        return self._respond(
            transfer, "تم إرسال طلب البضاعة", status_code=status.HTTP_201_CREATED
        )

    def _respond(self, transfer, message, status_code=status.HTTP_200_OK):
        return success_response(
            data={
                "transfer": StockTransferDetailSerializer(
                    transfer, context=self.priced([transfer])
                ).data
            },
            message=message,
            status_code=status_code,
        )

    @action(detail=True, methods=["post"])
    def confirm(self, request, *args, **kwargs):
        """Rep accepts the quantities the admin modified."""
        transfer = transfer_service.rep_confirm_transfer(
            self.get_object(), request=request
        )
        return self._respond(transfer, "تم تأكيد الكميات")

    @action(detail=True, methods=["post"])
    def reject(self, request, *args, **kwargs):
        """Rep refuses the modified quantities. Terminal."""
        transfer = transfer_service.cancel_transfer(
            self.get_object(), action="rep_rejected", request=request
        )
        return self._respond(transfer, "تم رفض الطلب")

    @action(detail=True, methods=["post"])
    def receive(self, request, *args, **kwargs):
        """Physical receipt — the transfer's only stock movement."""
        transfer = self.get_object()
        return self.idempotent(
            request,
            "stock_transfer.receive",
            lambda: self._respond(
                transfer_service.receive_transfer(transfer, request=request),
                "تم تأكيد الاستلام وتحديث المستودعات",
            ),
        )


class CustomerRequestViewSet(
    CompanyContextMixin,
    ModuleScopedViewMixin,
    PaginatedListMixin,
    viewsets.GenericViewSet,
):
    """`/api/companies/customer-requests/` — read-only visibility for the office.

    These are signals, not orders: there is nothing for an admin to approve, and
    they are resolved by a rep delivering against them (§3.3).

    Filters: `status`, `customer`, `rep`.
    """

    permission_classes = [IsAuthenticated, IsSubUser, HasModulePermission]
    required_module = CUSTOMER_REQUESTS
    queryset = CustomerRequest.objects.all()
    list_key = "requests"

    def get_serializer_class(self):
        return (
            CustomerRequestSerializer
            if self.action == "list"
            else CustomerRequestDetailSerializer
        )

    def get_queryset(self):
        queryset = request_queryset(
            super().get_queryset(), detailed=self.action != "list"
        )
        params = self.request.query_params

        for param, field in (
            ("status", "status"),
            ("customer", "customer_id"),
            ("rep", "rep_id"),
        ):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        return queryset.order_by("-created_at", "-id")

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def retrieve(self, request, *args, **kwargs):
        return success_response(
            data={"request": self.get_serializer(self.get_object()).data}
        )


class RepCustomerRequestViewSet(
    CompanyContextMixin, PaginatedListMixin, viewsets.GenericViewSet
):
    """`/api/reps/customer-requests/` — the rep's orders screen (الطلبات).

    A request is a heads-up about interest, not a confirmed order, and answering
    it does not change that: `accept` is a promise to visit, `reject` is a
    decline, and **neither moves stock nor creates a debt**. Nothing is reserved
    by accepting — the goods stay in the van, sellable to whoever the rep reaches
    first.

    **Delivery is not an action here.** A rep marks a request delivered by
    writing the Sales Invoice with `fulfils_request_ids`, because that invoice is
    the only document that deducts the van and creates the debt. A status
    transition that skipped it would show goods delivered with nothing behind
    them. So the screen's "تم التسليم" button opens the invoice screen; it does
    not call this viewset.

        pending ──accept──> accepted ──POST /reps/sales-invoices/──> fulfilled
           │                    │        (fulfils_request_ids)
           └──reject──> rejected└────────────────────────────────────┘

    Filters: `status` (drives the الكل/معلق/مقبول/مسلم/مرفوض tabs), `customer`
    (the store page's "الطلبات السابقة" section).

    **Lines are included in the list here**, unlike the admin endpoint, priced at
    today's catalog rates. The rows are the point of the screen — a list of
    requests without them says a customer wants *something* — and a rep cannot
    judge "accept" without seeing what it is worth. Both are batched: one extra
    query for the page, not one per request.
    """

    permission_classes = [IsAuthenticated, IsRep]
    queryset = CustomerRequest.objects.all()
    serializer_class = CustomerRequestDetailSerializer
    list_key = "requests"

    @property
    def rep_id(self) -> int:
        return self.request.token_payload.get("rep_id")

    def get_queryset(self):
        queryset = request_queryset(
            super().get_queryset().filter(
                company_id=self.request.company_id, rep_id=self.rep_id
            ),
            detailed=True,
        )

        params = self.request.query_params
        for param, field in (("status", "status"), ("customer", "customer_id")):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        return filter_by_period(queryset, params, field="created_at").order_by(
            "-created_at", "-id"
        )

    def get_serializer_context(self):
        """Prices for the page being rendered.

        `PaginatedListMixin.paginated_response` slices the page before it builds
        the serializer, so by the time this runs the paginator knows which rows
        are going out and they can be priced in one batch. Detail actions have no
        page and pass their own context through `priced()`.
        """
        context = super().get_serializer_context()
        page = getattr(getattr(self, "paginator", None), "page", None)
        context["line_prices"] = price_requests(
            list(page) if page is not None else [], company=self.company
        )
        return context

    def priced(self, requests):
        """Serializer context carrying catalog prices for specific rows."""
        return {
            **super().get_serializer_context(),
            "line_prices": price_requests(requests, company=self.company),
        }

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def retrieve(self, request, *args, **kwargs):
        customer_request = self.get_object()
        return success_response(
            data={
                "request": self.get_serializer(
                    customer_request, context=self.priced([customer_request])
                ).data
            }
        )

    @action(detail=True, methods=["post"])
    def accept(self, request, *args, **kwargs):
        """`POST {id}/accept/` — yes, I will bring this. Only from `pending`."""
        customer_request = request_service.accept_customer_request(
            self.get_object(), request=request
        )
        return self._answered(customer_request, "تم قبول الطلب")

    @action(detail=True, methods=["post"])
    def reject(self, request, *args, **kwargs):
        """`POST {id}/reject/` — no. Optional `reason`, shown to the customer."""
        customer_request = request_service.reject_customer_request(
            self.get_object(),
            reason=(request.data.get("reason") or "").strip(),
            request=request,
        )
        return self._answered(customer_request, "تم رفض الطلب")

    def _answered(self, customer_request, message: str):
        return success_response(
            data={
                "request": self.get_serializer(
                    customer_request, context=self.priced([customer_request])
                ).data
            },
            message=message,
        )


class MyCustomerRequestViewSet(PaginatedListMixin, viewsets.GenericViewSet):
    """`/api/customers/requests/` — the customer app's wishlist.

    Customers are global entities with no company of their own, so scoping is by
    customer id from the token and the target company arrives in the payload.
    Creating one moves no stock and creates no financial record; it notifies the
    assigned rep that there is interest.
    """

    permission_classes = [IsAuthenticated, IsCustomer]
    queryset = CustomerRequest.objects.all()
    list_key = "requests"

    @property
    def customer_id(self) -> int:
        return self.request.token_payload.get("customer_id")

    def get_serializer_class(self):
        if self.action == "create":
            return CustomerRequestCreateSerializer
        return (
            CustomerRequestSerializer
            if self.action == "list"
            else CustomerRequestDetailSerializer
        )

    def get_queryset(self):
        queryset = request_queryset(
            super().get_queryset().filter(customer_id=self.customer_id),
            detailed=self.action != "list",
        )

        params = self.request.query_params
        for param, field in (("status", "status"), ("company", "company_id")):
            value = params.get(param)
            if value:
                queryset = queryset.filter(**{field: value})

        return queryset.order_by("-created_at", "-id")

    def list(self, request, *args, **kwargs):
        return self.paginated_response(self.get_queryset())

    def retrieve(self, request, *args, **kwargs):
        return success_response(
            data={"request": self.get_serializer(self.get_object()).data}
        )

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        customer_request = request_service.create_customer_request(
            company_id=data["company_id"],
            customer_id=self.customer_id,
            lines=data["product_lines"],
            notes=data.get("notes", ""),
            request=request,
        )

        return success_response(
            data={"request": CustomerRequestDetailSerializer(customer_request).data},
            message="تم إرسال طلبك إلى المندوب",
            status_code=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"])
    def cancel(self, request, *args, **kwargs):
        customer_request = request_service.cancel_customer_request(
            self.get_object(), request=request
        )
        return success_response(
            data={"request": CustomerRequestDetailSerializer(customer_request).data},
            message="تم إلغاء الطلب",
        )
