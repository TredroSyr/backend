"""URL patterns for customer management by companies."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.customers.views import CustomerViewSet, CustomerCategoryViewSet

# Create router for viewsets
router = DefaultRouter()
router.register(r"companies/customers", CustomerViewSet, basename="customer")
router.register(r"companies/customer-categories", CustomerCategoryViewSet, basename="customer-category")

urlpatterns = [
    # Include router URLs for viewsets
    path("", include(router.urls)),
]
