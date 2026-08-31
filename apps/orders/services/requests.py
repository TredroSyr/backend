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
from apps.notifications.models import ActorType
from apps.notifications.services import (
    CUSTOMER_REQUEST_ACCEPTED,
    CUSTOMER_REQUEST_CREATED,
    CUSTOMER_REQUEST_REJECTED,
    notify,
    notify_rep,
)
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


#: Statuses a request can still be answered or delivered against. `accepted` sits
#: here with `pending` because the rep saying yes does not close anything — the
#: Sales Invoice does.
OPEN_STATUSES = (CustomerRequestStatus.PENDING, CustomerRequestStatus.ACCEPTED)


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

    # A request the rep has already accepted is still deliverable — accepting is
    # a promise to visit, not a closure. Only the genuinely finished states block.
    already_closed = [
        item.id for item in requests if item.status not in OPEN_STATUSES
    ]
    if already_closed:
        raise DomainError(
            "بعض الطلبات المحددة تم إغلاقها مسبقاً",
            {"fulfils_request_ids": [f"Already closed: {already_closed}"]},
        )

    now = timezone.now()
    previous_statuses = {item.id: item.status for item in requests}
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
            from_status=previous_statuses[item.id],
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


# ---------------------------------------------------------------------------
# The rep's answer (§3.3)
#
# Accepting or rejecting is a reply to the customer, not a movement of anything.
# Neither touches a warehouse, neither creates a financial record, and accepting
# reserves nothing — the goods are still in the van and still sellable to whoever
# the rep reaches first. What accepting buys the customer is an answer.
#
# There is deliberately no `deliver` here. A delivery is a Sales Invoice, which is
# the only document that moves stock and creates a debt; the rep marks a request
# delivered by writing that invoice with `fulfils_request_ids`, which routes back
# through `fulfil_requests` above. A status transition that skipped it would show
# goods delivered with no invoice behind them.
# ---------------------------------------------------------------------------


def _answer(
    customer_request: CustomerRequest,
    *,
    status: str,
    timestamp_field: str,
    action: str,
    event_key: str,
    request: Request | None = None,
    **extra_fields,
) -> CustomerRequest:
    """Move a pending request to the rep's answer, once.

    Only `pending` can be answered: re-accepting is a no-op the client should not
    be able to mistake for a change, and flipping an accepted request to rejected
    after telling the customer yes is a different conversation, not a status edit.
    """
    if customer_request.status != CustomerRequestStatus.PENDING:
        raise DomainError(
            "لا يمكن الرد على طلب تم الرد عليه مسبقاً",
            {
                "status": [
                    f"Only a pending request can be answered; this one is "
                    f"'{customer_request.status}'."
                ]
            },
        )

    previous_status = customer_request.status
    customer_request.status = status
    setattr(customer_request, timestamp_field, timezone.now())
    for field, value in extra_fields.items():
        setattr(customer_request, field, value)

    customer_request.save(
        update_fields=[
            "status",
            timestamp_field,
            *extra_fields,
            "updated_at",
        ]
    )

    notify(
        company_id=customer_request.company_id,
        recipient_actor_type=ActorType.CUSTOMER,
        recipient_actor_id=customer_request.customer_id,
        event_key=event_key,
        payload={
            "customer_request_id": customer_request.id,
            "rep_id": customer_request.rep_id,
        },
    )

    record_audit(
        company_id=customer_request.company_id,
        entity=customer_request,
        action=action,
        request=request,
        from_status=previous_status,
        to_status=customer_request.status,
        changes=dict(extra_fields) or None,
    )
    return customer_request


@transaction.atomic
def accept_customer_request(
    customer_request: CustomerRequest, *, request: Request | None = None
) -> CustomerRequest:
    """The rep says yes: they will bring this on the next visit."""
    return _answer(
        customer_request,
        status=CustomerRequestStatus.ACCEPTED,
        timestamp_field="accepted_at",
        action="accepted",
        event_key=CUSTOMER_REQUEST_ACCEPTED,
        request=request,
    )


@transaction.atomic
def reject_customer_request(
    customer_request: CustomerRequest,
    *,
    reason: str = "",
    request: Request | None = None,
) -> CustomerRequest:
    """The rep says no. `reason` is optional and shown to the customer."""
    return _answer(
        customer_request,
        status=CustomerRequestStatus.REJECTED,
        timestamp_field="rejected_at",
        action="rejected",
        event_key=CUSTOMER_REQUEST_REJECTED,
        request=request,
        rejection_reason=reason,
    )
