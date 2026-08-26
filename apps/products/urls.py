"""URL patterns for products app."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.products.views import (
    CustomFieldDefinitionViewSet,
    ProductCategoryViewSet,
    ProductImageViewSet,
    ProductPriceViewSet,
    ProductViewSet,
    ProductWarehouseStockViewSet,
    WarehouseViewSet,
)

# Main router for top-level resources
router = DefaultRouter()
router.register(
    r"companies/product-categories",
    ProductCategoryViewSet,
    basename="product-category",
)
router.register(
    r"companies/products",
    ProductViewSet,
    basename="product",
)
router.register(
    r"companies/custom-field-definitions",
    CustomFieldDefinitionViewSet,
    basename="custom-field-definition",
)
router.register(
    r"companies/warehouses",
    WarehouseViewSet,
    basename="warehouse",
)

# Nested resources - manual URL patterns for images, prices, and stock
urlpatterns = [
    # Include main router URLs
    path("", include(router.urls)),
    
    # Product images (nested under products)
    path(
        "companies/products/<int:product_pk>/images/",
        ProductImageViewSet.as_view({"get": "list", "post": "create"}),
        name="product-image-list",
    ),
    path(
        "companies/products/<int:product_pk>/images/<int:pk>/",
        ProductImageViewSet.as_view({
            "get": "retrieve",
            "patch": "partial_update",
            "put": "update",
            "delete": "destroy",
        }),
        name="product-image-detail",
    ),
    
    # Product prices (nested under products)
    path(
        "companies/products/<int:product_pk>/prices/",
        ProductPriceViewSet.as_view({"get": "list", "post": "create"}),
        name="product-price-list",
    ),
    path(
        "companies/products/<int:product_pk>/prices/<int:pk>/",
        ProductPriceViewSet.as_view({
            "get": "retrieve",
            "patch": "partial_update",
            "put": "update",
            "delete": "destroy",
        }),
        name="product-price-detail",
    ),
    
    # Product warehouse stock (nested under products) - read-only
    path(
        "companies/products/<int:product_pk>/warehouse-stock/",
        ProductWarehouseStockViewSet.as_view({"get": "list"}),
        name="product-warehouse-stock-list",
    ),
    
    # Warehouse product stock (nested under warehouses) - read-only
    path(
        "companies/warehouses/<int:warehouse_pk>/product-stock/",
        ProductWarehouseStockViewSet.as_view({"get": "list"}),
        name="warehouse-product-stock-list",
    ),
]
