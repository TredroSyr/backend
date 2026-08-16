"""Tests for authentication utilities."""

from __future__ import annotations

import pytest
from apps.authentication.utils import (
    hash_password,
    normalize_phone,
    validate_phone,
    verify_password,
)


class TestPasswordHashing:
    """Tests for password hashing and verification."""
    
    def test_hash_password(self):
        """Test that password is hashed correctly."""
        password = "SecurePass123!"
        hashed = hash_password(password)
        
        assert hashed != password
        assert hashed.startswith("pbkdf2_sha256$")
    
    def test_verify_password_correct(self):
        """Test that correct password verification works."""
        password = "SecurePass123!"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) is True
    
    def test_verify_password_incorrect(self):
        """Test that incorrect password verification fails."""
        password = "SecurePass123!"
        wrong_password = "WrongPass456!"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) is False


class TestPhoneValidation:
    """Tests for phone number validation and normalization."""
    
    @pytest.mark.parametrize(
        "phone",
        [
            "+963944123456",
            "+963955987654",
            "+963112345678",
        ],
    )
    def test_validate_phone_valid(self, phone):
        """Test that valid Syrian phone numbers pass validation."""
        assert validate_phone(phone) is True
    
    @pytest.mark.parametrize(
        "phone",
        [
            "944123456",  # Missing country code
            "+96294412345",  # Too few digits
            "+9639441234567",  # Too many digits
            "+962944123456",  # Wrong country code
            "963944123456",  # Missing +
            "+963 944 123 456",  # With spaces
        ],
    )
    def test_validate_phone_invalid(self, phone):
        """Test that invalid phone numbers fail validation."""
        assert validate_phone(phone) is False
    
    @pytest.mark.parametrize(
        "input_phone,expected",
        [
            ("+963944123456", "+963944123456"),  # Already normalized
            ("963944123456", "+963944123456"),  # Missing +
            ("00963944123456", "+963944123456"),  # International prefix
            ("0944123456", "+963944123456"),  # Local format
            ("+963 944 123 456", "+963944123456"),  # With spaces
            ("+963-944-123-456", "+963944123456"),  # With dashes
        ],
    )
    def test_normalize_phone(self, input_phone, expected):
        """Test that various phone formats are normalized correctly."""
        assert normalize_phone(input_phone) == expected
