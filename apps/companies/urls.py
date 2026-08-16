"""URL patterns for companies app."""

from __future__ import annotations

from django.urls import path

from apps.companies.views import (
    CompanyBusinessTypesView,
    CompanyLocationsView,
    CompanyOnboardingStatusView,
    CompanyOnboardingView,
)

urlpatterns = [
    # Onboarding
    path(
        "companies/onboarding",
        CompanyOnboardingView.as_view(),
        name="company-onboarding",
    ),
    path(
        "companies/onboarding/status",
        CompanyOnboardingStatusView.as_view(),
        name="company-onboarding-status",
    ),
    # Reference data
    path(
        "companies/locations",
        CompanyLocationsView.as_view(),
        name="company-locations",
    ),
    path(
        "companies/business-types",
        CompanyBusinessTypesView.as_view(),
        name="company-business-types",
    ),
]
