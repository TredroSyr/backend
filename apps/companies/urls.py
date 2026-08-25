"""URL patterns for companies app."""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.companies.views import (
    CompanyOnboardingStatusView,
    CompanyOnboardingView,
    RepViewSet,
    SubUserCreateView,
    SubUserDetailView,
    SubUserListView,
)

# Create a router for viewsets
router = DefaultRouter()
router.register(r"companies/reps", RepViewSet, basename="rep")

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
    # Include router URLs for viewsets
    path("", include(router.urls)),
]
