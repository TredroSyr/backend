"""URL configuration for authentication endpoints."""

from __future__ import annotations

from django.urls import path

from apps.authentication.views import (
    CompanySigninView,
    CompanySignupView,
    CustomerSigninView,
    CustomerSignupView,
    RepSigninView,
    SignoutView,
    TokenRefreshView,
)

app_name = "authentication"

urlpatterns = [
    # Company authentication
    path("auth/company/signup", CompanySignupView.as_view(), name="company-signup"),
    path("auth/company/signin", CompanySigninView.as_view(), name="company-signin"),
    
    # Rep authentication
    path("auth/rep/signin", RepSigninView.as_view(), name="rep-signin"),
    
    # Customer authentication
    path("auth/customer/signup", CustomerSignupView.as_view(), name="customer-signup"),
    path("auth/customer/signin", CustomerSigninView.as_view(), name="customer-signin"),
    
    # Token management
    path("auth/token/refresh", TokenRefreshView.as_view(), name="token-refresh"),
    path("auth/signout", SignoutView.as_view(), name="signout"),
]
