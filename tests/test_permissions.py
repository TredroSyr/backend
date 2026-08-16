"""Tests for permission classes and decorators."""

from __future__ import annotations

import pytest
from django.http import HttpRequest
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory

from apps.companies.permissions import (
    HasModulePermission,
    IsCustomer,
    IsOwner,
    IsRep,
    IsSubUser,
    owner_required,
    require_module_permission,
)


class DummyView:
    """Dummy view for testing permissions."""
    
    required_module = None
    required_permission = "can_view"


class TestIsOwner:
    """Tests for IsOwner permission class."""
    
    def test_owner_has_permission(self):
        """Test that company owners have permission."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.is_owner = True
        
        permission = IsOwner()
        assert permission.has_permission(request, DummyView()) is True
    
    def test_non_owner_no_permission(self):
        """Test that non-owners don't have permission."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.is_owner = False
        
        permission = IsOwner()
        assert permission.has_permission(request, DummyView()) is False


class TestActorTypePermissions:
    """Tests for actor type permission classes."""
    
    def test_is_subuser(self):
        """Test IsSubUser permission class."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.actor_type = "subuser"
        
        permission = IsSubUser()
        assert permission.has_permission(request, DummyView()) is True
    
    def test_is_rep(self):
        """Test IsRep permission class."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.actor_type = "rep"
        
        permission = IsRep()
        assert permission.has_permission(request, DummyView()) is True
    
    def test_is_customer(self):
        """Test IsCustomer permission class."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.actor_type = "customer"
        
        permission = IsCustomer()
        assert permission.has_permission(request, DummyView()) is True
    
    def test_wrong_actor_type(self):
        """Test that wrong actor type fails permission check."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.actor_type = "rep"
        
        permission = IsSubUser()
        assert permission.has_permission(request, DummyView()) is False


class TestHasModulePermission:
    """Tests for HasModulePermission class."""
    
    def test_no_module_required(self):
        """Test that permission passes when no module is required."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        
        view = DummyView()
        view.required_module = None
        
        permission = HasModulePermission()
        assert permission.has_permission(request, view) is True
    
    def test_owner_has_all_permissions(self):
        """Test that owners have access to all modules."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.is_owner = True
        request.actor_type = "subuser"
        
        view = DummyView()
        view.required_module = "products"
        view.required_permission = "can_action"
        
        permission = HasModulePermission()
        assert permission.has_permission(request, view) is True
    
    def test_subuser_with_permission(self):
        """Test that subuser with required permission has access."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.is_owner = False
        request.actor_type = "subuser"
        request.user_permissions = {
            "products": {"can_view": True, "can_action": True}
        }
        
        view = DummyView()
        view.required_module = "products"
        view.required_permission = "can_view"
        
        permission = HasModulePermission()
        assert permission.has_permission(request, view) is True
    
    def test_subuser_without_permission(self):
        """Test that subuser without required permission is denied."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.is_owner = False
        request.actor_type = "subuser"
        request.user_permissions = {
            "products": {"can_view": True, "can_action": False}
        }
        
        view = DummyView()
        view.required_module = "products"
        view.required_permission = "can_action"
        
        permission = HasModulePermission()
        assert permission.has_permission(request, view) is False
    
    def test_rep_cannot_access_modules(self):
        """Test that reps don't have module permissions."""
        factory = APIRequestFactory()
        request = factory.get("/api/test/")
        request.is_owner = False
        request.actor_type = "rep"
        request.user_permissions = {}
        
        view = DummyView()
        view.required_module = "products"
        
        permission = HasModulePermission()
        assert permission.has_permission(request, view) is False


class TestDecorators:
    """Tests for permission decorators."""
    
    def test_owner_required_decorator_allows_owner(self):
        """Test that owner_required allows owners."""
        @owner_required
        def test_view(request):
            return "success"
        
        request = HttpRequest()
        request.is_owner = True
        
        result = test_view(request)
        assert result == "success"
    
    def test_owner_required_decorator_denies_non_owner(self):
        """Test that owner_required denies non-owners."""
        @owner_required
        def test_view(request):
            return "success"
        
        request = HttpRequest()
        request.is_owner = False
        
        with pytest.raises(PermissionDenied):
            test_view(request)
    
    def test_require_module_permission_allows_with_permission(self):
        """Test that require_module_permission allows users with permission."""
        @require_module_permission("products", "can_view")
        def test_view(request):
            return "success"
        
        request = HttpRequest()
        request.is_owner = False
        request.user_permissions = {
            "products": {"can_view": True, "can_action": False}
        }
        
        result = test_view(request)
        assert result == "success"
    
    def test_require_module_permission_denies_without_permission(self):
        """Test that require_module_permission denies users without permission."""
        @require_module_permission("products", "can_action")
        def test_view(request):
            return "success"
        
        request = HttpRequest()
        request.is_owner = False
        request.user_permissions = {
            "products": {"can_view": True, "can_action": False}
        }
        
        with pytest.raises(PermissionDenied):
            test_view(request)
    
    def test_require_module_permission_allows_owner(self):
        """Test that require_module_permission always allows owners."""
        @require_module_permission("products", "can_action")
        def test_view(request):
            return "success"
        
        request = HttpRequest()
        request.is_owner = True
        request.user_permissions = {}
        
        result = test_view(request)
        assert result == "success"
