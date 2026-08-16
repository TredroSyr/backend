"""Serializers for company management."""

from __future__ import annotations

from django.contrib.auth.hashers import make_password
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from apps.companies.models import Company, ModulePermission, Role, SubUser


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


class ModulePermissionSerializer(serializers.Serializer):
    """Serializer for module permission assignment."""
    
    module = serializers.CharField(max_length=64)
    can_view = serializers.BooleanField(default=False)
    can_action = serializers.BooleanField(default=False)
    
    def validate_module(self, value):
        """Validate that module is one of the six available modules."""
        allowed_modules = [
            "customers",
            "invoices",
            "orders",
            "products",
            "reps",
            "notifications",
        ]
        
        if value not in allowed_modules:
            raise serializers.ValidationError(
                f"Module must be one of: {', '.join(allowed_modules)}"
            )
        
        return value


class CreateSubUserSerializer(serializers.ModelSerializer):
    """Serializer for creating a sub-user with permissions."""
    
    permissions = ModulePermissionSerializer(many=True, required=True)
    password = serializers.CharField(write_only=True, min_length=6, max_length=128)
    
    class Meta:
        model = SubUser
        fields = [
            "name",
            "phone",
            "email",
            "password",
            "permissions",
        ]
    
    def validate_permissions(self, value):
        """Validate that at least one permission is provided."""
        if not value:
            raise serializers.ValidationError("يجب تحديد صلاحية واحدة على الأقل")
        
        # Validate that each permission has at least can_view enabled
        for perm in value:
            if not perm.get("can_view") and not perm.get("can_action"):
                raise serializers.ValidationError(
                    f"يجب تفعيل صلاحية العرض أو الإجراء للوحدة {perm.get('module')}"
                )
        
        # Check for duplicate modules
        modules = [perm.get("module") for perm in value]
        if len(modules) != len(set(modules)):
            raise serializers.ValidationError("لا يمكن تحديد صلاحيات مكررة لنفس الوحدة")
        
        return value
    
    def validate_phone(self, value):
        """Validate that phone is unique within the company."""
        company = self.context.get("company")
        if not company:
            raise serializers.ValidationError("لم يتم العثور على معلومات الشركة")
        
        if SubUser.objects.filter(company=company, phone=value).exists():
            raise serializers.ValidationError("رقم الهاتف مستخدم بالفعل في هذه الشركة")
        
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        """Create sub-user with role and permissions."""
        permissions_data = validated_data.pop("permissions")
        company = self.context.get("company")
        
        if not company:
            raise serializers.ValidationError("لم يتم العثور على معلومات الشركة")
        
        # Create a role for this sub-user (named after the user for simplicity)
        role = Role.objects.create(
            company=company,
            name=f"{validated_data['name']} - Role",
        )
        
        # Create module permissions for the role
        for perm_data in permissions_data:
            ModulePermission.objects.create(
                company=company,
                role=role,
                module=perm_data["module"],
                can_view=perm_data["can_view"],
                can_action=perm_data["can_action"],
            )
        
        # Hash the password
        validated_data["password"] = make_password(validated_data["password"])
        
        # Create the sub-user
        sub_user = SubUser.objects.create(
            company=company,
            role=role,
            is_owner=False,
            **validated_data,
        )
        
        return sub_user


class SubUserDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for SubUser with permissions."""
    
    permissions = serializers.SerializerMethodField()
    role_name = serializers.CharField(source="role.name", read_only=True)
    
    class Meta:
        model = SubUser
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "is_owner",
            "is_active",
            "role_name",
            "permissions",
            "created_at",
        ]
        read_only_fields = ["id", "is_owner", "created_at"]
    
    def get_permissions(self, obj):
        """Get module permissions for this sub-user."""
        if obj.is_owner:
            # Owner has all permissions
            return [
                {
                    "module": module,
                    "can_view": True,
                    "can_action": True,
                }
                for module in [
                    "customers",
                    "invoices",
                    "orders",
                    "products",
                    "reps",
                    "notifications",
                ]
            ]
        
        if not obj.role:
            return []
        
        permissions = ModulePermission.objects.filter(role=obj.role)
        return [
            {
                "module": perm.module,
                "can_view": perm.can_view,
                "can_action": perm.can_action,
            }
            for perm in permissions
        ]
