"""Tests for company scoping in products API."""

from __future__ import annotations

import pytest
from django.test import TestCase
from rest_framework.test import APIClient

from apps.common.models import Currency, UnitOfMeasure
from apps.companies.models import Company, SubUser
from apps.products.models import Product, ProductCategory, ProductPrice


@pytest.mark.django_db
class CompanyScopingTestCase(TestCase):
    """Test that company scoping prevents cross-company data access."""
    
    def setUp(self):
        """Set up test data for two companies."""
        # Create units and currency (global)
        self.unit = UnitOfMeasure.objects.create(
            code="kg",
            name="Kilogram",
            is_active=True,
        )
        self.currency = Currency.objects.create(
            code="USD",
            name="US Dollar",
            symbol="$",
            is_active=True,
        )
        
        # Company A
        self.company_a = Company.objects.create(
            name="Company A",
            slug="company-a",
            currency=self.currency,
        )
        self.user_a = SubUser.objects.create(
            company=self.company_a,
            name="User A",
            phone="0911111111",
            email="usera@example.com",
            password="password",
            is_owner=True,
        )
        self.category_a = ProductCategory.objects.create(
            company=self.company_a,
            name="Category A",
        )
        self.product_a = Product.objects.create(
            company=self.company_a,
            name="Product A",
            unit=self.unit,
            sku="SKU-A",
        )
        
        # Company B
        self.company_b = Company.objects.create(
            name="Company B",
            slug="company-b",
            currency=self.currency,
        )
        self.user_b = SubUser.objects.create(
            company=self.company_b,
            name="User B",
            phone="0922222222",
            email="userb@example.com",
            password="password",
            is_owner=True,
        )
        self.category_b = ProductCategory.objects.create(
            company=self.company_b,
            name="Category B",
        )
        self.product_b = Product.objects.create(
            company=self.company_b,
            name="Product B",
            unit=self.unit,
            sku="SKU-B",
        )
        
        self.client = APIClient()
    
    def _mock_auth(self, company_id):
        """Mock authentication by setting company_id on request."""
        # In real scenario, this would be set by JWT middleware
        self.client.defaults['HTTP_X_COMPANY_ID'] = str(company_id)
    
    def test_product_list_scoped_to_company(self):
        """Test that product listing only returns company's products."""
        # Mock auth as company A
        # Note: In production, this is handled by TenantScopingMiddleware + JWT
        # For testing, we'll need to directly test the view's queryset filtering
        from apps.products.views import ProductViewSet
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/api/companies/products/')
        request.company_id = self.company_a.id
        
        view = ProductViewSet.as_view({'get': 'list'})
        response = view(request)
        
        # Should only see company A's products
        assert response.status_code == 200
        products = response.data['data']['products']
        assert len(products) == 1
        assert products[0]['name'] == 'Product A'
    
    def test_product_detail_cross_company_denied(self):
        """Test that accessing another company's product is denied."""
        from apps.products.views import ProductViewSet
        from django.test import RequestFactory
        from rest_framework.exceptions import NotFound
        
        factory = RequestFactory()
        request = factory.get(f'/api/companies/products/{self.product_b.id}/')
        request.company_id = self.company_a.id
        
        view = ProductViewSet.as_view({'get': 'retrieve'})
        
        # Should raise NotFound (product not in company A's scope)
        with pytest.raises(NotFound):
            view(request, pk=self.product_b.id)
    
    def test_product_category_scoped_to_company(self):
        """Test that categories are scoped to company."""
        from apps.products.views import ProductCategoryViewSet
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.get('/api/companies/product-categories/')
        request.company_id = self.company_a.id
        
        view = ProductCategoryViewSet.as_view({'get': 'list'})
        response = view(request)
        
        # Should only see company A's categories
        assert response.status_code == 200
        categories = response.data['data']['categories']
        assert len(categories) == 1
        assert categories[0]['name'] == 'Category A'
    
    def test_product_creation_assigns_to_company(self):
        """Test that creating a product assigns it to the authenticated company."""
        from apps.products.views import ProductViewSet
        from django.test import RequestFactory
        
        factory = RequestFactory()
        request = factory.post('/api/companies/products/', {
            'name': 'New Product',
            'unit': self.unit.id,
        })
        request.company_id = self.company_a.id
        
        view = ProductViewSet.as_view({'post': 'create'})
        response = view(request)
        
        assert response.status_code == 201
        
        # Verify product was created for company A
        product = Product.objects.get(name='New Product')
        assert product.company_id == self.company_a.id
    
    def test_cannot_assign_another_companys_category_to_product(self):
        """Test that a product cannot be assigned to another company's category."""
        # Attempt to create product in company A with company B's category
        # This should be caught by serializer validation
        from apps.products.serializers import ProductWriteSerializer
        
        serializer = ProductWriteSerializer(
            data={
                'name': 'Invalid Product',
                'unit': self.unit.id,
                'category': self.category_b.id,
            },
            context={'company_id': self.company_a.id}
        )
        
        assert not serializer.is_valid()
        assert 'category' in serializer.errors
