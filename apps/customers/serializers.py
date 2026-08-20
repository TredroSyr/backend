"""Serializers for customer management."""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from rest_framework import serializers

from apps.authentication.utils import normalize_phone, validate_phone
from apps.customers.models import Customer
from apps.reps.models import Rep


class CustomerSignupSerializer(serializers.Serializer):
    """Serializer for customer self-registration."""
    
    name = serializers.CharField(max_length=255, required=True)
    phone = serializers.CharField(max_length=32, required=True)
    password = serializers.CharField(min_length=6, write_only=True, required=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    referral_code = serializers.CharField(
        max_length=32, 
        required=False, 
        allow_blank=True,
        help_text="Optional rep referral code for auto-assignment"
    )
    latitude = serializers.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        required=False, 
        allow_null=True,
        help_text="GPS latitude for first visit location"
    )
    longitude = serializers.DecimalField(
        max_digits=9, 
        decimal_places=6, 
        required=False, 
        allow_null=True,
        help_text="GPS longitude for first visit location"
    )
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        normalized = normalize_phone(value)
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        if Customer.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
        
        return normalized
    
    def validate_referral_code(self, value: str) -> str:
        """Validate referral code exists if provided."""
        if value and not Rep.objects.filter(referral_code=value, is_active=True).exists():
            raise serializers.ValidationError("كود الإحالة غير صحيح أو غير نشط")
        
        return value
    
    def validate(self, data):
        """Cross-field validation for GPS coordinates."""
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        
        # Both or neither GPS coordinates
        if (latitude is not None) != (longitude is not None):
            raise serializers.ValidationError({
                "location": "يجب تقديم خطوط الطول والعرض معاً أو تركهما فارغين"
            })
        
        return data


class CustomerSerializer(serializers.ModelSerializer):
    """Full serializer for customer with assigned rep details."""
    
    assigned_rep_name = serializers.CharField(
        source="assigned_rep.name", 
        read_only=True,
        allow_null=True
    )
    assigned_rep_phone = serializers.CharField(
        source="assigned_rep.phone", 
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "assigned_rep",
            "assigned_rep_name",
            "assigned_rep_phone",
            "referral_code_used",
            "latitude",
            "longitude",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "referral_code_used", "created_at", "updated_at"]
        extra_kwargs = {
            "assigned_rep": {"write_only": True},
        }


class CustomerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for customer list view."""
    
    assigned_rep_name = serializers.CharField(
        source="assigned_rep.name", 
        read_only=True,
        allow_null=True
    )
    
    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "assigned_rep_name",
            "referral_code_used",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields


class CustomerCreateSerializer(serializers.ModelSerializer):
    """Serializer for company creating a customer manually."""
    
    password = serializers.CharField(min_length=6, write_only=True, required=True)
    
    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "email",
            "password",
            "assigned_rep",
            "latitude",
            "longitude",
            "is_active",
        ]
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        normalized = normalize_phone(value)
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        # Check uniqueness, excluding current instance on update
        queryset = Customer.objects.filter(phone=normalized)
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
        
        return normalized
    
    def validate_assigned_rep(self, value):
        """Validate rep belongs to the company and is active."""
        if value:
            company_id = self.context.get("company_id")
            
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            if value.company_id != company_id:
                raise serializers.ValidationError("المندوب لا ينتمي لهذه الشركة")
            
            if not value.is_active:
                raise serializers.ValidationError("المندوب غير نشط")
        
        return value
    
    def create(self, validated_data):
        """Create customer with hashed password."""
        validated_data["password"] = make_password(validated_data["password"])
        return super().create(validated_data)
    
    def update(self, instance, validated_data):
        """Update customer, hashing password if provided."""
        if "password" in validated_data:
            validated_data["password"] = make_password(validated_data["password"])
        
        return super().update(instance, validated_data)


class CustomerUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating customer (no password required)."""
    
    password = serializers.CharField(
        min_length=6, 
        write_only=True, 
        required=False,
        help_text="Only include if changing password"
    )
    
    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "email",
            "password",
            "assigned_rep",
            "latitude",
            "longitude",
            "is_active",
        ]
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        normalized = normalize_phone(value)
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        # Check uniqueness, excluding current instance
        queryset = Customer.objects.filter(phone=normalized)
        if self.instance:
            queryset = queryset.exclude(id=self.instance.id)
        
        if queryset.exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
        
        return normalized
    
    def validate_assigned_rep(self, value):
        """Validate rep belongs to the company and is active."""
        if value:
            company_id = self.context.get("company_id")
            
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            if value.company_id != company_id:
                raise serializers.ValidationError("المندوب لا ينتمي لهذه الشركة")
            
            if not value.is_active:
                raise serializers.ValidationError("المندوب غير نشط")
        
        return value
    
    def update(self, instance, validated_data):
        """Update customer, hashing password if provided."""
        if "password" in validated_data:
            validated_data["password"] = make_password(validated_data["password"])
        
        return super().update(instance, validated_data)


class CustomerSigninSerializer(serializers.Serializer):
    """Serializer for customer sign-in."""
    
    phone = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate_phone(self, value: str) -> str:
        """Normalize phone number."""
        return normalize_phone(value)
