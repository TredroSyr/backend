"""Idempotent write support (invoicing spec §6.6).

Reps work in low-connectivity field conditions: a request can succeed on the
server and still time out on the handset, so the app retries. Any endpoint that
creates a document or moves stock therefore accepts an `Idempotency-Key` header
and replays the original response instead of doing the work twice.

Flow, in order:

1. Reserve the key (a committed row with `response_status = 0`). A duplicate that
   arrives while the first is still running sees the reservation and gets 409
   rather than a second execution.
2. Run the operation.
3. Success -> store the rendered response on the reservation, so the retry
   replays it verbatim.
4. Failure -> drop the reservation, so the client can retry with corrected data.

A key replayed with a *different* body is rejected: that is a client bug, and
silently returning the old response would hide it.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Callable

from django.db import IntegrityError, transaction
from rest_framework import status
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from apps.common.models import IdempotencyKey
from apps.common.services.audit import actor_from_request
from core.responses import error_response

if TYPE_CHECKING:
    from rest_framework.request import Request

IDEMPOTENCY_HEADER = "Idempotency-Key"

# A reservation that has not been completed yet.
_IN_FLIGHT = 0


def fingerprint(payload: Any) -> str:
    """Stable SHA-256 of a request body, insensitive to key ordering."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _as_json(data: Any) -> Any:
    """Round-trip through DRF's renderer so Decimals/datetimes survive JSONField."""
    return json.loads(JSONRenderer().render(data)) if data is not None else {}


class IdempotentWriteMixin:
    """Wrap a write handler so it runs at most once per `Idempotency-Key`.

    Requests without the header run normally — the key is opt-in, and the rep app
    supplies it for exactly the three operations §6.6 names.
    """

    def idempotent(
        self,
        request: Request,
        scope: str,
        handler: Callable[[], Response],
    ) -> Response:
        key = (request.headers.get(IDEMPOTENCY_HEADER) or "").strip()
        company_id = getattr(request, "company_id", None)

        if not key or company_id is None:
            return handler()

        digest = fingerprint(request.data)
        actor_type, actor_id = actor_from_request(request)

        try:
            with transaction.atomic():
                reservation = IdempotencyKey.objects.create(
                    company_id=company_id,
                    actor_type=actor_type,
                    actor_id=actor_id,
                    scope=scope,
                    key=key,
                    request_fingerprint=digest,
                    response_status=_IN_FLIGHT,
                )
        except IntegrityError:
            return self._replay(company_id, scope, key, digest)

        try:
            response = handler()
        except Exception:
            reservation.delete()
            raise

        if not status.is_success(response.status_code):
            reservation.delete()
            return response

        reservation.response_status = response.status_code
        reservation.response_body = _as_json(response.data)
        reservation.save(update_fields=["response_status", "response_body"])
        return response

    @staticmethod
    def _replay(company_id: int, scope: str, key: str, digest: str) -> Response:
        existing = IdempotencyKey.objects.filter(
            company_id=company_id, scope=scope, key=key
        ).first()

        if existing is None:
            # The other request failed and released the key between our INSERT
            # and this read. Telling the client to retry is safer than racing again.
            return error_response(
                message="تعذّر تنفيذ الطلب، يرجى المحاولة مرة أخرى",
                status_code=status.HTTP_409_CONFLICT,
            )

        if existing.request_fingerprint != digest:
            return error_response(
                message="تم استخدام مفتاح الطلب هذا مع بيانات مختلفة",
                errors={IDEMPOTENCY_HEADER: ["Key already used with a different request body."]},
                status_code=status.HTTP_409_CONFLICT,
            )

        if existing.response_status == _IN_FLIGHT:
            return error_response(
                message="الطلب قيد المعالجة",
                status_code=status.HTTP_409_CONFLICT,
            )

        return Response(existing.response_body, status=existing.response_status)
