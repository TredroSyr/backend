"""Serializers for customer management."""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from rest_framework import serializers

from apps.authentication.utils import normalize_phone, validate_phone
from apps.customers.models import Customer
from apps.reps.models import Rep


class CustomerSignupSerializer(serializers.Serializer):
    """Serializer for customer self-registration or completing signup."""
    
    name = serializers.CharField(max_length=255, required=True)
    phone = serializers.CharField(max_length=32, required=True)
    password = serializers.CharField(min_length=6, write_only=True, required=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    category = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        help_text="Customer category (optional)"
    )
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
        
        # Check if customer exists with this phone
        existing_customer = Customer.objects.filter(phone=normalized).first()
        
        if existing_customer:
            # If customer exists and already has password, can't sign up again
            if existing_customer.has_completed_signup():
                raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
            # If no password set, they're completing signup (allowed)
            # Store existing customer in context for use in create/update
            self.context['existing_customer'] = existing_customer
        
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
    """Full serializer for customer with assigned reps details."""
    
    assigned_reps_details = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "category",
            "assigned_reps",
            "assigned_reps_details",
            "referral_code_used",
            "latitude",
            "longitude",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "referral_code_used", "created_at", "updated_at"]
        extra_kwargs = {
            "assigned_reps": {"write_only": True},
        }
    
    def get_assigned_reps_details(self, obj):
        """Get details of all assigned reps."""
        return [
            {
                "id": rep.id,
                "name": rep.name,
                "phone": rep.phone,
                "company_id": rep.company_id,
                "referral_code": rep.referral_code,
            }
            for rep in obj.assigned_reps.select_related('company').all()
        ]


class CustomerListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for customer list view."""
    
    assigned_reps_count = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "category",
            "assigned_reps_count",
            "referral_code_used",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields
    
    def get_assigned_reps_count(self, obj):
        """Get count of assigned reps."""
        return obj.assigned_reps.count()


class CustomerCreateSerializer(serializers.ModelSerializer):
    """Serializer for company creating a customer manually (no password)."""
    
    assigned_reps = serializers.PrimaryKeyRelatedField(
        queryset=Rep.objects.filter(is_active=True),
        many=True,
        required=False,
        allow_empty=True,
        help_text="List of rep IDs to assign to this customer"
    )
    
    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "email",
            "category",
            "assigned_reps",
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
    
    def validate_assigned_reps(self, value):
        """Validate reps belong to the company and are active."""
        if value:
            company_id = self.context.get("company_id")
            
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            # Filter to only reps from this company
            company_reps = [rep for rep in value if rep.company_id == company_id]
            
            if len(company_reps) != len(value):
                raise serializers.ValidationError("بعض المندوبين لا ينتمون لهذه الشركة")
        
        return value
    
    def create(self, validated_data):
        """Create customer without password (company created)."""
        assigned_reps = validated_data.pop('assigned_reps', [])
        customer = Customer.objects.create(**validated_data)
        
        if assigned_reps:
            customer.assigned_reps.set(assigned_reps)
        
        return customer


class CustomerUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating customer (password cannot be changed by company)."""
    
    assigned_reps = serializers.PrimaryKeyRelatedField(
        queryset=Rep.objects.filter(is_active=True),
        many=True,
        required=False,
        allow_empty=True,
        help_text="List of rep IDs to assign to this customer"
    )
    
    class Meta:
        model = Customer
        fields = [
            "name",
            "phone",
            "email",
            "category",
            "assigned_reps",
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
    
    def validate_assigned_reps(self, value):
        """Validate reps belong to the company and are active."""
        if value:
            company_id = self.context.get("company_id")
            
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            # Filter to only reps from this company
            company_reps = [rep for rep in value if rep.company_id == company_id]
            
            if len(company_reps) != len(value):
                raise serializers.ValidationError("بعض المندوبين لا ينتمون لهذه الشركة")
        
        return value
    
    def update(self, instance, validated_data):
        """Update customer, handling M2M relationship."""
        assigned_reps = validated_data.pop('assigned_reps', None)
        
        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        
        # Update M2M relationship if provided
        if assigned_reps is not None:
            instance.assigned_reps.set(assigned_reps)
        
        return instance


class CustomerSigninSerializer(serializers.Serializer):
    """Serializer for customer sign-in."""
    
    phone = serializers.CharField(required=True)
    password = serializers.CharField(write_only=True, required=True)
    
    def validate_phone(self, value: str) -> str:
        """Normalize phone number."""
        return normalize_phone(value)


class CustomerImportSerializer(serializers.Serializer):
    """Serializer for validating a single row from Excel import."""
    
    row_number = serializers.IntegerField(read_only=True)
    name = serializers.CharField(max_length=255, required=True, allow_blank=False)
    phone = serializers.CharField(max_length=32, required=True, allow_blank=False)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    category = serializers.CharField(
        max_length=100,
        required=False,
        allow_blank=True,
        allow_null=True
    )
    assigned_rep_codes = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        help_text="Comma-separated referral codes"
    )
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True
    )
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        if not value or not value.strip():
            raise serializers.ValidationError("رقم الهاتف مطلوب")
        
        normalized = normalize_phone(value.strip())
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        return normalized
    
    def validate_name(self, value: str) -> str:
        """Validate name is not empty."""
        if not value or not value.strip():
            raise serializers.ValidationError("الاسم مطلوب")
        return value.strip()
    
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
