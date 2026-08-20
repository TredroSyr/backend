"""Serializers for authentication."""

from __future__ import annotations

from rest_framework import serializers

from apps.authentication.utils import hash_password, normalize_phone, validate_phone
from apps.companies.models import SubUser


class CompanySignupSerializer(serializers.Serializer):
    """Serializer for company registration."""
    
    company_name = serializers.CharField(max_length=255, required=True)
    phone = serializers.CharField(max_length=32, required=True)
    password = serializers.CharField(min_length=8, write_only=True, required=True)
    password_confirm = serializers.CharField(write_only=True, required=True)
    currency = serializers.CharField(max_length=3, required=False, default="SYP")
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        normalized = normalize_phone(value)
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        # Check if phone already exists
        if SubUser.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
        
        return normalized
    
    def validate_company_name(self, value: str) -> str:
        """Validate company name."""
        if not value or not value.strip():
            raise serializers.ValidationError("اسم الشركة مطلوب")
        return value.strip()
    
    def validate_password(self, value: str) -> str:
        """Validate password strength."""
        if len(value) < 8:
            raise serializers.ValidationError(
                "كلمة المرور يجب أن تكون 8 أحرف على الأقل"
            )
        
        # Check for at least one letter and one number
        has_letter = any(c.isalpha() for c in value)
        has_number = any(c.isdigit() for c in value)
        
        if not (has_letter and has_number):
            raise serializers.ValidationError(
                "كلمة المرور يجب أن تحتوي على أحرف وأرقام"
            )
        
        return value
    
    def validate(self, data):
        """Validate that passwords match."""
        if data.get("password") != data.get("password_confirm"):
            raise serializers.ValidationError(
                {"password_confirm": "كلمة المرور غير متطابقة"}
            )
        return data
    
    def create(self, validated_data):
        """This is handled in the view, not here."""
        raise NotImplementedError("Use the view's create logic")


class CompanySigninSerializer(serializers.Serializer):
    """Serializer for company user sign-in."""
    
    phone = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate_phone(self, value: str) -> str:
        """Normalize phone number."""
        return normalize_phone(value)


class RepSigninSerializer(serializers.Serializer):
    """Serializer for sales rep sign-in."""
    
    phone = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate_phone(self, value: str) -> str:
        """Normalize phone number."""
        return normalize_phone(value)


class CustomerSignupSerializer(serializers.Serializer):
    """Serializer for customer self-registration."""
    
    name = serializers.CharField(max_length=255, required=True)
    phone = serializers.CharField(max_length=32, required=True)
    password = serializers.CharField(min_length=6, write_only=True, required=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    referral_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    latitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=9, decimal_places=6, required=False, allow_null=True)
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        from apps.customers.models import Customer
        
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
        from apps.reps.models import Rep
        
        if value and not Rep.objects.filter(referral_code=value, is_active=True).exists():
            raise serializers.ValidationError("كود الإحالة غير صحيح أو غير نشط")
        
        return value
    
    def validate(self, data):
        """Cross-field validation for GPS coordinates."""
        latitude = data.get("latitude")
        longitude = data.get("longitude")
        
        if (latitude is not None) != (longitude is not None):
            raise serializers.ValidationError({
                "location": "يجب تقديم خطوط الطول والعرض معاً أو تركهما فارغين"
            })
        
        return data


class CustomerSigninSerializer(serializers.Serializer):
    """Serializer for customer sign-in."""
    
    phone = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate_phone(self, value: str) -> str:
        """Normalize phone number."""
        return normalize_phone(value)


class TokenRefreshSerializer(serializers.Serializer):
    """Serializer for token refresh."""
    
    refresh = serializers.CharField(required=True)


class SignoutSerializer(serializers.Serializer):
    """Serializer for sign-out."""
    
    refresh = serializers.CharField(required=True)
