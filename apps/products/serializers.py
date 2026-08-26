"""Serializers for product management."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from rest_framework import serializers

from apps.common.models import Currency, UnitOfMeasure
from apps.products.models import (
    CustomFieldDefinition,
    CustomFieldValue,
    Product,
    ProductCategory,
    ProductImage,
    ProductPrice,
    ProductWarehouseStock,
    Warehouse,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    """Serializer for ProductCategory with parent/children info."""
    
    children_count = serializers.SerializerMethodField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)
    
    class Meta:
        model = ProductCategory
        fields = [
            "id",
            "name",
            "parent",
            "parent_name",
            "children_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def get_children_count(self, obj):
        """Get count of direct children."""
        return obj.children.filter(is_active=True).count()
    
    def validate_parent(self, value):
        """Validate parent belongs to same company."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            if value.company_id != company_id:
                raise serializers.ValidationError("التصنيف الأب يجب أن ينتمي لنفس الشركة")
            
            # Prevent circular reference
            if self.instance and value.id == self.instance.id:
                raise serializers.ValidationError("لا يمكن أن يكون التصنيف والداً لنفسه")
        
        return value


class ProductImageSerializer(serializers.ModelSerializer):
    """Serializer for ProductImage."""
    
    class Meta:
        model = ProductImage
        fields = [
            "id",
            "image",
            "alt_text",
            "is_primary",
            "sort_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def validate(self, data):
        """Validate primary image constraint."""
        product = self.context.get("product")
        is_primary = data.get("is_primary", False)
        
        # If setting as primary, we'll handle unsetting others in the view
        if is_primary and product:
            # Check if there's already a primary image (excluding current instance)
            existing_primary = ProductImage.objects.filter(
                product=product,
                is_primary=True
            )
            
            if self.instance:
                existing_primary = existing_primary.exclude(id=self.instance.id)
            
            # Store this info for the view to handle in a transaction
            if existing_primary.exists():
                data["_unset_other_primary"] = True
        
        return data


class ProductPriceSerializer(serializers.ModelSerializer):
    """Serializer for ProductPrice with nested currency/category details."""
    
    currency_code = serializers.CharField(source="currency.code", read_only=True)
    currency_symbol = serializers.CharField(source="currency.symbol", read_only=True)
    customer_category_name = serializers.CharField(
        source="customer_category.name", 
        read_only=True, 
        allow_null=True
    )
    
    class Meta:
        model = ProductPrice
        fields = [
            "id",
            "currency",
            "currency_code",
            "currency_symbol",
            "price_type",
            "customer_category",
            "customer_category_name",
            "price",
            "is_default",
            "valid_from",
            "valid_until",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def validate_currency(self, value):
        """Validate currency exists and is active."""
        if not Currency.objects.filter(id=value.id, is_active=True).exists():
            raise serializers.ValidationError("العملة غير موجودة أو غير نشطة")
        return value
    
    def validate_customer_category(self, value):
        """Validate customer category belongs to same company if set."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            # Customer categories can be global (company=null) or company-specific
            from django.db.models import Q
            from apps.customers.models import CustomerCategory
            
            category_valid = CustomerCategory.objects.filter(
                Q(company__isnull=True) | Q(company_id=company_id),
                id=value.id,
                is_active=True
            ).exists()
            
            if not category_valid:
                raise serializers.ValidationError("تصنيف العميل غير موجود أو غير متاح")
        
        return value
    
    def validate(self, data):
        """Validate price constraints mirroring DB constraints."""
        product = self.context.get("product")
        if not product:
            raise serializers.ValidationError("معلومات المنتج غير موجودة")
        
        currency = data.get("currency")
        price_type = data.get("price_type")
        customer_category = data.get("customer_category")
        is_default = data.get("is_default", False)
        
        # Validate general price uniqueness (currency + price_type, no customer_category)
        if customer_category is None:
            existing = ProductPrice.objects.filter(
                product=product,
                currency=currency,
                price_type=price_type,
                customer_category__isnull=True
            )
            
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            
            if existing.exists():
                raise serializers.ValidationError({
                    "currency": "يوجد سعر عام بالفعل لهذه العملة ونوع السعر"
                })
        else:
            # Validate customer-category price uniqueness
            existing = ProductPrice.objects.filter(
                product=product,
                currency=currency,
                price_type=price_type,
                customer_category=customer_category
            )
            
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            
            if existing.exists():
                raise serializers.ValidationError({
                    "customer_category": "يوجد سعر بالفعل لهذه العملة ونوع السعر وتصنيف العميل"
                })
        
        # Validate only one default price per product (must be general, not customer-category)
        if is_default:
            if customer_category is not None:
                raise serializers.ValidationError({
                    "is_default": "السعر الافتراضي يجب أن يكون عاماً (بدون تصنيف عميل)"
                })
            
            existing_default = ProductPrice.objects.filter(
                product=product,
                is_default=True,
                customer_category__isnull=True
            )
            
            if self.instance:
                existing_default = existing_default.exclude(id=self.instance.id)
            
            if existing_default.exists():
                raise serializers.ValidationError({
                    "is_default": "يوجد سعر افتراضي بالفعل لهذا المنتج"
                })
        
        return data


class CustomFieldDefinitionSerializer(serializers.ModelSerializer):
    """Serializer for CustomFieldDefinition."""
    
    class Meta:
        model = CustomFieldDefinition
        fields = [
            "id",
            "key",
            "label",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def validate_key(self, value):
        """Validate key uniqueness within company."""
        company_id = self.context.get("company_id")
        if not company_id:
            raise serializers.ValidationError("معلومات الشركة غير موجودة")
        
        existing = CustomFieldDefinition.objects.filter(
            company_id=company_id,
            key=value
        )
        
        if self.instance:
            existing = existing.exclude(id=self.instance.id)
        
        if existing.exists():
            raise serializers.ValidationError("يوجد حقل مخصص بنفس المفتاح")
        
        return value


class ProductWarehouseStockSerializer(serializers.ModelSerializer):
    """Read-only serializer for ProductWarehouseStock."""
    
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    
    class Meta:
        model = ProductWarehouseStock
        fields = [
            "id",
            "warehouse",
            "warehouse_name",
            "product",
            "product_name",
            "product_sku",
            "quantity",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class WarehouseSerializer(serializers.ModelSerializer):
    """Serializer for Warehouse."""
    
    rep_name = serializers.CharField(source="rep.name", read_only=True, allow_null=True)
    
    class Meta:
        model = Warehouse
        fields = [
            "id",
            "name",
            "address",
            "kind",
            "owner_type",
            "rep",
            "rep_name",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def validate(self, data):
        """Validate owner_type and rep consistency."""
        owner_type = data.get("owner_type")
        rep = data.get("rep")
        
        if owner_type == "company" and rep is not None:
            raise serializers.ValidationError({
                "rep": "مستودع الشركة لا يجب أن يرتبط بمندوب"
            })
        
        if owner_type == "rep" and rep is None:
            raise serializers.ValidationError({
                "rep": "مستودع المندوب يجب أن يرتبط بمندوب"
            })
        
        # Validate rep belongs to same company if set
        if rep:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            from apps.reps.models import Rep
            
            if not Rep.objects.filter(id=rep.id, company_id=company_id, is_active=True).exists():
                raise serializers.ValidationError({
                    "rep": "المندوب غير موجود أو لا ينتمي لهذه الشركة"
                })
        
        return data


class ProductListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for product listing."""
    
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    primary_image = serializers.SerializerMethodField(read_only=True)
    default_price = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "barcode",
            "brand",
            "category",
            "category_name",
            "unit",
            "unit_name",
            "is_active",
            "is_sellable",
            "is_purchasable",
            "primary_image",
            "default_price",
            "created_at",
        ]
        read_only_fields = fields
    
    def get_primary_image(self, obj):
        """Get primary image URL if exists."""
        primary = obj.images.filter(is_primary=True).first()
        if primary:
            return {
                "id": primary.id,
                "image": primary.image.url if primary.image else None,
                "alt_text": primary.alt_text,
            }
        return None
    
    def get_default_price(self, obj):
        """Get default price if exists."""
        default = obj.prices.filter(is_default=True, customer_category__isnull=True).first()
        if default:
            return {
                "price": str(default.price),
                "currency_code": default.currency.code,
                "currency_symbol": default.currency.symbol,
                "price_type": default.price_type,
            }
        return None


class ProductDetailSerializer(serializers.ModelSerializer):
    """Detailed serializer for product with nested data."""
    
    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    prices = ProductPriceSerializer(many=True, read_only=True)
    custom_fields = serializers.SerializerMethodField(read_only=True)
    
    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "description",
            "sku",
            "barcode",
            "brand",
            "category",
            "category_name",
            "unit",
            "unit_name",
            "unit_code",
            "weight",
            "weight_unit",
            "length",
            "width",
            "height",
            "dimension_unit",
            "reorder_point",
            "reorder_quantity",
            "is_taxable",
            "tax_rate",
            "is_sellable",
            "is_purchasable",
            "external_reference",
            "notes",
            "is_active",
            "images",
            "prices",
            "custom_fields",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "images", "prices", "custom_fields", "created_at", "updated_at"]
    
    def get_custom_fields(self, obj):
        """Get custom field values as a flat dict."""
        values = obj.custom_field_values.select_related("definition").all()
        return {
            value.definition.key: value.value
            for value in values
        }
    
    def validate_category(self, value):
        """Validate category belongs to same company."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            if value.company_id != company_id:
                raise serializers.ValidationError("التصنيف يجب أن ينتمي لنفس الشركة")
        
        return value
    
    def validate_unit(self, value):
        """Validate unit exists and is active."""
        if not UnitOfMeasure.objects.filter(id=value.id, is_active=True).exists():
            raise serializers.ValidationError("الوحدة غير موجودة أو غير نشطة")
        return value


class ProductWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products with custom fields."""
    
    custom_fields = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        write_only=True,
        help_text="Dict of custom field key-value pairs"
    )
    
    class Meta:
        model = Product
        fields = [
            "name",
            "description",
            "sku",
            "barcode",
            "brand",
            "category",
            "unit",
            "weight",
            "weight_unit",
            "length",
            "width",
            "height",
            "dimension_unit",
            "reorder_point",
            "reorder_quantity",
            "is_taxable",
            "tax_rate",
            "is_sellable",
            "is_purchasable",
            "external_reference",
            "notes",
            "is_active",
            "custom_fields",
        ]
    
    def validate_category(self, value):
        """Validate category belongs to same company."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            if value.company_id != company_id:
                raise serializers.ValidationError("التصنيف يجب أن ينتمي لنفس الشركة")
        
        return value
    
    def validate_unit(self, value):
        """Validate unit exists and is active."""
        if not UnitOfMeasure.objects.filter(id=value.id, is_active=True).exists():
            raise serializers.ValidationError("الوحدة غير موجودة أو غير نشطة")
        return value
    
    def validate_sku(self, value):
        """Validate SKU uniqueness within company if provided."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            existing = Product.objects.filter(company_id=company_id, sku=value)
            
            if self.instance:
                existing = existing.exclude(id=self.instance.id)
            
            if existing.exists():
                raise serializers.ValidationError("رمز المنتج (SKU) مستخدم بالفعل")
        
        return value
    
    def validate_custom_fields(self, value):
        """Validate custom field keys exist for this company."""
        if value:
            company_id = self.context.get("company_id")
            if not company_id:
                raise serializers.ValidationError("معلومات الشركة غير موجودة")
            
            # Get all valid keys for this company
            valid_keys = set(
                CustomFieldDefinition.objects.filter(
                    company_id=company_id,
                    is_active=True
                ).values_list("key", flat=True)
            )
            
            # Check if all provided keys are valid
            invalid_keys = set(value.keys()) - valid_keys
            if invalid_keys:
                raise serializers.ValidationError(
                    f"حقول مخصصة غير صالحة: {', '.join(invalid_keys)}"
                )
        
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        """Create product with custom fields."""
        custom_fields = validated_data.pop("custom_fields", {})
        company_id = self.context.get("company_id")
        
        # Create product
        product = Product.objects.create(company_id=company_id, **validated_data)
        
        # Create custom field values
        if custom_fields:
            self._upsert_custom_fields(product, custom_fields, company_id)
        
        return product
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Update product with custom fields."""
        custom_fields = validated_data.pop("custom_fields", None)
        company_id = self.context.get("company_id")
        
        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # Update custom field values if provided
        if custom_fields is not None:
            self._upsert_custom_fields(instance, custom_fields, company_id)
        
        return instance
    
    def _upsert_custom_fields(self, product, custom_fields, company_id):
        """Upsert custom field values for a product."""
        # Get definitions for all keys
        definitions = CustomFieldDefinition.objects.filter(
            company_id=company_id,
            key__in=custom_fields.keys(),
            is_active=True
        )
        
        definition_map = {d.key: d for d in definitions}
        
        # Upsert values
        for key, value in custom_fields.items():
            definition = definition_map.get(key)
            if definition:
                CustomFieldValue.objects.update_or_create(
                    product=product,
                    definition=definition,
                    defaults={"value": value}
                )
