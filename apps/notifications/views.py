"""The in-app inbox, for whichever actor is holding the token.

One viewset serves all three clients rather than three near-identical ones under
`/api/companies/`, `/api/reps/` and `/api/customers/`. A notification is
addressed to an actor, and the token already says which actor is asking — so the
audience prefix the document endpoints use would carry no information here, and
three copies of "which rows are mine" is three chances to get scoping wrong.

Scoping lives in `services.recipient_notifications`, which the rep dashboard's
bell badge also calls, so the count on the badge and the rows behind it can never
disagree.
"""

from __future__ import annotations

from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from apps.companies.mixins import PaginatedListMixin
from apps.notifications.models import ActorType, Notification
from apps.notifications.serializers import NotificationSerializer
from apps.notifications.services import mark_read, recipient_notifications
from core.responses import success_response


class NotificationViewSet(PaginatedListMixin, viewsets.GenericViewSet):
    """`/api/notifications/` — read your own notifications and mark them read.

    Rows are never created or deleted through the API: they are written by the
    services that raise the events (`apps.notifications.services.notify`), so the
    only mutation a client can make is marking one read.

    Endpoints:

    * `GET  /api/notifications/` — newest first, paged. Filters: `unread=true`,
      `event_key`. Every response carries `unread_count` for the badge.
    * `GET  /api/notifications/unread-count/` — the badge on its own, for polling.
    * `POST /api/notifications/{id}/read/` — mark one read.
    * `POST /api/notifications/read-all/` — mark the whole inbox read.
    """

    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    list_key = "notifications"

    def get_queryset(self):
        """The authenticated actor's own rows, and nobody else's.

        A Customer is deliberately not company-scoped: they are a global entity
        who may deal with several companies, and pinning them to one would hide
        the rest of their inbox. Every other actor is tenant-scoped.
        """
        actor_type = getattr(self.request, "actor_type", None)
        if actor_type not in ActorType.values:
            return self.queryset.none()

        company_id = (
            None
            if actor_type == ActorType.CUSTOMER
            else getattr(self.request, "company_id", None)
        )
        if actor_type != ActorType.CUSTOMER and company_id is None:
            return self.queryset.none()

        return recipient_notifications(
            recipient_actor_type=actor_type,
            recipient_actor_id=self.request.user.id,
            company_id=company_id,
        )

    def _unread(self, queryset):
        return queryset.filter(read_at__isnull=True)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()

        # The badge counts the whole unread inbox, not the filtered page — a rep
        # looking at "unread only" still needs to know the total.
        unread_count = self._unread(queryset).count()

        if request.query_params.get("unread") == "true":
            queryset = self._unread(queryset)

        event_key = request.query_params.get("event_key")
        if event_key:
            queryset = queryset.filter(event_key=event_key)

        return self.paginated_response(queryset, extra={"unread_count": unread_count})

    @action(detail=False, methods=["get"], url_path="unread-count")
    def unread_count(self, request, *args, **kwargs):
        return success_response(
            data={"unread_count": self._unread(self.get_queryset()).count()}
        )

    @action(detail=True, methods=["post"], url_path="read")
    def read(self, request, *args, **kwargs):
        notification = self.get_object()
        mark_read(self.get_queryset().filter(pk=notification.pk))
        notification.refresh_from_db(fields=["read_at"])

        return success_response(
            data={"notification": self.get_serializer(notification).data},
            message="تم تعليم الإشعار كمقروء",
        )

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request, *args, **kwargs):
        updated = mark_read(self.get_queryset())

        return success_response(
            data={"updated_count": updated, "unread_count": 0},
            message="تم تعليم جميع الإشعارات كمقروءة",
        )
