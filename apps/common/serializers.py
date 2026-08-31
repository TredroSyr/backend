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


#: Annotation name a queryset uses to pre-count a document's lines. Deliberately
#: not `line_count`: that is the serializer field, and an annotation of the same
#: name would shadow it depending on which queryset the object arrived on.
LINE_COUNT_ANNOTATION = "line_count_value"


def line_count_of(document) -> int:
    """How many lines a document has, by whichever route is already paid for.

    Every document list prints this and the three audiences reach it differently:
    a list annotates the count, a detail view has prefetched the lines anyway, and
    a one-off object (the invoice handed back after recording a payment) has
    neither. Without the first two branches this is one query per row.
    """
    annotated = getattr(document, LINE_COUNT_ANNOTATION, None)
    if annotated is not None:
        return annotated

    if "lines" in getattr(document, "_prefetched_objects_cache", {}):
        return len(document.lines.all())

    return document.lines.count()
