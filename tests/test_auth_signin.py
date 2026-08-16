"""Tests for company signin endpoint."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.billing.models import Plan
from apps.billing.services import create_trial_subscription
from apps.authentication.utils import hash_password
from apps.companies.models import Company, ModulePermission, Role, SubUser


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
def owner_subuser(company, db):
    """Create an owner SubUser."""
    return SubUser.objects.create(
        company=company,
        name="Owner User",
        phone="+963944123456",
        password=hash_password("OwnerPass123"),
        is_owner=True,
        is_active=True,
    )


@pytest.fixture
def staff_role(company, db):
    """Create a staff role with limited permissions."""
    role = Role.objects.create(
        company=company,
        name="Sales Staff",
    )
    
    # Add some permissions
    ModulePermission.objects.create(
        company=company,
        role=role,
        module="products",
        can_view=True,
        can_action=False,
    )
    ModulePermission.objects.create(
        company=company,
        role=role,
        module="orders",
        can_view=True,
        can_action=True,
    )
    
    return role


@pytest.fixture
def staff_subuser(company, staff_role, db):
    """Create a staff SubUser with role."""
    return SubUser.objects.create(
        company=company,
        role=staff_role,
        name="Staff User",
        phone="+963955123456",
        password=hash_password("StaffPass123"),
        is_owner=False,
        is_active=True,
    )


class TestCompanySignin:
    """Tests for company signin endpoint."""
    
    def test_signin_success_owner(self, api_client, owner_subuser):
        """Test successful signin for company owner."""
        data = {
            "phone": "+963944123456",
            "password": "OwnerPass123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        assert response.data["success"] is True
        assert "تم تسجيل الدخول بنجاح" in response.data["message"]
        
        # Check response structure
        assert "user" in response.data["data"]
        assert "tokens" in response.data["data"]
        
        # Check user data
        user_data = response.data["data"]["user"]
        assert user_data["phone"] == "+963944123456"
        assert user_data["is_owner"] is True
        assert user_data["is_active"] is True
        
        # Check that permissions are included
        assert "permissions" in user_data
        permissions = user_data["permissions"]
        
        # Owners should have full access to all modules
        assert permissions["products"]["can_view"] is True
        assert permissions["products"]["can_action"] is True
        assert permissions["orders"]["can_view"] is True
        assert permissions["orders"]["can_action"] is True
        
        # Check tokens
        tokens = response.data["data"]["tokens"]
        assert "access" in tokens
        assert "refresh" in tokens
        assert len(tokens["access"]) > 0
        assert len(tokens["refresh"]) > 0
    
    def test_signin_success_staff(self, api_client, staff_subuser):
        """Test successful signin for staff member."""
        data = {
            "phone": "+963955123456",
            "password": "StaffPass123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        
        user_data = response.data["data"]["user"]
        assert user_data["is_owner"] is False
        
        # Check permissions from role
        permissions = user_data["permissions"]
        assert permissions["products"]["can_view"] is True
        assert permissions["products"]["can_action"] is False
        assert permissions["orders"]["can_view"] is True
        assert permissions["orders"]["can_action"] is True
    
    def test_signin_wrong_password(self, api_client, owner_subuser):
        """Test signin fails with wrong password."""
        data = {
            "phone": "+963944123456",
            "password": "WrongPassword123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert response.data["success"] is False
        assert "غير صحيحة" in response.data["message"]
    
    def test_signin_nonexistent_phone(self, api_client):
        """Test signin fails with nonexistent phone number."""
        data = {
            "phone": "+963999999999",
            "password": "AnyPass123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
        assert "غير صحيحة" in response.data["message"]
    
    def test_signin_inactive_user(self, api_client, owner_subuser, db):
        """Test signin fails for inactive user."""
        owner_subuser.is_active = False
        owner_subuser.save()
        
        data = {
            "phone": "+963944123456",
            "password": "OwnerPass123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "غير نشط" in response.data["message"]
    
    def test_signin_inactive_company(self, api_client, owner_subuser, db):
        """Test signin fails when company is inactive."""
        owner_subuser.company.is_active = False
        owner_subuser.company.save()
        
        data = {
            "phone": "+963944123456",
            "password": "OwnerPass123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_403_FORBIDDEN
        assert "غير نشط" in response.data["message"]
    
    def test_signin_phone_normalization(self, api_client, owner_subuser):
        """Test that phone numbers are normalized during signin."""
        test_phones = [
            "+963944123456",
            "963944123456",
            "00963944123456",
            "0944123456",
            "+963 944 123 456",
        ]
        
        for phone in test_phones:
            data = {
                "phone": phone,
                "password": "OwnerPass123",
            }
            
            response = api_client.post("/api/auth/company/signin", data, format="json")
            assert response.status_code == status.HTTP_200_OK
    
    def test_signin_missing_fields(self, api_client):
        """Test that signin fails with missing fields."""
        # Missing password
        response1 = api_client.post(
            "/api/auth/company/signin",
            {"phone": "+963944123456"},
            format="json"
        )
        assert response1.status_code == status.HTTP_400_BAD_REQUEST
        
        # Missing phone
        response2 = api_client.post(
            "/api/auth/company/signin",
            {"password": "SomePass123"},
            format="json"
        )
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
    
    def test_signin_includes_company_data(self, api_client, owner_subuser):
        """Test that signin response includes company data."""
        data = {
            "phone": "+963944123456",
            "password": "OwnerPass123",
        }
        
        response = api_client.post("/api/auth/company/signin", data, format="json")
        
        assert response.status_code == status.HTTP_200_OK
        
        user_data = response.data["data"]["user"]
        assert "company" in user_data
        
        company_data = user_data["company"]
        assert company_data["name"] == "Test Company"
        assert company_data["slug"] == "test-company"
        assert company_data["currency"] == "SYP"
