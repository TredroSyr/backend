"""Customer Request service (invoicing spec §3.3, flow §4.3).

A customer request is a wishlist signal, not a sale. Creating one:

* never touches a warehouse,
* never creates a financial record,
* notifies the assigned rep as a heads-up about interest.

Linking a request to a delivered Sales Invoice is optional in both directions: a
rep may deliver goods nobody asked for, and invoice creation is never blocked on
a request existing.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING, Sequence

from django.db import transaction
from django.utils import timezone

from apps.common.services.audit import record_audit
from apps.notifications.services import CUSTOMER_REQUEST_CREATED, notify_rep
from apps.orders.models import (
    CustomerRequest,
    CustomerRequestLine,
    CustomerRequestStatus,
)
from apps.reps.models import RepCustomerAssignment
from core.domain import DomainError

if TYPE_CHECKING:
    from rest_framework.request import Request

    from apps.invoices.models import SalesInvoice
    from apps.products.models import Product


def assigned_rep_id(company_id: int, customer_id: int) -> int | None:
    """The rep this company has on the customer, if any — the notification target."""
    return (
        RepCustomerAssignment.objects.filter(
            customer_id=customer_id, rep__company_id=company_id, rep__is_active=True
        )
        .values_list("rep_id", flat=True)
        .first()
    )


@transaction.atomic
def create_customer_request(
    *,
    company_id: int,
    customer_id: int,
    lines: Sequence[tuple[Product, Decimal]],
    notes: str = "",
    request: Request | None = None,
) -> CustomerRequest:
    """Record what a customer wants and ping their rep."""
    if not lines:
        raise DomainError("لا يمكن إرسال طلب فارغ", {"lines": ["No lines."]})

    customer_request = CustomerRequest.objects.create(
        company_id=company_id,
        customer_id=customer_id,
        rep_id=assigned_rep_id(company_id, customer_id),
        notes=notes,
    )

    CustomerRequestLine.objects.bulk_create(
        [
            CustomerRequestLine(
                company_id=company_id,
                request=customer_request,
                product=product,
                unit_id=product.unit_id,
                desired_quantity=quantity,
            )
            for product, quantity in lines
        ]
    )

    notify_rep(
        company_id=company_id,
        rep_id=customer_request.rep_id,
        event_key=CUSTOMER_REQUEST_CREATED,
        payload={
            "customer_request_id": customer_request.id,
            "customer_id": customer_id,
            "line_count": len(lines),
        },
    )

    record_audit(
        company_id=company_id,
        entity=customer_request,
        action="created",
        request=request,
        to_status=customer_request.status,
        changes={"lines": len(lines), "rep_id": customer_request.rep_id},
    )
    return customer_request


@transaction.atomic
def fulfil_requests(
    *,
    company_id: int,
    request_ids: Sequence[int],
    invoice: SalesInvoice,
    customer_id: int,
    request: Request | None = None,
) -> list[int]:
    """Mark the requests a delivery resolved (§3.3, last rule).

    Called from `invoices.services.sales` inside the invoice's own transaction, so
    a sale and the requests it fulfils commit together. Returns the ids actually
    marked.
    """
    if not request_ids:
        return []

    requests = list(
        CustomerRequest.objects.select_for_update()
        .filter(company_id=company_id, customer_id=customer_id, id__in=request_ids)
        .order_by("id")
    )

    found = {item.id for item in requests}
    missing = [request_id for request_id in request_ids if request_id not in found]
    if missing:
        raise DomainError(
            "بعض الطلبات المحددة غير موجودة لهذا العميل",
            {"fulfils_request_ids": [f"Not found for this customer: {missing}"]},
        )

    already_closed = [
        item.id for item in requests if item.status != CustomerRequestStatus.PENDING
    ]
    if already_closed:
        raise DomainError(
            "بعض الطلبات المحددة تم إغلاقها مسبقاً",
            {"fulfils_request_ids": [f"Already fulfilled or cancelled: {already_closed}"]},
        )

    now = timezone.now()
    for item in requests:
        item.status = CustomerRequestStatus.FULFILLED
        item.fulfilled_by_invoice = invoice
        item.fulfilled_at = now

    CustomerRequest.objects.bulk_update(
        requests, ["status", "fulfilled_by_invoice", "fulfilled_at", "updated_at"]
    )

    for item in requests:
        record_audit(
            company_id=company_id,
            entity=item,
            action="fulfilled",
            request=request,
            from_status=CustomerRequestStatus.PENDING,
            to_status=item.status,
            changes={"sales_invoice": invoice.number},
        )

    return [item.id for item in requests]


@transaction.atomic
def cancel_customer_request(
    customer_request: CustomerRequest, *, request: Request | None = None
) -> CustomerRequest:
    """Withdraw a request that has not been delivered against."""
    if customer_request.status != CustomerRequestStatus.PENDING:
        raise DomainError(
            "لا يمكن إلغاء طلب تم إغلاقه",
            {"status": [f"Cannot cancel a request in status '{customer_request.status}'."]},
        )

    previous_status = customer_request.status
    customer_request.status = CustomerRequestStatus.CANCELLED
    customer_request.cancelled_at = timezone.now()
    customer_request.save(update_fields=["status", "cancelled_at", "updated_at"])

    record_audit(
        company_id=customer_request.company_id,
        entity=customer_request,
        action="cancelled",
        request=request,
        from_status=previous_status,
        to_status=customer_request.status,
    )
    return customer_request
