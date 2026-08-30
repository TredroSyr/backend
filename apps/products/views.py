"""Views for product management."""

from __future__ import annotations

from django.db import transaction
from django.db.models import (
    Count,
    DecimalField,
    IntegerField,
    OuterRef,
    Prefetch,
    Q,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.parsers import JSONParser

from .parsers import NestedJSONMultiPartParser

from apps.common.models import Currency
from apps.companies.mixins import TenantScopedViewMixin
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
from apps.products.serializers import (
    CustomFieldDefinitionSerializer,
    ProductCategorySerializer,
    ProductDetailSerializer,
    ProductImageSerializer,
    ProductListSerializer,
    ProductPriceSerializer,
    ProductWarehouseStockSerializer,
    ProductWriteSerializer,
    WarehouseSerializer,
)
from apps.products.services.images import primary_image_prefetch
from apps.products.services.pricing import PriceNotFoundError, resolve_product_price
from core.responses import error_response, success_response


STOCK_DECIMAL = DecimalField(max_digits=14, decimal_places=3)


def with_product_display_annotations(queryset):
    """Annotate the totals `ProductListSerializer` shows for every row.

    Subqueries rather than `annotate(Sum(...), Count(...))`: those would join
    three reverse relations into one query, and each join multiplies the others'
    rows, so every aggregate comes back inflated.
    """

    def total_of(model, field, output_field):
        return Coalesce(
            Subquery(
                model.objects.filter(product=OuterRef("pk"))
                .values("product")
                .annotate(total=field)
                .values("total")[:1],
                output_field=output_field,
            ),
            Value(0, output_field=output_field),
            output_field=output_field,
        )

    return queryset.annotate(
        total_stock_sum=total_of(
            ProductWarehouseStock, Sum("quantity"), STOCK_DECIMAL
        ),
        images_count_total=total_of(ProductImage, Count("id"), IntegerField()),
        prices_count_total=total_of(ProductPrice, Count("id"), IntegerField()),
    )


class ProductCategoryViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing product categories.
    
    Categories are company-scoped and support parent/child relationships.
    
    Endpoints:
    - GET /api/companies/product-categories/ - List all categories
    - POST /api/companies/product-categories/ - Create category
    - GET /api/companies/product-categories/{id}/ - Get category details
    - PATCH /api/companies/product-categories/{id}/ - Update category
    - DELETE /api/companies/product-categories/{id}/ - Soft delete category
    
    Query params:
    - is_active: Filter by active status (true/false)
    - parent_id: Filter by parent category
    - search: Search by name
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = ProductCategorySerializer
    queryset = ProductCategory.objects.all()
    
    def get_queryset(self):
        """Get company-scoped categories with optional filters."""
        queryset = super().get_queryset()
        
        # Filter by active status
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        # Filter by parent
        parent_id = self.request.query_params.get("parent_id")
        if parent_id:
            queryset = queryset.filter(parent_id=parent_id)
        elif parent_id == "":  # Empty string means root categories only
            queryset = queryset.filter(parent__isnull=True)
        
        # Search by name
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(name__icontains=search)
        
        return queryset.select_related("parent").order_by("name")
    
    def get_serializer_context(self):
        """Add company_id to serializer context."""
        context = super().get_serializer_context()
        context["company_id"] = self.get_company_id()
        return context
    
    def list(self, request, *args, **kwargs):
        """List all categories."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"categories": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create a new category."""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        company_id = self.get_company_id()
        category = serializer.save(company_id=company_id)
        
        return success_response(
            data={"category": ProductCategorySerializer(category).data},
            message="تم إنشاء التصنيف بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get category details."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"category": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Update category."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        category = serializer.save()
        
        return success_response(
            data={"category": ProductCategorySerializer(category).data},
            message="تم تحديث التصنيف بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update category."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete category."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        
        return success_response(
            message="تم حذف التصنيف بنجاح",
            status_code=status.HTTP_200_OK,
        )


class ProductViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing products.
    
    Products are company-scoped with full CRUD operations.
    List returns lightweight data; retrieve returns full details with nested relations.
    
    Endpoints:
    - GET /api/companies/products/ - List products
    - POST /api/companies/products/ - Create product
    - GET /api/companies/products/{id}/ - Get product details
    - PATCH /api/companies/products/{id}/ - Update product
    - DELETE /api/companies/products/{id}/ - Soft delete product
    - GET /api/companies/products/{id}/resolved-price/ - Resolve price
    
    Query params for list:
    - category: Filter by category ID
    - is_active: Filter by active status
    - is_sellable: Filter by sellable status
    - is_purchasable: Filter by purchasable status
    - brand: Filter by brand (exact match)
    - search: Search by name, SKU, or barcode
    - ordering: Sort by field (name, created_at, sku, -name, etc.)
    """
    
    permission_classes = [IsAuthenticated]
    parser_classes = [NestedJSONMultiPartParser, JSONParser]
    queryset = Product.objects.all()
    
    def get_serializer_class(self):
        """Use different serializers for list vs detail."""
        if self.action == "list":
            return ProductListSerializer
        elif self.action in ["create", "update", "partial_update"]:
            return ProductWriteSerializer
        return ProductDetailSerializer
    
    def get_queryset(self):
        """Get company-scoped products with optimizations and filters."""
        queryset = super().get_queryset()
        
        # Apply filters
        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)
        
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        is_sellable = self.request.query_params.get("is_sellable")
        if is_sellable is not None:
            queryset = queryset.filter(is_sellable=is_sellable.lower() == "true")
        
        is_purchasable = self.request.query_params.get("is_purchasable")
        if is_purchasable is not None:
            queryset = queryset.filter(is_purchasable=is_purchasable.lower() == "true")
        
        brand = self.request.query_params.get("brand")
        if brand:
            queryset = queryset.filter(brand__iexact=brand)
        
        # Search
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(sku__icontains=search)
                | Q(barcode__icontains=search)
            )
        
        # Ordering
        ordering = self.request.query_params.get("ordering", "-created_at")
        valid_orderings = ["name", "-name", "created_at", "-created_at", "sku", "-sku"]
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)
        
        # Optimize queries based on action
        if self.action == "list":
            queryset = with_product_display_annotations(
                queryset.select_related("category", "unit")
            ).prefetch_related(
                primary_image_prefetch(),
                Prefetch(
                    "prices",
                    queryset=ProductPrice.objects.select_related(
                        "currency", "customer_category"
                    ),
                ),
            )
        elif self.action == "retrieve":
            # No annotations here: the prefetches below already carry every
            # count and total the detail serializer needs.
            queryset = queryset.select_related(
                "category", "category__parent", "unit"
            ).prefetch_related(
                "images",
                Prefetch(
                    "prices",
                    queryset=ProductPrice.objects.select_related(
                        "currency", "customer_category"
                    ),
                ),
                Prefetch(
                    "custom_field_values",
                    queryset=CustomFieldValue.objects.select_related("definition"),
                ),
                Prefetch(
                    "warehouse_stocks",
                    queryset=ProductWarehouseStock.objects.select_related(
                        "warehouse", "warehouse__rep"
                    ).order_by("warehouse__name"),
                ),
            )
        
        return queryset
    
    def get_serializer_context(self):
        """Add company_id to serializer context."""
        context = super().get_serializer_context()
        context["company_id"] = self.get_company_id()
        return context
    
    def list(self, request, *args, **kwargs):
        """List products with lightweight serialization."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"products": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create a new product."""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        product = serializer.save()
        
        # Return with detail serializer. The context carries `request`, without
        # which image URLs would come back relative here but absolute on GET.
        detail_serializer = ProductDetailSerializer(
            product, context=self.get_serializer_context()
        )
        
        return success_response(
            data={"product": detail_serializer.data},
            message="تم إنشاء المنتج بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get product details with full nested data."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"product": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Update product."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        product = serializer.save()
        
        # Return with detail serializer. The context carries `request`, without
        # which image URLs would come back relative here but absolute on GET.
        detail_serializer = ProductDetailSerializer(
            product, context=self.get_serializer_context()
        )
        
        return success_response(
            data={"product": detail_serializer.data},
            message="تم تحديث المنتج بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update product."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete product."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        
        return success_response(
            message="تم حذف المنتج بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    @action(detail=True, methods=["get"], url_path="resolved-price")
    def resolved_price(self, request, pk=None):
        """
        Resolve price for a product given currency and optional customer category.
        
        GET /api/companies/products/{id}/resolved-price/?currency={id}&customer_category={id}&price_type=standard
        
        Query params:
        - currency: Currency ID (required)
        - customer_category: Customer category ID (optional)
        - price_type: Price type (default: standard)
        
        Returns the resolved price with fallback logic:
        1. Customer-category specific price if provided
        2. General price for the currency/price_type
        3. 404 if neither exists
        """
        product = self.get_object()
        
        # Validate required params
        currency_id = request.query_params.get("currency")
        if not currency_id:
            return error_response(
                message="معرف العملة مطلوب",
                errors={"currency": ["يجب تقديم معرف العملة"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Validate currency exists
        try:
            currency = Currency.objects.get(id=currency_id, is_active=True)
        except Currency.DoesNotExist:
            return error_response(
                message="العملة غير موجودة",
                errors={"currency": ["العملة غير موجودة أو غير نشطة"]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        # Optional params
        customer_category_id = request.query_params.get("customer_category")
        price_type = request.query_params.get("price_type", "standard")
        
        # Resolve price using service
        try:
            price_info = resolve_product_price(
                product=product,
                currency=currency,
                customer_category=int(customer_category_id) if customer_category_id else None,
                price_type=price_type,
            )
        except PriceNotFoundError as e:
            return error_response(
                message="السعر غير موجود",
                errors={"price": [str(e)]},
                status_code=status.HTTP_404_NOT_FOUND,
            )
        except ValueError:
            return error_response(
                message="معرف تصنيف العميل غير صالح",
                errors={"customer_category": ["معرف تصنيف العميل يجب أن يكون رقماً"]},
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Format response
        return success_response(
            data={
                "price": str(price_info["price"]),
                "currency": {
                    "id": price_info["currency"].id,
                    "code": price_info["currency"].code,
                    "symbol": price_info["currency"].symbol,
                },
                "price_type": price_info["price_type"],
                "is_default": price_info["is_default"],
                "is_category_specific": price_info["is_category_specific"],
                "customer_category": (
                    {
                        "id": price_info["customer_category"].id,
                        "name": price_info["customer_category"].name,
                    }
                    if price_info["customer_category"]
                    else None
                ),
                "valid_from": price_info["valid_from"],
                "valid_until": price_info["valid_until"],
            },
            status_code=status.HTTP_200_OK,
        )


class ProductImageViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    Nested viewset for product images.
    
    Images are managed under a specific product.
    Setting is_primary=True automatically unsets other primary images.
    
    Endpoints:
    - GET /api/companies/products/{product_id}/images/ - List images
    - POST /api/companies/products/{product_id}/images/ - Upload image
    - GET /api/companies/products/{product_id}/images/{id}/ - Get image
    - PATCH /api/companies/products/{product_id}/images/{id}/ - Update image
    - DELETE /api/companies/products/{product_id}/images/{id}/ - Delete image
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = ProductImageSerializer
    queryset = ProductImage.objects.all()
    
    def get_queryset(self):
        """Filter images by product."""
        product_id = self.kwargs.get("product_pk")
        return self.queryset.filter(product_id=product_id).order_by("sort_order", "id")
    
    def get_product(self):
        """Get the parent product and ensure company access."""
        product_id = self.kwargs.get("product_pk")
        company_id = self.get_company_id()
        
        try:
            product = Product.objects.get(id=product_id, company_id=company_id)
            return product
        except Product.DoesNotExist:
            return None
    
    def get_serializer_context(self):
        """Add product to context."""
        context = super().get_serializer_context()
        context["product"] = self.get_product()
        return context
    
    def list(self, request, *args, **kwargs):
        """List product images."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"images": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    @transaction.atomic
    def create(self, request, *args, **kwargs):
        """Create product image."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Check if this is the first image - make it primary by default
        is_first_image = not ProductImage.objects.filter(product=product).exists()
        is_primary = serializer.validated_data.get("is_primary", False) or is_first_image
        
        # If setting as primary, unset other primary images
        if is_primary:
            ProductImage.objects.filter(product=product, is_primary=True).update(
                is_primary=False
            )
        
        image = serializer.save(product=product, is_primary=is_primary)
        
        return success_response(
            data={
                "image": ProductImageSerializer(
                    image, context=self.get_serializer_context()
                ).data
            },
            message="تم رفع الصورة بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get image details."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"image": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    @transaction.atomic
    def update(self, request, *args, **kwargs):
        """Update image."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # If setting as primary, unset other primary images
        if serializer.validated_data.get("is_primary"):
            ProductImage.objects.filter(product=product, is_primary=True).exclude(
                id=instance.id
            ).update(is_primary=False)
        
        image = serializer.save()
        
        return success_response(
            data={
                "image": ProductImageSerializer(
                    image, context=self.get_serializer_context()
                ).data
            },
            message="تم تحديث الصورة بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update image."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete image."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        instance = self.get_object()
        instance.delete()
        
        return success_response(
            message="تم حذف الصورة بنجاح",
            status_code=status.HTTP_200_OK,
        )


class ProductPriceViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    Nested viewset for product prices.
    
    Prices are managed under a specific product.
    Validates uniqueness constraints for general vs customer-category prices.
    
    Endpoints:
    - GET /api/companies/products/{product_id}/prices/ - List prices
    - POST /api/companies/products/{product_id}/prices/ - Create price
    - GET /api/companies/products/{product_id}/prices/{id}/ - Get price
    - PATCH /api/companies/products/{product_id}/prices/{id}/ - Update price
    - DELETE /api/companies/products/{product_id}/prices/{id}/ - Delete price
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = ProductPriceSerializer
    queryset = ProductPrice.objects.all()
    
    def get_queryset(self):
        """Filter prices by product."""
        product_id = self.kwargs.get("product_pk")
        return self.queryset.filter(product_id=product_id).select_related(
            "currency", "customer_category"
        )
    
    def get_product(self):
        """Get the parent product and ensure company access."""
        product_id = self.kwargs.get("product_pk")
        company_id = self.get_company_id()
        
        try:
            product = Product.objects.get(id=product_id, company_id=company_id)
            return product
        except Product.DoesNotExist:
            return None
    
    def get_serializer_context(self):
        """Add product and company_id to context."""
        context = super().get_serializer_context()
        context["product"] = self.get_product()
        context["company_id"] = self.get_company_id()
        return context
    
    def list(self, request, *args, **kwargs):
        """List product prices."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"prices": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create product price."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        price = serializer.save(product=product)
        
        return success_response(
            data={"price": ProductPriceSerializer(price).data},
            message="تم إنشاء السعر بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get price details."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"price": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Update price."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        price = serializer.save()
        
        return success_response(
            data={"price": ProductPriceSerializer(price).data},
            message="تم تحديث السعر بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update price."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Delete price."""
        product = self.get_product()
        if not product:
            return error_response(
                message="المنتج غير موجود",
                status_code=status.HTTP_404_NOT_FOUND,
            )
        
        instance = self.get_object()
        instance.delete()
        
        return success_response(
            message="تم حذف السعر بنجاح",
            status_code=status.HTTP_200_OK,
        )


class ProductWarehouseStockViewSet(TenantScopedViewMixin, viewsets.ReadOnlyModelViewSet):
    """
    Read-only viewset for product warehouse stock.
    
    Stock quantity is a projection from StockMovement - no write operations.
    Can be viewed by product or by warehouse.
    
    Endpoints:
    - GET /api/companies/products/{product_id}/warehouse-stock/ - List stock for product
    - GET /api/companies/warehouses/{warehouse_id}/product-stock/ - List stock for warehouse
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = ProductWarehouseStockSerializer
    queryset = ProductWarehouseStock.objects.all()
    
    def get_queryset(self):
        """Filter by product or warehouse based on URL."""
        queryset = super().get_queryset()
        
        # Check if nested under product
        product_id = self.kwargs.get("product_pk")
        if product_id:
            queryset = queryset.filter(product_id=product_id)
        
        # Check if nested under warehouse
        warehouse_id = self.kwargs.get("warehouse_pk")
        if warehouse_id:
            queryset = queryset.filter(warehouse_id=warehouse_id)

        return queryset.select_related(
            "product", "product__unit", "warehouse", "warehouse__rep"
        )
    
    def list(self, request, *args, **kwargs):
        """List warehouse stock."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"stock": serializer.data},
            status_code=status.HTTP_200_OK,
        )


class CustomFieldDefinitionViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing custom field definitions.
    
    Custom fields allow companies to define additional product attributes.
    
    Endpoints:
    - GET /api/companies/custom-field-definitions/ - List definitions
    - POST /api/companies/custom-field-definitions/ - Create definition
    - GET /api/companies/custom-field-definitions/{id}/ - Get definition
    - PATCH /api/companies/custom-field-definitions/{id}/ - Update definition
    - DELETE /api/companies/custom-field-definitions/{id}/ - Soft delete definition
    
    Query params:
    - is_active: Filter by active status
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = CustomFieldDefinitionSerializer
    queryset = CustomFieldDefinition.objects.all()
    
    def get_queryset(self):
        """Get company-scoped definitions with filters."""
        queryset = super().get_queryset()
        
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        return queryset.order_by("label")
    
    def get_serializer_context(self):
        """Add company_id to context."""
        context = super().get_serializer_context()
        context["company_id"] = self.get_company_id()
        return context
    
    def list(self, request, *args, **kwargs):
        """List custom field definitions."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"definitions": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create custom field definition."""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        company_id = self.get_company_id()
        definition = serializer.save(company_id=company_id)
        
        return success_response(
            data={"definition": CustomFieldDefinitionSerializer(definition).data},
            message="تم إنشاء الحقل المخصص بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get definition details."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"definition": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Update definition."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        definition = serializer.save()
        
        return success_response(
            data={"definition": CustomFieldDefinitionSerializer(definition).data},
            message="تم تحديث الحقل المخصص بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update definition."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete definition."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        
        return success_response(
            message="تم حذف الحقل المخصص بنجاح",
            status_code=status.HTTP_200_OK,
        )


class WarehouseViewSet(TenantScopedViewMixin, viewsets.ModelViewSet):
    """
    ViewSet for managing warehouses.
    
    Warehouses are company-scoped and can be owned by company or reps.
    
    Endpoints:
    - GET /api/companies/warehouses/ - List warehouses
    - POST /api/companies/warehouses/ - Create warehouse
    - GET /api/companies/warehouses/{id}/ - Get warehouse details
    - PATCH /api/companies/warehouses/{id}/ - Update warehouse
    - DELETE /api/companies/warehouses/{id}/ - Soft delete warehouse
    
    Query params:
    - is_active: Filter by active status
    - owner_type: Filter by owner type (company/rep)
    """
    
    permission_classes = [IsAuthenticated]
    serializer_class = WarehouseSerializer
    queryset = Warehouse.objects.all()
    
    def get_queryset(self):
        """Get company-scoped warehouses with filters."""
        queryset = super().get_queryset()
        
        is_active = self.request.query_params.get("is_active")
        if is_active is not None:
            queryset = queryset.filter(is_active=is_active.lower() == "true")
        
        owner_type = self.request.query_params.get("owner_type")
        if owner_type:
            queryset = queryset.filter(owner_type=owner_type)
        
        return queryset.select_related("rep").order_by("name")
    
    def get_serializer_context(self):
        """Add company_id to context."""
        context = super().get_serializer_context()
        context["company_id"] = self.get_company_id()
        return context
    
    def list(self, request, *args, **kwargs):
        """List warehouses."""
        queryset = self.filter_queryset(self.get_queryset())
        serializer = self.get_serializer(queryset, many=True)
        
        return success_response(
            data={"warehouses": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def create(self, request, *args, **kwargs):
        """Create warehouse."""
        serializer = self.get_serializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        company_id = self.get_company_id()
        warehouse = serializer.save(company_id=company_id)
        
        return success_response(
            data={"warehouse": WarehouseSerializer(warehouse).data},
            message="تم إنشاء المستودع بنجاح",
            status_code=status.HTTP_201_CREATED,
        )
    
    def retrieve(self, request, *args, **kwargs):
        """Get warehouse details."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        
        return success_response(
            data={"warehouse": serializer.data},
            status_code=status.HTTP_200_OK,
        )
    
    def update(self, request, *args, **kwargs):
        """Update warehouse."""
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات غير صالحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        warehouse = serializer.save()
        
        return success_response(
            data={"warehouse": WarehouseSerializer(warehouse).data},
            message="تم تحديث المستودع بنجاح",
            status_code=status.HTTP_200_OK,
        )
    
    def partial_update(self, request, *args, **kwargs):
        """Partial update warehouse."""
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)
    
    def destroy(self, request, *args, **kwargs):
        """Soft delete warehouse."""
        instance = self.get_object()
        instance.is_active = False
        instance.save(update_fields=["is_active", "updated_at"])
        
        return success_response(
            message="تم حذف المستودع بنجاح",
            status_code=status.HTTP_200_OK,
        )
