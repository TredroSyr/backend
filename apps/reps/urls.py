"""URL patterns for reps app."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.reps.views import (
    RepCustomerViewSet,
    RepDashboardView,
    RepInventoryViewSet,
    RepProfileViewSet,
)

# Create a router for viewsets
router = DefaultRouter()
router.register(r"reps/customers", RepCustomerViewSet, basename="rep-customer")
router.register(r"reps/profile", RepProfileViewSet, basename="rep-profile")
router.register(r"reps/inventory", RepInventoryViewSet, basename="rep-inventory")

urlpatterns = [
    # Home screen — one read that fills every card on it.
    path("reps/dashboard/", RepDashboardView.as_view(), name="rep-dashboard"),
    # Include router URLs for viewsets
    path("", include(router.urls)),
]
