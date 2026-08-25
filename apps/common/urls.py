"""URL patterns for common app."""

from __future__ import annotations

from django.urls import path

from apps.common.views import ApkVersionView, BusinessTypesView, LocationsView, ModulesView

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
]
