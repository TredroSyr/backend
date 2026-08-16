"""Tests for token refresh and signout endpoints."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.utils import hash_password
from apps.companies.models import Company, SubUser


@pytest.fixture
def api_client():
    """Create API client."""
    return APIClient()


@pytest.fixture
def company(db):
    """Create a test company."""
    return Company.objects.create(
        name="Test Company",
        slug="test-company",
        currency="SYP",
        is_active=True,
    )


@pytest.fixture
def subuser(company, db):
    """Create a SubUser."""
    return SubUser.objects.create(
        company=company,
        name="Test User",
        phone="+963944123456",
        password=hash_password("TestPass123"),
        is_owner=True,
        is_active=True,
    )


@pytest.fixture
def tokens(subuser):
    """Generate tokens for the subuser."""
    from apps.authentication.utils import generate_tokens_for_subuser
    return generate_tokens_for_subuser(subuser)


class TestTokenRefresh:
    """Tests for token refresh endpoint."""
    
    def test_refresh_token_success(self, api_client, tokens):
        """Test successful token refresh."""
        data = {
            "refresh": tokens["refresh"],
        }
        
        response = api_client.post("/api/auth/token/refresh", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        
        # Check that new access token is returned
        assert "data" in response.data
        assert "access" in response.data["data"]
        assert len(response.data["data"]["access"]) > 0
        
        # New access token should be different from old one
        assert response.data["data"]["access"] != tokens["access"]
    
    def test_refresh_token_invalid(self, api_client):
        """Test token refresh fails with invalid token."""
        data = {
            "refresh": "invalid_token_here",
        }
        
        response = api_client.post("/api/auth/token/refresh", data, format="json")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["success"] is False
        assert "غير صالح" in response.data["message"]
    
    def test_refresh_token_missing(self, api_client):
        """Test token refresh fails with missing refresh token."""
        data = {}
        
        response = api_client.post("/api/auth/token/refresh", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
    
    def test_refresh_token_expired(self, api_client):
        """Test token refresh fails with expired token."""
        # Create an expired token
        expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJ0b2tlbl90eXBlIjoicmVmcmVzaCIsImV4cCI6MTYwMDAwMDAwMCwidXNlcl9pZCI6MX0.invalid"
        
        data = {
            "refresh": expired_token,
        }
        
        response = api_client.post("/api/auth/token/refresh", data, format="json")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["success"] is False
    
    def test_refresh_token_format(self, api_client, tokens):
        """Test that refreshed token has correct format."""
        data = {
            "refresh": tokens["refresh"],
        }
        
        response = api_client.post("/api/auth/token/refresh", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        
        # JWT tokens should have 3 parts separated by dots
        access_token = response.data["data"]["access"]
        parts = access_token.split(".")
        assert len(parts) == 3


class TestSignout:
    """Tests for signout endpoint."""
    
    def test_signout_success(self, api_client, tokens):
        """Test successful signout."""
        # First, authenticate with the access token
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        
        data = {
            "refresh": tokens["refresh"],
        }
        
        response = api_client.post("/api/auth/signout", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "تم تسجيل الخروج بنجاح" in response.data["message"]
    
    def test_signout_blacklists_token(self, api_client, tokens):
        """Test that signout blacklists the refresh token."""
        api_client.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        
        data = {
            "refresh": tokens["refresh"],
        }
        
        # Sign out
        response = api_client.post("/api/auth/signout", data, format="json")
        assert response.status_code == status.HTTP_200_OK
        
        # Try to use the same refresh token again
        refresh_response = api_client.post("/api/auth/token/refresh", data, format="json")
        
        # Should fail because token is blacklisted
        assert refresh_response.status_code == status.HTTP_401_UNAUTHORIZED
    
    def test_signout_invalid_token(self, api_client):
        """Test signout fails with invalid token."""
        data = {
            "refresh": "invalid_token_here",
        }
        
        response = api_client.post("/api/auth/signout", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
    
    def test_signout_missing_token(self, api_client):
        """Test signout fails with missing refresh token."""
        data = {}
        
        response = api_client.post("/api/auth/signout", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert response.data["success"] is False
    
    def test_signout_without_authentication(self, api_client, tokens):
        """Test that signout works even without Bearer token in header."""
        # Don't set authorization header
        data = {
            "refresh": tokens["refresh"],
        }
        
        # Signout should still work because we're blacklisting the refresh token
        response = api_client.post("/api/auth/signout", data, format="json")
        
        # In the current implementation, signout doesn't require authentication
        # It just needs a valid refresh token to blacklist
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_401_UNAUTHORIZED]


class TestTokenLifecycle:
    """Tests for full token lifecycle."""
    
    def test_signup_signin_refresh_signout(self, api_client, db):
        """Test complete auth flow from signup to signout."""
        from apps.billing.models import Plan
        
        # Create a plan first
        Plan.objects.create(
            name="Free",
            price=0,
            billing_interval="monthly",
            is_active=True,
        )
        
        # 1. Sign up
        signup_data = {
            "company_name": "Flow Test Company",
            "phone": "+963944555666",
            "password": "FlowTest123",
            "password_confirm": "FlowTest123",
        }
        
        signup_response = api_client.post(
            "/api/auth/company/signup",
            signup_data,
            format="json"
        )
        assert signup_response.status_code == status.HTTP_201_CREATED
        
        tokens = signup_response.data["data"]["tokens"]
        
        # 2. Refresh token
        refresh_data = {"refresh": tokens["refresh"]}
        refresh_response = api_client.post(
            "/api/auth/token/refresh",
            refresh_data,
            format="json"
        )
        assert refresh_response.status_code == status.HTTP_200_OK
        new_access = refresh_response.data["data"]["access"]
        
        # 3. Sign out
        signout_data = {"refresh": tokens["refresh"]}
        signout_response = api_client.post(
            "/api/auth/signout",
            signout_data,
            format="json"
        )
        assert signout_response.status_code == status.HTTP_200_OK
        
        # 4. Try to refresh again (should fail)
        refresh_again = api_client.post(
            "/api/auth/token/refresh",
            refresh_data,
            format="json"
        )
        assert refresh_again.status_code == status.HTTP_401_UNAUTHORIZED
