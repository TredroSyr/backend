"""Tests for customer Excel import functionality."""

from __future__ import annotations

from io import BytesIO

import pytest
from django.contrib.auth.hashers import make_password
from openpyxl import Workbook

from apps.companies.models import Company
from apps.customers.excel_import import generate_template, parse_excel_file
from apps.customers.models import Customer
from apps.reps.models import Rep


@pytest.fixture
def company():
    """Create a test company."""
    return Company.objects.create(
        name="Test Company",
        phone="+963991111111",
        email="test@company.com",
        password=make_password("password123"),
        is_active=True,
    )


@pytest.fixture
def rep(company):
    """Create a test rep."""
    return Rep.objects.create(
        company=company,
        name="Test Rep",
        phone="+963992222222",
        password=make_password("password123"),
        referral_code="REP001",
        is_active=True,
    )


def create_test_excel(data: list[dict]) -> BytesIO:
    """Create a test Excel file with given data."""
    wb = Workbook()
    ws = wb.active
    
    # Headers
    headers = ["name", "phone", "email", "category", "assigned_rep_codes", "latitude", "longitude"]
    ws.append(headers)
    
    # Data rows
    for row in data:
        ws.append([row.get(h, "") for h in headers])
    
    excel_file = BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    return excel_file


@pytest.mark.django_db
class TestExcelImport:
    """Test Excel import functionality."""
    
    def test_generate_template(self):
        """Test template generation."""
        template = generate_template()
        assert template is not None
        assert len(template.getvalue()) > 0
    
    def test_import_valid_customers(self, company, rep):
        """Test importing valid customers."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",
                "email": "ahmad@test.com",
                "category": "تاجر",
                "assigned_rep_codes": "REP001",
            },
            {
                "name": "فاطمة علي",
                "phone": "+963992345678",
                "email": "",
                "category": "",
                "assigned_rep_codes": "",
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["total_rows"] == 2
        assert results["successful"] == 2
        assert results["failed"] == 0
        assert len(results["created_customers"]) == 2
        assert len(results["errors"]) == 0
        
        # Verify customers created
        assert Customer.objects.filter(phone="+963991234567").exists()
        assert Customer.objects.filter(phone="+963992345678").exists()
    
    def test_import_with_invalid_phone(self, company):
        """Test import with invalid phone number."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "123456",  # Invalid format
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["successful"] == 0
        assert results["failed"] == 1
        assert len(results["errors"]) == 1
        assert "phone" in results["errors"][0]["errors"]
    
    def test_import_with_missing_name(self, company):
        """Test import with missing required name field."""
        data = [
            {
                "name": "",  # Missing
                "phone": "+963991234567",
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["successful"] == 0
        assert results["failed"] == 1
        assert "name" in results["errors"][0]["errors"]
    
    def test_import_with_duplicate_phone(self, company):
        """Test import with duplicate phone number."""
        # Create existing customer
        Customer.objects.create(
            name="Existing Customer",
            phone="+963991234567",
        )
        
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",  # Duplicate
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["successful"] == 0
        assert results["failed"] == 1
        assert "phone" in results["errors"][0]["errors"]
    
    def test_import_with_invalid_rep_code(self, company):
        """Test import with invalid rep referral code."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",
                "assigned_rep_codes": "INVALID_CODE",
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["successful"] == 0
        assert results["failed"] == 1
        assert "assigned_rep_codes" in results["errors"][0]["errors"]
    
    def test_import_partial_success(self, company, rep):
        """Test import with mixed valid and invalid rows."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",
                "assigned_rep_codes": "REP001",
            },
            {
                "name": "",  # Invalid - missing name
                "phone": "+963992345678",
            },
            {
                "name": "خالد سعيد",
                "phone": "123456",  # Invalid phone
            },
            {
                "name": "علي حسن",
                "phone": "+963993456789",  # Valid
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["total_rows"] == 4
        assert results["successful"] == 2
        assert results["failed"] == 2
        assert len(results["created_customers"]) == 2
        assert len(results["errors"]) == 2
        
        # Verify correct customers created
        assert Customer.objects.filter(phone="+963991234567").exists()
        assert Customer.objects.filter(phone="+963993456789").exists()
        assert not Customer.objects.filter(phone="+963992345678").exists()
    
    def test_import_with_gps_coordinates(self, company):
        """Test import with GPS coordinates."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",
                "latitude": "33.513050",
                "longitude": "36.276950",
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["successful"] == 1
        assert results["failed"] == 0
        
        customer = Customer.objects.get(phone="+963991234567")
        assert customer.latitude is not None
        assert customer.longitude is not None
    
    def test_import_with_incomplete_gps(self, company):
        """Test import with only one GPS coordinate (should fail)."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",
                "latitude": "33.513050",
                "longitude": "",  # Missing
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        assert results["successful"] == 0
        assert results["failed"] == 1
        assert "location" in results["errors"][0]["errors"]
    
    def test_import_skip_empty_rows(self, company):
        """Test that completely empty rows are skipped."""
        data = [
            {
                "name": "أحمد محمود",
                "phone": "+963991234567",
            },
            {
                "name": "",
                "phone": "",
                "email": "",
            },  # Completely empty - should be skipped
            {
                "name": "فاطمة علي",
                "phone": "+963992345678",
            },
        ]
        
        excel_file = create_test_excel(data)
        results = parse_excel_file(excel_file, company.id)
        
        # Empty row should be skipped, not counted as failed
        assert results["successful"] == 2
        assert results["failed"] == 0
