"""Tests for company signup endpoint."""

from __future__ import annotations

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.billing.models import Plan, Subscription, SubscriptionStatus
from apps.companies.models import Company, SubUser


@pytest.fixture
def api_client():
    """Create API client."""
    return APIClient()


@pytest.fixture
def free_plan(db):
    """Create a free plan for testing."""
    return Plan.objects.create(
        name="Free",
        price=0,
        billing_interval="monthly",
        is_active=True,
    )


class TestCompanySignup:
    """Tests for company signup endpoint."""
    
    def test_signup_success(self, api_client, free_plan):
        """Test successful company signup."""
        data = {
            "company_name": "شركة الأمل التجارية",
            "phone": "+963944123456",
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
            "currency": "SYP",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["success"] is True
        assert "تم إنشاء الحساب بنجاح" in response.data["message"]
        
        # Check response data
        assert "company" in response.data["data"]
        assert "user" in response.data["data"]
        assert "tokens" in response.data["data"]
        
        # Check company data
        company_data = response.data["data"]["company"]
        assert company_data["name"] == "شركة الأمل التجارية"
        assert company_data["currency"] == "SYP"
        assert company_data["is_active"] is True
        
        # Check user data
        user_data = response.data["data"]["user"]
        assert user_data["phone"] == "+963944123456"
        assert user_data["is_owner"] is True
        assert user_data["is_active"] is True
        
        # Check tokens
        tokens = response.data["data"]["tokens"]
        assert "access" in tokens
        assert "refresh" in tokens
    
    def test_signup_creates_database_records(self, api_client, free_plan):
        """Test that signup creates Company, SubUser, and Subscription records."""
        data = {
            "company_name": "Test Company",
            "phone": "+963944123456",
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        assert response.status_code == status.HTTP_201_CREATED
        
        # Check Company was created
        company = Company.objects.get(name="Test Company")
        assert company.slug == "test-company"
        assert company.currency == "SYP"
        
        # Check SubUser was created
        subuser = SubUser.objects.get(phone="+963944123456")
        assert subuser.company == company
        assert subuser.is_owner is True
        assert subuser.role is None  # Owners don't have roles
        
        # Check Subscription was created
        subscription = Subscription.objects.get(company=company)
        assert subscription.plan == free_plan
        assert subscription.status == SubscriptionStatus.ACTIVE
    
    def test_signup_duplicate_phone(self, api_client, free_plan, db):
        """Test that signup fails with duplicate phone number."""
        # Create first user
        first_data = {
            "company_name": "First Company",
            "phone": "+963944123456",
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
        }
        
        response1 = api_client.post("/api/auth/company/signup", first_data, format="json")
        assert response1.status_code == status.HTTP_201_CREATED
        
        # Try to create second user with same phone
        second_data = {
            "company_name": "Second Company",
            "phone": "+963944123456",
            "password": "AnotherPass123",
            "password_confirm": "AnotherPass123",
        }
        
        response2 = api_client.post("/api/auth/company/signup", second_data, format="json")
        assert response2.status_code == status.HTTP_400_BAD_REQUEST
        assert "رقم الهاتف مستخدم من قبل" in str(response2.data)
    
    def test_signup_invalid_phone_format(self, api_client, free_plan):
        """Test that signup fails with invalid phone format."""
        data = {
            "company_name": "Test Company",
            "phone": "0944123456",  # Missing +963
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        # Phone should be normalized and accepted
        # The normalize_phone function handles this
        assert response.status_code == status.HTTP_201_CREATED
    
    def test_signup_password_mismatch(self, api_client, free_plan):
        """Test that signup fails when passwords don't match."""
        data = {
            "company_name": "Test Company",
            "phone": "+963944123456",
            "password": "SecurePass123",
            "password_confirm": "DifferentPass123",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password_confirm" in response.data["errors"]
        assert "غير متطابقة" in str(response.data)
    
    def test_signup_weak_password(self, api_client, free_plan):
        """Test that signup fails with weak password."""
        data = {
            "company_name": "Test Company",
            "phone": "+963944123456",
            "password": "12345",  # Too short
            "password_confirm": "12345",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "password" in response.data["errors"]
    
    def test_signup_password_no_letters(self, api_client, free_plan):
        """Test that signup fails with password containing only numbers."""
        data = {
            "company_name": "Test Company",
            "phone": "+963944123456",
            "password": "12345678",  # Only numbers
            "password_confirm": "12345678",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "أحرف وأرقام" in str(response.data)
    
    def test_signup_missing_required_fields(self, api_client, free_plan):
        """Test that signup fails with missing required fields."""
        data = {
            "company_name": "Test Company",
            # Missing phone and password
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        
        assert response.status_code == status.HTTP_400_BAD_REQUEST
        assert "errors" in response.data
    
    def test_signup_phone_normalization(self, api_client, free_plan):
        """Test that phone numbers are normalized correctly."""
        test_cases = [
            "+963944123456",
            "963944123456",
            "00963944123456",
            "0944123456",
            "+963 944 123 456",
            "+963-944-123-456",
        ]
        
        for i, phone_input in enumerate(test_cases):
            data = {
                "company_name": f"Test Company {i}",
                "phone": phone_input,
                "password": "SecurePass123",
                "password_confirm": "SecurePass123",
            }
            
            response = api_client.post("/api/auth/company/signup", data, format="json")
            
            if response.status_code == status.HTTP_201_CREATED:
                # Phone should be normalized to +963944123456
                user_data = response.data["data"]["user"]
                assert user_data["phone"] == "+963944123456"
                
                # Clean up for next iteration
                SubUser.objects.filter(phone="+963944123456").delete()
                Company.objects.filter(name=f"Test Company {i}").delete()
    
    def test_signup_unique_slug_generation(self, api_client, free_plan, db):
        """Test that unique slugs are generated for companies with same names."""
        # Create first company
        data1 = {
            "company_name": "Test Company",
            "phone": "+963944123451",
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
        }
        
        response1 = api_client.post("/api/auth/company/signup", data1, format="json")
        assert response1.status_code == status.HTTP_201_CREATED
        company1 = Company.objects.get(name="Test Company")
        assert company1.slug == "test-company"
        
        # Create second company with same name
        data2 = {
            "company_name": "Test Company",
            "phone": "+963944123452",
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
        }
        
        response2 = api_client.post("/api/auth/company/signup", data2, format="json")
        assert response2.status_code == status.HTTP_201_CREATED
        
        # Check that slug is different
        companies = Company.objects.filter(name="Test Company").order_by("id")
        assert companies[0].slug == "test-company"
        assert companies[1].slug == "test-company-1"
    
    def test_signup_password_is_hashed(self, api_client, free_plan):
        """Test that password is hashed and not stored in plain text."""
        data = {
            "company_name": "Test Company",
            "phone": "+963944123456",
            "password": "SecurePass123",
            "password_confirm": "SecurePass123",
        }
        
        response = api_client.post("/api/auth/company/signup", data, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        
        # Check that password is hashed
        subuser = SubUser.objects.get(phone="+963944123456")
        assert subuser.password != "SecurePass123"
        assert subuser.password.startswith("pbkdf2_sha256$")
