"""Audit trail writer (invoicing spec §6.4).

Every transition that moves money or stock records who did it, when, and what
changed. Entries are append-only; nothing in the codebase updates or deletes them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from apps.common.models import ActorType, AuditLog

if TYPE_CHECKING:
    from django.db.models import Model
    from rest_framework.request import Request


def actor_from_request(request: Request | None) -> tuple[str, int | None]:
    """Resolve `(actor_type, actor_id)` from the JWT claims on the request."""
    if request is None:
        return ActorType.SYSTEM, None

    actor_type = getattr(request, "actor_type", None)
    if actor_type not in ActorType.values:
        return ActorType.SYSTEM, None

    token_payload = getattr(request, "token_payload", {}) or {}
    return actor_type, token_payload.get("user_id")


def record_audit(
    *,
    company_id: int,
    entity: Model,
    action: str,
    request: Request | None = None,
    from_status: str = "",
    to_status: str = "",
    changes: dict[str, Any] | None = None,
) -> AuditLog:
    """Append one history entry for `entity`.

    `entity_type` is taken from the model's `db_table` so the log reads in the
    same vocabulary as the schema (`sales_invoice`, `stock_transfer`, ...).
    """
    actor_type, actor_id = actor_from_request(request)

    return AuditLog.objects.create(
        company_id=company_id,
        actor_type=actor_type,
        actor_id=actor_id,
        entity_type=entity._meta.db_table,
        entity_id=entity.pk,
        entity_number=getattr(entity, "number", "") or "",
        action=action,
        from_status=from_status or "",
        to_status=to_status or "",
        changes=changes or {},
    )
