"""Tests for rep signin endpoint."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.authentication.utils import hash_password
from apps.companies.models import Company
from apps.reps.models import Rep


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
def active_rep(company, db):
    """Create an active rep."""
    return Rep.objects.create(
        company=company,
        name="خالد العلي",
        phone="+963955123456",
        password=hash_password("RepPass123"),
        referral_code="KH-2024-001",
        is_active=True,
    )


@pytest.fixture
def inactive_rep(company, db):
    """Create an inactive rep."""
    return Rep.objects.create(
        company=company,
        name="محمد أحمد",
        phone="+963966123456",
        password=hash_password("InactivePass123"),
        referral_code="MA-2024-001",
        is_active=False,
    )


class TestRepSignin:
    """Tests for rep signin endpoint."""
    
    def test_rep_signin_success(self, api_client, active_rep):
        """Test successful rep signin."""
        data = {
            "phone": "+963955123456",
            "password": "RepPass123",
        }
        
        response = api_client.post("/api/auth/rep/signin", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "تم تسجيل الدخول بنجاح" in response.data["message"]
        
        # Check response structure
        assert "rep" in response.data["data"]
        assert "tokens" in response.data["data"]
        
        # Check rep data
        rep_data = response.data["data"]["rep"]
        assert rep_data["name"] == "خالد العلي"
        assert rep_data["phone"] == "+963955123456"
        assert rep_data["referral_code"] == "KH-2024-001"
        assert rep_data["is_active"] is True
        
        # Check company data is included
        assert "company" in rep_data
        company_data = rep_data["company"]
        assert company_data["name"] == "Test Company"
        assert company_data["slug"] == "test-company"
        
        # Check tokens
        tokens = response.data["data"]["tokens"]
        assert "access" in tokens
        assert "refresh" in tokens
    
    def test_rep_signin_wrong_password(self, api_client, active_rep):
        """Test rep signin fails with wrong password."""
        data = {
            "phone": "+963955123456",
            "password": "WrongPassword123",
        }
        
        response = api_client.post("/api/auth/rep/signin", data, format="json")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["success"] is False
        assert "غير صحيحة" in response.data["message"]
    
    def test_rep_signin_nonexistent_phone(self, api_client):
        """Test rep signin fails with nonexistent phone."""
        data = {
            "phone": "+963999999999",
            "password": "AnyPass123",
        }
        
        response = api_client.post("/api/auth/rep/signin", data, format="json")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "غير صحيحة" in response.data["message"]
    
    def test_rep_signin_inactive_rep(self, api_client, inactive_rep):
        """Test rep signin fails for inactive rep."""
        data = {
            "phone": "+963966123456",
            "password": "InactivePass123",
        }
        
        response = api_client.post("/api/auth/rep/signin", data, format="json")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "غير نشط" in response.data["message"]
    
    def test_rep_signin_inactive_company(self, api_client, active_rep, db):
        """Test rep signin fails when company is inactive."""
        active_rep.company.is_active = False
        active_rep.company.save()
        
        data = {
            "phone": "+963955123456",
            "password": "RepPass123",
        }
        
        response = api_client.post("/api/auth/rep/signin", data, format="json")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "غير نشط" in response.data["message"]
    
    def test_rep_signin_phone_normalization(self, api_client, active_rep):
        """Test that phone numbers are normalized during rep signin."""
        test_phones = [
            "+963955123456",
            "963955123456",
            "00963955123456",
            "0955123456",
            "+963 955 123 456",
        ]
        
        for phone in test_phones:
            data = {
                "phone": phone,
                "password": "RepPass123",
            }
            
            response = api_client.post("/api/auth/rep/signin", data, format="json")
            assert response.status_code == status.HTTP_200_OK
    
    def test_rep_signin_missing_fields(self, api_client):
        """Test that rep signin fails with missing fields."""
        # Missing password
        response1 = api_client.post(
            "/api/auth/rep/signin",
            {"phone": "+963955123456"},
            format="json"
        )
        assert response1.status_code == status.HTTP_400_BAD_REQUEST
        
        # Missing phone
        response2 = api_client.post(
            "/api/auth/rep/signin",
            {"password": "SomePass123"},
            format="json"
        )
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
