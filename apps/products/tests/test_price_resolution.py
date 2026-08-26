"""Tests for price resolution service."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import TestCase

from apps.common.models import Currency, UnitOfMeasure
from apps.companies.models import Company
from apps.customers.models import CustomerCategory
from apps.products.models import Product, ProductPrice
from apps.products.services.pricing import (
    PriceNotFoundError,
    calculate_price_with_tax,
    resolve_product_price,
)


@pytest.mark.django_db
class PriceResolutionTestCase(TestCase):
    """Test price resolution fallback logic."""
    
    def setUp(self):
        """Set up test data."""
        self.unit = UnitOfMeasure.objects.create(code="kg", name="Kilogram", is_active=True)
        self.currency_usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_active=True)
        
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            currency=self.currency_usd,
        )
        
        self.product = Product.objects.create(
            company=self.company,
            name="Test Product",
            unit=self.unit,
            is_taxable=True,
            tax_rate=Decimal("10.00"),
        )
        
        self.wholesale_category = CustomerCategory.objects.create(
            company=self.company,
            name="Wholesale",
        )
        
        self.retail_category = CustomerCategory.objects.create(
            company=self.company,
            name="Retail",
        )
        
        # Create general price
        self.general_price = ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=Decimal("100.00"),
            customer_category=None,
            is_default=True,
        )
        
        # Create wholesale category-specific price
        self.wholesale_price = ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=Decimal("80.00"),
            customer_category=self.wholesale_category,
        )
    
    def test_resolve_general_price_when_no_category(self):
        """Test resolving general price when no customer category is provided."""
        result = resolve_product_price(
            product=self.product,
            currency=self.currency_usd,
            customer_category=None,
            price_type="standard",
        )
        
        assert result['price'] == Decimal("100.00")
        assert result['currency'] == self.currency_usd
        assert result['customer_category'] is None
        assert result['is_category_specific'] is False
        assert result['is_default'] is True
    
    def test_resolve_category_specific_price(self):
        """Test resolving category-specific price when category is provided."""
        result = resolve_product_price(
            product=self.product,
            currency=self.currency_usd,
            customer_category=self.wholesale_category,
            price_type="standard",
        )
        
        assert result['price'] == Decimal("80.00")
        assert result['customer_category'] == self.wholesale_category
        assert result['is_category_specific'] is True
    
    def test_fallback_to_general_price_when_category_price_not_found(self):
        """Test fallback to general price when category-specific price doesn't exist."""
        # Retail category doesn't have a specific price, should fall back to general
        result = resolve_product_price(
            product=self.product,
            currency=self.currency_usd,
            customer_category=self.retail_category,
            price_type="standard",
        )
        
        assert result['price'] == Decimal("100.00")
        assert result['customer_category'] is None
        assert result['is_category_specific'] is False
    
    def test_price_not_found_error_when_no_prices_exist(self):
        """Test that PriceNotFoundError is raised when no matching prices exist."""
        # Try to get wholesale price type (doesn't exist)
        with pytest.raises(PriceNotFoundError) as exc_info:
            resolve_product_price(
                product=self.product,
                currency=self.currency_usd,
                customer_category=None,
                price_type="wholesale",
            )
        
        assert "No price found" in str(exc_info.value)
    
    def test_resolve_price_with_currency_id(self):
        """Test that resolution works with currency ID instead of instance."""
        result = resolve_product_price(
            product=self.product,
            currency=self.currency_usd.id,  # Pass ID instead of instance
            customer_category=None,
            price_type="standard",
        )
        
        assert result['price'] == Decimal("100.00")
    
    def test_resolve_price_with_category_id(self):
        """Test that resolution works with category ID instead of instance."""
        result = resolve_product_price(
            product=self.product,
            currency=self.currency_usd,
            customer_category=self.wholesale_category.id,  # Pass ID
            price_type="standard",
        )
        
        assert result['price'] == Decimal("80.00")


@pytest.mark.django_db
class PriceTaxCalculationTestCase(TestCase):
    """Test price calculation with tax."""
    
    def setUp(self):
        """Set up test data."""
        self.unit = UnitOfMeasure.objects.create(code="kg", name="Kilogram", is_active=True)
        self.currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_active=True)
        
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            currency=self.currency,
        )
        
        self.taxable_product = Product.objects.create(
            company=self.company,
            name="Taxable Product",
            unit=self.unit,
            is_taxable=True,
            tax_rate=Decimal("21.00"),  # 21% tax
        )
        
        self.non_taxable_product = Product.objects.create(
            company=self.company,
            name="Non-Taxable Product",
            unit=self.unit,
            is_taxable=False,
        )
    
    def test_calculate_price_with_tax(self):
        """Test calculating price with tax included."""
        result = calculate_price_with_tax(
            price=Decimal("100.00"),
            product=self.taxable_product,
            include_tax=True,
        )
        
        assert result['base_price'] == Decimal("100.00")
        assert result['tax_rate'] == Decimal("21.00")
        assert result['tax_amount'] == Decimal("21.00")
        assert result['total_price'] == Decimal("121.00")
        assert result['is_taxable'] is True
    
    def test_calculate_price_without_tax(self):
        """Test calculating price without tax."""
        result = calculate_price_with_tax(
            price=Decimal("100.00"),
            product=self.taxable_product,
            include_tax=False,
        )
        
        assert result['base_price'] == Decimal("100.00")
        assert result['tax_amount'] == Decimal("0")
        assert result['total_price'] == Decimal("100.00")
    
    def test_non_taxable_product_has_no_tax(self):
        """Test that non-taxable products have zero tax."""
        result = calculate_price_with_tax(
            price=Decimal("100.00"),
            product=self.non_taxable_product,
            include_tax=True,
        )
        
        assert result['base_price'] == Decimal("100.00")
        assert result['tax_amount'] == Decimal("0")
        assert result['total_price'] == Decimal("100.00")
        assert result['is_taxable'] is False
        assert result['tax_rate'] is None
    
    def test_tax_calculation_precision(self):
        """Test that tax calculations are rounded to 2 decimal places."""
        result = calculate_price_with_tax(
            price=Decimal("99.99"),
            product=self.taxable_product,
            include_tax=True,
        )
        
        # 99.99 * 0.21 = 20.9979, should round to 20.00
        assert result['tax_amount'] == Decimal("21.00")
        assert result['total_price'] == Decimal("120.99")
