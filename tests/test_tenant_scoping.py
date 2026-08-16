"""Tests for tenant-scoping middleware and mixins."""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory

from apps.companies.middleware import TenantScopingMiddleware
from apps.companies.mixins import TenantScopedViewMixin


class TestTenantScopingMiddleware:
    """Tests for TenantScopingMiddleware."""
    
    def test_middleware_without_token(self):
        """Test middleware handles requests without JWT token."""
        factory = RequestFactory()
        request = factory.get("/api/test/")
        
        # Create a dummy get_response callable
        def get_response(req):
            return req
        
        middleware = TenantScopingMiddleware(get_response)
        processed_request = middleware(request)
        
        assert processed_request.actor_type is None
        assert processed_request.company_id is None
        assert processed_request.is_owner is False
    
    def test_middleware_with_invalid_token(self):
        """Test middleware handles invalid JWT token gracefully."""
        factory = RequestFactory()
        request = factory.get("/api/test/", HTTP_AUTHORIZATION="Bearer invalid_token")
        
        def get_response(req):
            return req
        
        middleware = TenantScopingMiddleware(get_response)
        processed_request = middleware(request)
        
        assert processed_request.actor_type is None
        assert processed_request.company_id is None


class DummyModel:
    """Dummy model for testing."""
    company_id = 1


class DummyQuerySet:
    """Dummy queryset for testing."""
    
    def __init__(self, company_id=None):
        self.company_id = company_id
        self.model = DummyModel
    
    def filter(self, **kwargs):
        """Mock filter method."""
        return DummyQuerySet(company_id=kwargs.get("company_id"))
    
    def none(self):
        """Mock none method."""
        return DummyQuerySet(company_id=None)


class DummyView(TenantScopedViewMixin):
    """Dummy view for testing tenant scoping."""
    
    def get_queryset(self):
        """Return dummy queryset."""
        return DummyQuerySet()


class TestTenantScopedViewMixin:
    """Tests for TenantScopedViewMixin."""
    
    def test_get_queryset_with_company_id(self):
        """Test that queryset is filtered by company_id from request."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.company_id = 123
        
        view = DummyView()
        view.request = request
        
        queryset = view.get_queryset()
        assert queryset.company_id == 123
    
    def test_get_queryset_without_company_id(self):
        """Test that queryset is empty when no company_id present."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.company_id = None
        
        view = DummyView()
        view.request = request
        
        queryset = view.get_queryset()
        # Should return empty queryset for safety
        assert queryset.company_id is None
    
    def test_get_company_id(self):
        """Test that get_company_id returns the correct company_id."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.company_id = 456
        
        view = DummyView()
        view.request = request
        
        assert view.get_company_id() == 456
    
    def test_ensure_company_access_same_company(self):
        """Test that ensure_company_access allows access to same company's object."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.company_id = 123
        
        view = DummyView()
        view.request = request
        
        # Create object from same company
        obj = type("obj", (), {"company_id": 123})()
        
        # Should not raise exception
        view.ensure_company_access(obj)
    
    def test_ensure_company_access_different_company(self):
        """Test that ensure_company_access denies access to different company's object."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.company_id = 123
        
        view = DummyView()
        view.request = request
        
        # Create object from different company
        obj = type("obj", (), {"company_id": 456})()
        
        # Should raise PermissionDenied
        with pytest.raises(PermissionDenied):
            view.ensure_company_access(obj)
    
    def test_ensure_company_access_no_auth(self):
        """Test that ensure_company_access denies access when not authenticated."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.company_id = None
        
        view = DummyView()
        view.request = request
        
        obj = type("obj", (), {"company_id": 123})()
        
        # Should raise PermissionDenied
        with pytest.raises(PermissionDenied):
            view.ensure_company_access(obj)
