"""Serializers for customer management."""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from rest_framework import serializers

from apps.authentication.utils import normalize_phone, validate_phone
from apps.customers.models import Customer, CustomerCategory
from apps.reps.models import Rep


class CustomerSignupSerializer(serializers.Serializer):
    """Serializer for customer self-registration or completing signup."""
    
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

    assigned_reps_count = serializers.SerializerMethodField(read_only=True)
    assigned_reps_details = serializers.SerializerMethodField(read_only=True)
    category = serializers.IntegerField(write_only=True, required=False, allow_null=True, help_text="Category ID to assign for this company")
    category_details = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Customer
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "category",
            "category_details",
            "assigned_reps_count",
            "assigned_reps_details",
            "referral_code_used",
            "address",
            "latitude",
            "longitude",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "referral_code_used", "created_at", "updated_at"]

    def get_assigned_reps_count(self, obj):
        """Get count of assigned reps."""
        return obj.assigned_reps.count()
    
    def get_assigned_reps_details(self, obj):
        """Get details of all assigned reps with work days."""
        from apps.reps.models import RepCustomerAssignment
        
        reps = obj.assigned_reps.select_related('company').all()
        result = []
        
        for rep in reps:
            # Get assignment work days
            try:
                assignment = RepCustomerAssignment.objects.get(
                    rep_id=rep.id,
                    customer_id=obj.id
                )
                effective_work_days = assignment.get_effective_work_days()
            except RepCustomerAssignment.DoesNotExist:
                effective_work_days = rep.work_days
            
            result.append({
                "id": rep.id,
                "name": rep.name,
                "phone": rep.phone,
                "company_id": rep.company_id,
                "referral_code": rep.referral_code,
                "work_days": effective_work_days,
            })
        
        return result
    
    def get_category_details(self, obj):
        """Get category details for the current company context."""
        company_id = self.context.get("company_id")
        if company_id:
            category = obj.get_category_for_company(company_id)
            if category:
                return {
                    "id": category.id,
                    "name": category.name,
                    "is_global": category.company_id is None,
                }
        return None

class CustomerCreateSerializer(serializers.Serializer):
    """Serializer for company creating a customer manually (no password)."""
    
    name = serializers.CharField(max_length=255, required=True)
    phone = serializers.CharField(max_length=32, required=True)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    category = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Category ID to assign for this company"
    )
    assigned_rep_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="List of rep IDs to assign to this customer (with empty work_days)"
    )
    address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Street / neighbourhood / city, as a rep would read it"
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
    is_active = serializers.BooleanField(default=True, required=False)
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        normalized = normalize_phone(value)
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        # Check uniqueness
        if Customer.objects.filter(phone=normalized).exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
        
        return normalized
    
    def validate_category(self, value):
        """Validate category exists and is available to this company."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            from django.db.models import Q
            # Check category is either global or belongs to this company
            category_exists = CustomerCategory.objects.filter(
                Q(company__isnull=True) | Q(company_id=company_id),
                id=value,
                is_active=True
            ).exists()
            
            if not category_exists:
                raise serializers.ValidationError("التصنيف غير موجود أو غير متاح")
        
        return value
    
    def validate_assigned_rep_ids(self, value):
        """Validate reps belong to the company and are active."""
        if value:
            company_id = self.context.get("company_id")
            
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            # Check all reps exist and belong to company
            reps = Rep.objects.filter(id__in=value, company_id=company_id, is_active=True)
            
            if reps.count() != len(value):
                raise serializers.ValidationError("بعض المندوبين لا ينتمون لهذه الشركة أو غير نشطين")
        
        return value
    
    def create(self, validated_data):
        """Create customer and assign reps with category."""
        from apps.reps.models import RepCustomerAssignment
        
        assigned_rep_ids = validated_data.pop('assigned_rep_ids', [])
        category_id = validated_data.pop('category', None)
        company_id = self.context.get("company_id")
        
        customer = Customer.objects.create(**validated_data)
        
        # Create rep assignments with empty work_days (will use rep's default)
        if assigned_rep_ids:
            for rep_id in assigned_rep_ids:
                RepCustomerAssignment.objects.create(
                    rep_id=rep_id,
                    customer=customer,
                    work_days=[]
                )
        
        # Assign category for this company
        if category_id and company_id:
            customer.set_category_for_company(company_id, category_id)
        
        return customer


class CustomerUpdateSerializer(serializers.Serializer):
    """Serializer for updating customer (password cannot be changed by company)."""
    
    name = serializers.CharField(max_length=255, required=False)
    phone = serializers.CharField(max_length=32, required=False)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    category = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Category ID to assign for this company"
    )
    assigned_rep_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True,
        help_text="List of rep IDs to assign to this customer (replaces existing assignments)"
    )
    address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Street / neighbourhood / city, as a rep would read it"
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
    is_active = serializers.BooleanField(required=False)
    
    def validate_phone(self, value: str) -> str:
        """Validate and normalize phone number."""
        normalized = normalize_phone(value)
        
        if not validate_phone(normalized):
            raise serializers.ValidationError(
                "رقم الهاتف غير صحيح. الصيغة المطلوبة: +963XXXXXXXXX"
            )
        
        # Check uniqueness, excluding current instance
        customer = self.context.get('customer')
        queryset = Customer.objects.filter(phone=normalized)
        if customer:
            queryset = queryset.exclude(id=customer.id)
        
        if queryset.exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم من قبل")
        
        return normalized
    
    def validate_category(self, value):
        """Validate category exists and is available to this company."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            from django.db.models import Q
            # Check category is either global or belongs to this company
            category_exists = CustomerCategory.objects.filter(
                Q(company__isnull=True) | Q(company_id=company_id),
                id=value,
                is_active=True
            ).exists()
            
            if not category_exists:
                raise serializers.ValidationError("التصنيف غير موجود أو غير متاح")
        
        return value
    
    def validate_assigned_rep_ids(self, value):
        """Validate reps belong to the company and are active."""
        if value:
            company_id = self.context.get("company_id")
            
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            # Check all reps exist and belong to company
            reps = Rep.objects.filter(id__in=value, company_id=company_id, is_active=True)
            
            if reps.count() != len(value):
                raise serializers.ValidationError("بعض المندوبين لا ينتمون لهذه الشركة أو غير نشطين")
        
        return value
    
    def update(self, instance, validated_data):
        """Update customer, handling rep assignments and category."""
        from apps.reps.models import RepCustomerAssignment
        
        assigned_rep_ids = validated_data.pop('assigned_rep_ids', None)
        category_id = validated_data.pop('category', None)
        company_id = self.context.get("company_id")
        
        # Update regular fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        if validated_data:
            instance.save()
        
        # Update rep assignments if provided (replaces existing from this company)
        if assigned_rep_ids is not None and company_id:
            # Remove existing assignments from this company
            RepCustomerAssignment.objects.filter(
                customer=instance,
                rep__company_id=company_id
            ).delete()
            
            # Create new assignments with empty work_days
            for rep_id in assigned_rep_ids:
                RepCustomerAssignment.objects.create(
                    rep_id=rep_id,
                    customer=instance,
                    work_days=[]
                )
        
        # Update category assignment for this company
        if company_id:
            if category_id:
                instance.set_category_for_company(company_id, category_id)
            elif category_id is None and 'category' in self.initial_data:
                # Explicitly set to null, remove assignment
                instance.remove_category_for_company(company_id)
        
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
