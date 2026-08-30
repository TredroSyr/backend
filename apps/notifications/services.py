"""In-app notification dispatch.

One `notify` entry point writes `Notification` rows; callers name an event key and
pass a payload. Copy lives in `EVENT_COPY` so the wording of an event is changed
in one place rather than at every call site, and clients that prefer to render
their own text can ignore it and read the payload.

Role-based targeting (`notify_company_admins`) resolves recipients from the
existing Role/ModulePermission matrix rather than a second notification-specific
list of who cares about what.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from django.db.models import Q

from apps.companies.models import SubUser
from apps.notifications.models import ActorType, Notification

if TYPE_CHECKING:
    from apps.notifications.models import Notification as NotificationType

# Customer request (invoicing spec §3.3): the copy deliberately reads as a
# heads-up about interest, not as a confirmed order — no commitment has been made
# and the sale only happens when the rep visits.
CUSTOMER_REQUEST_CREATED = "customer_request.created"
STOCK_TRANSFER_REQUESTED = "stock_transfer.requested"
# Sent to the rep when the office starts the transfer itself. Distinct from
# `.confirmed` on purpose: the rep is being told about goods they never asked
# for, which reads as news rather than as an answer.
STOCK_TRANSFER_DISPATCHED = "stock_transfer.dispatched"
STOCK_TRANSFER_MODIFIED = "stock_transfer.modified"
STOCK_TRANSFER_CONFIRMED = "stock_transfer.confirmed"
STOCK_TRANSFER_RECEIVED = "stock_transfer.received"
STOCK_TRANSFER_CANCELLED = "stock_transfer.cancelled"

EVENT_COPY: dict[str, dict[str, str]] = {
    CUSTOMER_REQUEST_CREATED: {
        "title": "اهتمام جديد من عميل",
        "body": "أضاف العميل منتجات إلى قائمة رغباته — ليس طلباً مؤكداً، راجعها قبل زيارتك القادمة.",
    },
    STOCK_TRANSFER_REQUESTED: {
        "title": "طلب بضاعة جديد",
        "body": "قام أحد المندوبين بطلب بضاعة من المستودع.",
    },
    STOCK_TRANSFER_DISPATCHED: {
        "title": "بضاعة بانتظارك في المستودع",
        "body": "أرسلت لك الإدارة بضاعة جاهزة للاستلام من المستودع.",
    },
    STOCK_TRANSFER_MODIFIED: {
        "title": "تم تعديل كميات طلبك",
        "body": "قامت الإدارة بتعديل الكميات المطلوبة، يرجى الموافقة أو الرفض.",
    },
    STOCK_TRANSFER_CONFIRMED: {
        "title": "طلب البضاعة جاهز للاستلام",
        "body": "تمت الموافقة على الطلب وهو جاهز للاستلام من المستودع.",
    },
    STOCK_TRANSFER_RECEIVED: {
        "title": "تم تسليم البضاعة",
        "body": "أكد المندوب استلام البضاعة وتم تحديث المستودعات.",
    },
    STOCK_TRANSFER_CANCELLED: {
        "title": "تم إلغاء طلب البضاعة",
        "body": "تم إلغاء طلب البضاعة.",
    },
}


def notify(
    *,
    company_id: int,
    recipient_actor_type: str,
    recipient_actor_id: int,
    event_key: str,
    payload: dict | None = None,
) -> NotificationType:
    """Write one in-app notification, merging the event's default copy."""
    return Notification.objects.create(
        company_id=company_id,
        recipient_actor_type=recipient_actor_type,
        recipient_actor_id=recipient_actor_id,
        event_key=event_key,
        payload={**EVENT_COPY.get(event_key, {}), **(payload or {})},
    )


def notify_rep(
    *, company_id: int, rep_id: int, event_key: str, payload: dict | None = None
) -> NotificationType | None:
    if not rep_id:
        return None
    return notify(
        company_id=company_id,
        recipient_actor_type=ActorType.REP,
        recipient_actor_id=rep_id,
        event_key=event_key,
        payload=payload,
    )


def admin_recipient_ids(company_id: int, module: str) -> list[int]:
    """SubUsers who can act on `module`: the owner, plus any role granted it.

    Joining through the role's permissions can duplicate a row, hence distinct().
    """
    return list(
        SubUser.objects.filter(company_id=company_id, is_active=True)
        .filter(
            Q(is_owner=True)
            | Q(role__permissions__module=module, role__permissions__can_action=True)
        )
        .values_list("id", flat=True)
        .distinct()
    )


def notify_company_admins(
    *,
    company_id: int,
    module: str,
    event_key: str,
    payload: dict | None = None,
) -> list[NotificationType]:
    """Fan out to everyone in the company allowed to act on `module`."""
    return [
        notify(
            company_id=company_id,
            recipient_actor_type=ActorType.SUBUSER,
            recipient_actor_id=subuser_id,
            event_key=event_key,
            payload=payload,
        )
        for subuser_id in admin_recipient_ids(company_id, module)
    ]


def notify_many(
    *,
    company_id: int,
    recipients: Iterable[tuple[str, int]],
    event_key: str,
    payload: dict | None = None,
) -> list[NotificationType]:
    """Fan out to explicit `(actor_type, actor_id)` pairs."""
    return [
        notify(
            company_id=company_id,
            recipient_actor_type=actor_type,
            recipient_actor_id=actor_id,
            event_key=event_key,
            payload=payload,
        )
        for actor_type, actor_id in recipients
    ]
