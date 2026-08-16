"""Serializers for company management."""

from __future__ import annotations

from django.utils import timezone
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


class CompanyOnboardingSerializer(serializers.ModelSerializer):
    """Serializer for company onboarding - all fields are optional."""
    
    class Meta:
        model = Company
        fields = [
            "logo",
            "cover",
            "governorate",
            "region",
            "description",
            "business_type",
        ]
        extra_kwargs = {
            "logo": {"required": False},
            "cover": {"required": False},
            "governorate": {"required": False},
            "region": {"required": False},
            "description": {"required": False},
            "business_type": {"required": False},
        }
    
    def update(self, instance, validated_data):
        """Update company and mark onboarding as completed."""
        # Update all provided fields
        for field, value in validated_data.items():
            setattr(instance, field, value)
        
        # Mark onboarding as completed if not already
        if not instance.onboarding_completed:
            instance.onboarding_completed = True
            instance.onboarding_completed_at = timezone.now()
        
        instance.save()
        return instance
