from __future__ import annotations

from django.db import models


class ActorType(models.TextChoices):
    """JWT actor_type / polymorphic recipient. Not a table."""

    SUBUSER = "subuser", "SubUser"
    REP = "rep", "Rep"
    CUSTOMER = "customer", "Customer"


class Notification(models.Model):
    """In-app record. company_id always set even when the recipient is a Customer."""

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="notifications",
    )
    recipient_actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    recipient_actor_id = models.BigIntegerField()
    event_key = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification"
        indexes = [
            models.Index(fields=["company"], name="notification_company_idx"),
            models.Index(
                fields=["recipient_actor_type", "recipient_actor_id"],
                name="notification_recipient_idx",
            ),
            models.Index(fields=["created_at"], name="notification_created_idx"),
        ]
