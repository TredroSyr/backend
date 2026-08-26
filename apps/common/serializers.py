"""Serializers for common lookup data (global reference tables)."""

from __future__ import annotations

from rest_framework import serializers

from apps.common.models import Currency, UnitOfMeasure


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
