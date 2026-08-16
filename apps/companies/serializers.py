"""Serializers for company management."""

from __future__ import annotations

from rest_framework import serializers

from apps.companies.models import Company, SubUser


class CompanySerializer(serializers.ModelSerializer):
    """Serializer for Company model."""
    
    class Meta:
        model = Company
        fields = [
            "id",
            "name",
            "slug",
            "currency",
            "is_active",
            "logo",
            "cover",
            "governorate",
            "region",
            "description",
            "business_type",
            "onboarding_completed",
            "created_at",
        ]
        read_only_fields = ["id", "slug", "created_at"]


class SubUserSerializer(serializers.ModelSerializer):
    """Serializer for SubUser model."""
    
    company = CompanySerializer(read_only=True)
    
    class Meta:
        model = SubUser
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "is_owner",
            "is_active",
            "company",
            "created_at",
        ]
        read_only_fields = ["id", "is_owner", "created_at"]
