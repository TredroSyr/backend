"""URL configuration for authentication endpoints."""

from __future__ import annotations

from django.urls import path

from apps.authentication.views import (
    CompanySigninView,
    CompanySignupView,
    RepSigninView,
    SignoutView,
    TokenRefreshView,
)

app_name = "authentication"

urlpatterns = [
    # Authentication endpoints
    path("auth/company/signup", CompanySignupView.as_view(), name="company-signup"),
    path("auth/company/signin", CompanySigninView.as_view(), name="company-signin"),
    path("auth/rep/signin", RepSigninView.as_view(), name="rep-signin"),
    path("auth/token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/signout", SignoutView.as_view(), name="signout"),
]
