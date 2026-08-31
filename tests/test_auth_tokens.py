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


