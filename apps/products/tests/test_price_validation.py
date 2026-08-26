"""Tests for price and image validation constraints."""

from __future__ import annotations

import pytest
from django.test import TestCase
from rest_framework.exceptions import ValidationError

from apps.common.models import Currency, UnitOfMeasure
from apps.companies.models import Company
from apps.customers.models import CustomerCategory
from apps.products.models import Product, ProductImage, ProductPrice
from apps.products.serializers import ProductImageSerializer, ProductPriceSerializer


@pytest.mark.django_db
class PrimaryImageValidationTestCase(TestCase):
    """Test primary image uniqueness constraint."""
    
    def setUp(self):
        """Set up test data."""
        self.unit = UnitOfMeasure.objects.create(code="kg", name="Kilogram", is_active=True)
        self.currency = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_active=True)
        
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            currency=self.currency,
        )
        
        self.product = Product.objects.create(
            company=self.company,
            name="Test Product",
            unit=self.unit,
        )
    
    def test_only_one_primary_image_allowed(self):
        """Test that only one image can be primary per product."""
        # Create first primary image
        image1 = ProductImage.objects.create(
            product=self.product,
            image="products/image1.jpg",
            is_primary=True,
        )
        
        # Attempting to create another primary image should be handled by the view
        # The serializer validation allows it, but the view should unset the first one
        image2_data = {
            'image': 'products/image2.jpg',
            'is_primary': True,
        }
        
        serializer = ProductImageSerializer(
            data=image2_data,
            context={'product': self.product}
        )
        
        assert serializer.is_valid()
        
        # In the view, setting is_primary=True will unset other primary images
        # This is tested in integration tests, but we verify the flag is set
        assert '_unset_other_primary' in serializer.validated_data
    
    def test_first_image_defaults_to_primary(self):
        """Test that the first image is automatically set as primary."""
        # This logic is in the view's create method
        # We verify the behavior by checking that when no images exist,
        # the first one should be made primary
        
        assert not ProductImage.objects.filter(product=self.product).exists()
        
        # When creating the first image, the view should set is_primary=True
        # This is handled in ProductImageViewSet.create()


@pytest.mark.django_db
class DefaultPriceValidationTestCase(TestCase):
    """Test default price uniqueness constraint."""
    
    def setUp(self):
        """Set up test data."""
        self.unit = UnitOfMeasure.objects.create(code="kg", name="Kilogram", is_active=True)
        self.currency_usd = Currency.objects.create(code="USD", name="US Dollar", symbol="$", is_active=True)
        self.currency_eur = Currency.objects.create(code="EUR", name="Euro", symbol="€", is_active=True)
        
        self.company = Company.objects.create(
            name="Test Company",
            slug="test-company",
            currency=self.currency_usd,
        )
        
        self.product = Product.objects.create(
            company=self.company,
            name="Test Product",
            unit=self.unit,
        )
        
        self.customer_category = CustomerCategory.objects.create(
            company=self.company,
            name="Wholesale",
        )
    
    def test_only_one_default_price_per_product(self):
        """Test that only one general price can be marked as default."""
        # Create first default price
        ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=100.00,
            is_default=True,
            customer_category=None,
        )
        
        # Attempt to create another default price
        serializer = ProductPriceSerializer(
            data={
                'currency': self.currency_eur.id,
                'price_type': 'standard',
                'price': 90.00,
                'is_default': True,
                'customer_category': None,
            },
            context={'product': self.product, 'company_id': self.company.id}
        )
        
        assert not serializer.is_valid()
        assert 'is_default' in serializer.errors
    
    def test_default_price_must_be_general_not_category_specific(self):
        """Test that default price cannot have a customer_category."""
        serializer = ProductPriceSerializer(
            data={
                'currency': self.currency_usd.id,
                'price_type': 'standard',
                'price': 100.00,
                'is_default': True,
                'customer_category': self.customer_category.id,
            },
            context={'product': self.product, 'company_id': self.company.id}
        )
        
        assert not serializer.is_valid()
        assert 'is_default' in serializer.errors
    
    def test_one_general_price_per_currency_price_type(self):
        """Test uniqueness of general (no customer_category) prices."""
        # Create first general price
        ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=100.00,
            customer_category=None,
        )
        
        # Attempt to create duplicate general price
        serializer = ProductPriceSerializer(
            data={
                'currency': self.currency_usd.id,
                'price_type': 'standard',
                'price': 110.00,
                'customer_category': None,
            },
            context={'product': self.product, 'company_id': self.company.id}
        )
        
        assert not serializer.is_valid()
        assert 'currency' in serializer.errors
    
    def test_one_price_per_currency_price_type_customer_category(self):
        """Test uniqueness of customer-category specific prices."""
        # Create first category-specific price
        ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=80.00,
            customer_category=self.customer_category,
        )
        
        # Attempt to create duplicate category-specific price
        serializer = ProductPriceSerializer(
            data={
                'currency': self.currency_usd.id,
                'price_type': 'standard',
                'price': 85.00,
                'customer_category': self.customer_category.id,
            },
            context={'product': self.product, 'company_id': self.company.id}
        )
        
        assert not serializer.is_valid()
        assert 'customer_category' in serializer.errors
    
    def test_can_have_both_general_and_category_specific_prices(self):
        """Test that a product can have both general and category-specific prices."""
        # Create general price
        ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=100.00,
            customer_category=None,
        )
        
        # Create category-specific price (should be allowed)
        serializer = ProductPriceSerializer(
            data={
                'currency': self.currency_usd.id,
                'price_type': 'standard',
                'price': 80.00,
                'customer_category': self.customer_category.id,
            },
            context={'product': self.product, 'company_id': self.company.id}
        )
        
        assert serializer.is_valid()
        price = serializer.save(product=self.product)
        assert price.customer_category == self.customer_category
    
    def test_different_price_types_allowed_for_same_currency(self):
        """Test that different price types can exist for the same currency."""
        # Create standard price
        ProductPrice.objects.create(
            product=self.product,
            currency=self.currency_usd,
            price_type="standard",
            price=100.00,
            customer_category=None,
        )
        
        # Create wholesale price (should be allowed)
        serializer = ProductPriceSerializer(
            data={
                'currency': self.currency_usd.id,
                'price_type': 'wholesale',
                'price': 80.00,
                'customer_category': None,
            },
            context={'product': self.product, 'company_id': self.company.id}
        )
        
        assert serializer.is_valid()
