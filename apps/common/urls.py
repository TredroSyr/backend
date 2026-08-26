"""URL patterns for common app."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.common.views import (
    ApkVersionView,
    BusinessTypesView,
    CurrencyViewSet,
    LocationsView,
    ModulesView,
    UnitOfMeasureViewSet,
)

# Create router for lookup data viewsets
router = DefaultRouter()
router.register(r"units-of-measure", UnitOfMeasureViewSet, basename="unit-of-measure")
router.register(r"currencies", CurrencyViewSet, basename="currency")

urlpatterns = [
    path(
        "locations",
        LocationsView.as_view(),
        name="locations",
    ),
    path(
        "business-types",
        BusinessTypesView.as_view(),
        name="business-types",
    ),
    path(
        "modules",
        ModulesView.as_view(),
        name="modules",
    ),
    path(
        "apk-version",
        ApkVersionView.as_view(),
        name="apk-version",
    ),
    # Include router URLs for lookup data
    path("", include(router.urls)),
]
