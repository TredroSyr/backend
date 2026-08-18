"""URL patterns for companies app."""

from __future__ import annotations

from django.urls import path

from apps.companies.views import (
    CompanyBusinessTypesView,
    CompanyLocationsView,
    CompanyOnboardingStatusView,
    CompanyOnboardingView,
    ModuleListView,
    SubUserCreateView,
    SubUserDetailView,
    SubUserListView,
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
    path(
        "companies/modules",
        ModuleListView.as_view(),
        name="company-modules",
    ),
    # Sub-users
    path(
        "companies/subusers",
        SubUserCreateView.as_view(),
        name="subuser-create",
    ),
    path(
        "companies/subusers/list",
        SubUserListView.as_view(),
        name="subuser-list",
    ),
    path(
        "companies/subusers/<int:subuser_id>",
        SubUserDetailView.as_view(),
        name="subuser-detail",
    ),
]
