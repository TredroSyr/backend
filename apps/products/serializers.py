"""Serializers for product management."""

from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
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
from apps.products.services.images import primary_image_payload


class ProductCategorySerializer(serializers.ModelSerializer):
    """Serializer for ProductCategory with parent/children info."""
    
    children_count = serializers.SerializerMethodField(read_only=True)
    products_count = serializers.SerializerMethodField(read_only=True)
    parent_name = serializers.CharField(source="parent.name", read_only=True, allow_null=True)

    class Meta:
        model = ProductCategory
        fields = [
            "id",
            "name",
            "parent",
            "parent_name",
            "children_count",
            "products_count",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
    
    def get_children_count(self, obj):
        """Get count of direct children."""
        return obj.children.filter(is_active=True).count()

    def get_products_count(self, obj):
        """Number of active products in this category, for list badges."""
        return obj.products.filter(is_active=True).count()
    
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
    currency_name = serializers.CharField(source="currency.name", read_only=True)
    currency_symbol = serializers.CharField(source="currency.symbol", read_only=True)
    price_type_display = serializers.CharField(source="get_price_type_display", read_only=True)
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
            "currency_name",
            "currency_symbol",
            "price_type",
            "price_type_display",
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


class WarehouseStockRowSerializer(serializers.ModelSerializer):
    """Per-warehouse quantities as shown on a product's detail page.

    Product identity is deliberately absent: the rows are always read under one
    product, so repeating its name on every row would only pad the payload.
    """

    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    warehouse_kind = serializers.CharField(source="warehouse.kind", read_only=True)
    warehouse_owner_type = serializers.CharField(source="warehouse.owner_type", read_only=True)
    warehouse_is_active = serializers.BooleanField(source="warehouse.is_active", read_only=True)
    rep = serializers.IntegerField(source="warehouse.rep_id", read_only=True, allow_null=True)
    rep_name = serializers.CharField(source="warehouse.rep.name", read_only=True, allow_null=True)

    class Meta:
        model = ProductWarehouseStock
        fields = [
            "id",
            "warehouse",
            "warehouse_name",
            "warehouse_kind",
            "warehouse_owner_type",
            "warehouse_is_active",
            "rep",
            "rep_name",
            "quantity",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductWarehouseStockSerializer(serializers.ModelSerializer):
    """Read-only serializer for ProductWarehouseStock."""

    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    warehouse_kind = serializers.CharField(source="warehouse.kind", read_only=True)
    warehouse_owner_type = serializers.CharField(source="warehouse.owner_type", read_only=True)
    warehouse_is_active = serializers.BooleanField(source="warehouse.is_active", read_only=True)
    rep = serializers.IntegerField(source="warehouse.rep_id", read_only=True, allow_null=True)
    rep_name = serializers.CharField(source="warehouse.rep.name", read_only=True, allow_null=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_barcode = serializers.CharField(source="product.barcode", read_only=True)
    product_is_active = serializers.BooleanField(source="product.is_active", read_only=True)
    unit = serializers.IntegerField(source="product.unit_id", read_only=True)
    unit_name = serializers.CharField(source="product.unit.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    reorder_point = serializers.DecimalField(
        source="product.reorder_point",
        max_digits=14,
        decimal_places=3,
        read_only=True,
        allow_null=True,
    )
    is_low_stock = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = ProductWarehouseStock
        fields = [
            "id",
            "warehouse",
            "warehouse_name",
            "warehouse_kind",
            "warehouse_owner_type",
            "warehouse_is_active",
            "rep",
            "rep_name",
            "product",
            "product_name",
            "product_sku",
            "product_barcode",
            "product_is_active",
            "unit",
            "unit_name",
            "unit_code",
            "quantity",
            "reorder_point",
            "is_low_stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_is_low_stock(self, obj):
        """True when this warehouse alone is at or below the product's reorder point.

        Null when the product has no reorder point, so the frontend can tell
        "healthy" apart from "not tracked".
        """
        reorder_point = obj.product.reorder_point
        if reorder_point is None:
            return None
        return obj.quantity <= reorder_point


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


class ProductDisplayFieldsMixin:
    """Derived product fields shared by the list and detail serializers.

    Every getter first looks for an annotation or a prefetch the viewset already
    arranged and only falls back to its own query, so serializing N products
    stays at a fixed number of queries.
    """

    def _is_prefetched(self, obj, name):
        return name in getattr(obj, "_prefetched_objects_cache", {})

    def _default_price_object(self, obj):
        # `default_prices` is the filtered prefetch the list view sets up.
        default_prices = getattr(obj, "default_prices", None)
        if default_prices is not None:
            return default_prices[0] if default_prices else None

        if self._is_prefetched(obj, "prices"):
            return next(
                (
                    price
                    for price in obj.prices.all()
                    if price.is_default and price.customer_category_id is None
                ),
                None,
            )

        return (
            obj.prices.filter(is_default=True, customer_category__isnull=True)
            .select_related("currency")
            .first()
        )

    def _total_stock(self, obj):
        total = getattr(obj, "total_stock_sum", None)
        if total is not None:
            return total

        if self._is_prefetched(obj, "warehouse_stocks"):
            return sum(
                (stock.quantity for stock in obj.warehouse_stocks.all()),
                Decimal("0"),
            )

        return obj.warehouse_stocks.aggregate(total=Sum("quantity"))["total"] or Decimal("0")

    def get_primary_image(self, obj):
        """Cover image for cards and detail headers, or None."""
        return primary_image_payload(obj, self.context.get("request"))

    def get_default_price(self, obj):
        """Price to show when no customer/currency context is given, or None."""
        default = self._default_price_object(obj)
        if default is None:
            return None

        return {
            "id": default.id,
            "price": str(default.price),
            "currency": default.currency_id,
            "currency_code": default.currency.code,
            "currency_name": default.currency.name,
            "currency_symbol": default.currency.symbol,
            "price_type": default.price_type,
        }

    def get_total_stock(self, obj):
        """Quantity on hand across every warehouse, as a string like other decimals."""
        return str(self._total_stock(obj))

    def get_is_low_stock(self, obj):
        """True when total stock is at or below the reorder point.

        Null when no reorder point is set: "not tracked" is a different answer
        from "stock is fine".
        """
        if obj.reorder_point is None:
            return None
        return self._total_stock(obj) <= obj.reorder_point

    def get_images_count(self, obj):
        count = getattr(obj, "images_count_total", None)
        if count is not None:
            return count
        if self._is_prefetched(obj, "images"):
            return len(obj.images.all())
        return obj.images.count()

    def get_prices_count(self, obj):
        count = getattr(obj, "prices_count_total", None)
        if count is not None:
            return count
        if self._is_prefetched(obj, "prices"):
            return len(obj.prices.all())
        return obj.prices.count()


class ProductListSerializer(ProductDisplayFieldsMixin, serializers.ModelSerializer):
    """Lightweight serializer for product listing."""

    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    primary_image = serializers.SerializerMethodField(read_only=True)
    default_price = serializers.SerializerMethodField(read_only=True)
    total_stock = serializers.SerializerMethodField(read_only=True)
    is_low_stock = serializers.SerializerMethodField(read_only=True)
    images_count = serializers.SerializerMethodField(read_only=True)
    prices_count = serializers.SerializerMethodField(read_only=True)

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
            "is_active",
            "is_sellable",
            "is_purchasable",
            "status",
            "status_display",
            "external_reference",
            "notes",
            "primary_image",
            "default_price",
            "total_stock",
            "is_low_stock",
            "images_count",
            "prices_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ProductDetailSerializer(ProductDisplayFieldsMixin, serializers.ModelSerializer):
    """Detailed serializer for product with nested data."""

    category_name = serializers.CharField(source="category.name", read_only=True, allow_null=True)
    category_parent = serializers.IntegerField(
        source="category.parent_id", read_only=True, allow_null=True
    )
    category_parent_name = serializers.CharField(
        source="category.parent.name", read_only=True, allow_null=True
    )
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    images = ProductImageSerializer(many=True, read_only=True)
    prices = ProductPriceSerializer(many=True, read_only=True)
    custom_fields = serializers.SerializerMethodField(read_only=True)
    custom_field_values = serializers.SerializerMethodField(read_only=True)
    warehouse_stocks = serializers.SerializerMethodField(read_only=True)
    primary_image = serializers.SerializerMethodField(read_only=True)
    default_price = serializers.SerializerMethodField(read_only=True)
    total_stock = serializers.SerializerMethodField(read_only=True)
    is_low_stock = serializers.SerializerMethodField(read_only=True)
    images_count = serializers.SerializerMethodField(read_only=True)
    prices_count = serializers.SerializerMethodField(read_only=True)
    
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
            "category_parent",
            "category_parent_name",
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
            "status",
            "status_display",
            "is_active",
            "images",
            "prices",
            "custom_fields",
            "custom_field_values",
            "primary_image",
            "default_price",
            "warehouse_stocks",
            "total_stock",
            "is_low_stock",
            "images_count",
            "prices_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "images",
            "prices",
            "custom_fields",
            "custom_field_values",
            "primary_image",
            "default_price",
            "warehouse_stocks",
            "total_stock",
            "is_low_stock",
            "images_count",
            "prices_count",
            "created_at",
            "updated_at",
        ]

    def _custom_field_values(self, obj):
        """The rows behind both custom-field outputs, read once.

        Two fields render them, so the list is cached on the instance: without
        it the definition join would be paid twice on every product.
        """
        cached = getattr(obj, "_display_custom_field_values", None)
        if cached is None:
            values = (
                obj.custom_field_values.all()
                if self._is_prefetched(obj, "custom_field_values")
                else obj.custom_field_values.select_related("definition")
            )
            cached = list(values)
            obj._display_custom_field_values = cached
        return cached

    def get_custom_fields(self, obj):
        """Get custom field values as a flat dict."""
        return {
            value.definition.key: value.value
            for value in self._custom_field_values(obj)
        }

    def get_custom_field_values(self, obj):
        """Same values as `custom_fields`, but carrying the labels to render.

        The flat dict is what write requests echo back; this list is what a form
        can draw without a second call to fetch every definition's label.
        """
        return [
            {
                "id": value.id,
                "definition": value.definition_id,
                "key": value.definition.key,
                "label": value.definition.label,
                "value": value.value,
            }
            for value in self._custom_field_values(obj)
        ]

    def get_warehouse_stocks(self, obj):
        """Quantity per warehouse, so the detail page can show where stock sits."""
        return WarehouseStockRowSerializer(
            obj.warehouse_stocks.all(), many=True, context=self.context
        ).data
    
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


class ProductImageWriteSerializer(serializers.ModelSerializer):
    """Nested serializer for creating/updating product images."""
    
    class Meta:
        model = ProductImage
        fields = ["id", "image", "alt_text", "is_primary", "sort_order"]
        extra_kwargs = {
            "id": {"required": False},  # ID is optional (used for updates)
        }


class ProductPriceWriteSerializer(serializers.ModelSerializer):
    """Nested serializer for creating/updating product prices."""
    
    class Meta:
        model = ProductPrice
        fields = [
            "id",
            "currency",
            "price_type",
            "customer_category",
            "price",
            "is_default",
            "valid_from",
            "valid_until",
        ]
        extra_kwargs = {
            "id": {"required": False},  # ID is optional (used for updates)
        }
    
    def validate_currency(self, value):
        """Validate currency exists and is active."""
        if not Currency.objects.filter(id=value.id, is_active=True).exists():
            raise serializers.ValidationError("العملة غير موجودة أو غير نشطة")
        return value


class ProductWriteSerializer(serializers.ModelSerializer):
    """Serializer for creating/updating products with nested related models."""
    
    custom_fields = serializers.DictField(
        child=serializers.CharField(allow_blank=True),
        required=False,
        write_only=True,
        help_text="Dict of custom field key-value pairs"
    )
    images = ProductImageWriteSerializer(many=True, required=False)
    prices = ProductPriceWriteSerializer(many=True, required=False)
    
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
            "status",
            "is_active",
            "custom_fields",
            "images",
            "prices",
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
    
    def validate_prices(self, value):
        """Validate price data and constraints."""
        if not value:
            return value
        
        company_id = self.context.get("company_id")
        
        # Check for duplicate price definitions in the same request
        price_keys = []
        for price_data in value:
            currency = price_data.get("currency")
            price_type = price_data.get("price_type", "standard")
            customer_category = price_data.get("customer_category")
            
            # Validate customer category if provided
            if customer_category:
                from django.db.models import Q
                from apps.customers.models import CustomerCategory
                
                category_valid = CustomerCategory.objects.filter(
                    Q(company__isnull=True) | Q(company_id=company_id),
                    id=customer_category.id,
                    is_active=True
                ).exists()
                
                if not category_valid:
                    raise serializers.ValidationError("تصنيف العميل غير موجود أو غير متاح")
            
            # Create a key for uniqueness checking
            key = (currency.id if currency else None, price_type, customer_category.id if customer_category else None)
            if key in price_keys:
                raise serializers.ValidationError("يوجد أسعار مكررة في الطلب")
            price_keys.append(key)
        
        # Validate only one default price
        default_count = sum(1 for p in value if p.get("is_default", False))
        if default_count > 1:
            raise serializers.ValidationError("يمكن تحديد سعر افتراضي واحد فقط")
        
        # Default price must not have customer_category
        for price_data in value:
            if price_data.get("is_default") and price_data.get("customer_category"):
                raise serializers.ValidationError("السعر الافتراضي يجب أن يكون عاماً (بدون تصنيف عميل)")
        
        return value
    
    def validate_images(self, value):
        """Validate image data."""
        if not value:
            return value
        
        # Count primary images
        primary_count = sum(1 for img in value if img.get("is_primary", False))
        if primary_count > 1:
            raise serializers.ValidationError("يمكن تحديد صورة رئيسية واحدة فقط")
        
        return value
    
    @transaction.atomic
    def create(self, validated_data):
        """Create product with nested images, prices, and custom fields."""
        custom_fields = validated_data.pop("custom_fields", {})
        images_data = validated_data.pop("images", [])
        prices_data = validated_data.pop("prices", [])
        company_id = self.context.get("company_id")
        
        # Create product
        product = Product.objects.create(company_id=company_id, **validated_data)
        
        # Create images
        if images_data:
            self._create_images(product, images_data)
        
        # Create prices
        if prices_data:
            self._create_prices(product, prices_data)
        
        # Create custom field values
        if custom_fields:
            self._upsert_custom_fields(product, custom_fields, company_id)
        
        return product
    
    @transaction.atomic
    def update(self, instance, validated_data):
        """Update product with nested images, prices, and custom fields."""
        # Only pop if the key exists in validated_data - this ensures we don't update
        # nested relations unless they were explicitly provided in the request
        custom_fields = validated_data.pop("custom_fields") if "custom_fields" in validated_data else None
        images_data = validated_data.pop("images") if "images" in validated_data else None
        prices_data = validated_data.pop("prices") if "prices" in validated_data else None
        company_id = self.context.get("company_id")
        
        # Update product fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        
        instance.save()
        
        # Update images only if explicitly provided in request
        if images_data is not None:
            self._update_images(instance, images_data)
        
        # Update prices only if explicitly provided in request
        if prices_data is not None:
            self._update_prices(instance, prices_data)
        
        # Update custom field values only if explicitly provided in request
        if custom_fields is not None:
            self._upsert_custom_fields(instance, custom_fields, company_id)
        
        return instance
    
    def _create_images(self, product, images_data):
        """Create images for a product."""
        has_primary = any(img.get("is_primary", False) for img in images_data)
        
        for idx, image_data in enumerate(images_data):
            # If no primary specified, make the first one primary
            if not has_primary and idx == 0:
                image_data["is_primary"] = True
            
            ProductImage.objects.create(product=product, **image_data)
    
    def _update_images(self, product, images_data):
        """Update images for a product (replace strategy)."""
        keep_ids = [img["id"] for img in images_data if "id" in img]

        # Delete images not in the incoming list
        ProductImage.objects.filter(product=product).exclude(id__in=keep_ids).delete()

        # If a new primary is being set, unset any existing primary first
        has_new_primary = any(img.get("is_primary", False) for img in images_data)
        if has_new_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(is_primary=False)

        touched = []
        for image_data in images_data:
            image_id = image_data.pop("id", None)

            if image_id:
                # Update existing image: use model instance to avoid FileField issues
                image = ProductImage.objects.get(id=image_id, product=product)
                for field, value in image_data.items():
                    setattr(image, field, value)
                image.save()
            else:
                image = ProductImage.objects.create(product=product, **image_data)

            touched.append(image)

        # Invariant: if the product has any images left, exactly one must be primary.
        if touched and not ProductImage.objects.filter(product=product, is_primary=True).exists():
            fallback = touched[0]
            fallback.is_primary = True
            fallback.save(update_fields=["is_primary"])
    
    def _create_prices(self, product, prices_data):
        """Create prices for a product."""
        for price_data in prices_data:
            ProductPrice.objects.create(product=product, **price_data)
    
    def _update_prices(self, product, prices_data):
        """Update prices for a product (replace strategy)."""
        keep_ids = [price["id"] for price in prices_data if "id" in price]

        # Delete prices not in the incoming list
        ProductPrice.objects.filter(product=product).exclude(id__in=keep_ids).delete()

        for price_data in prices_data:
            price_id = price_data.pop("id", None)

            if price_id:
                ProductPrice.objects.filter(id=price_id, product=product).update(**price_data)
                continue

            currency = price_data.get("currency")
            price_type = price_data.get("price_type", "standard")
            customer_category = price_data.get("customer_category")

            query = ProductPrice.objects.filter(
                product=product,
                currency=currency,
                price_type=price_type,
            )
            query = (
                query.filter(customer_category=customer_category)
                if customer_category
                else query.filter(customer_category__isnull=True)
            )

            if query.exists():
                raise serializers.ValidationError({
                    "prices": (
                        f"يوجد سعر بالفعل بنفس العملة ونوع السعر"
                        f"{' وتصنيف العميل' if customer_category else ''}"
                    )
                })

            ProductPrice.objects.create(product=product, **price_data)
    
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
