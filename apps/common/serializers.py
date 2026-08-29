"""Serializers for common lookup data (global reference tables)."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.models import AuditLog, Currency, UnitOfMeasure


class UnitOfMeasureSerializer(serializers.ModelSerializer):
    """Serializer for UnitOfMeasure lookup data."""
    
    class Meta:
        model = UnitOfMeasure
        fields = ["id", "code", "name", "is_active"]
        read_only_fields = fields


class CurrencySerializer(serializers.ModelSerializer):
    """Serializer for Currency lookup data."""
    
    class Meta:
        model = Currency
        fields = ["id", "code", "name", "symbol", "is_active"]
        read_only_fields = fields


class AuditLogSerializer(serializers.ModelSerializer):
    """Read-only view of the immutable history trail (invoicing spec §6.4)."""

    class Meta:
        model = AuditLog
        fields = [
            "id",
            "actor_type",
            "actor_id",
            "entity_type",
            "entity_id",
            "entity_number",
            "action",
            "from_status",
            "to_status",
            "changes",
            "created_at",
        ]
        read_only_fields = fields
