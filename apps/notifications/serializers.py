"""Serializers for the in-app notification inbox."""

from __future__ import annotations

from rest_framework import serializers

from apps.notifications.models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """One row of the bell menu.

    `title` and `body` are lifted out of `payload` rather than stored as columns:
    `services.notify` merges `EVENT_COPY` into the payload at write time, so the
    wording of an event still lives in one place while clients get it without
    digging. The whole `payload` is still returned — a client that renders its
    own copy, or needs the ids to deep-link into the document that raised the
    event, reads it there and ignores the two convenience fields.
    """

    title = serializers.SerializerMethodField()
    body = serializers.SerializerMethodField()
    is_read = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            "id",
            "event_key",
            "title",
            "body",
            "payload",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = fields

    def get_title(self, obj) -> str:
        return obj.payload.get("title", "")

    def get_body(self, obj) -> str:
        return obj.payload.get("body", "")

    def get_is_read(self, obj) -> bool:
        return obj.read_at is not None
