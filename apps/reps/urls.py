"""URL patterns for reps app."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.reps.views import RepCustomerViewSet, RepProfileViewSet

# Create a router for viewsets
router = DefaultRouter()
router.register(r"reps/customers", RepCustomerViewSet, basename="rep-customer")
router.register(r"reps/profile", RepProfileViewSet, basename="rep-profile")

urlpatterns = [
    # Include router URLs for viewsets
    path("", include(router.urls)),
]
