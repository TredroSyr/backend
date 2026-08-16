"""Tenant-scoping middleware for multi-tenant isolation."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework_simplejwt.authentication import JWTAuthentication

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


class TenantScopingMiddleware:
    """
    Middleware that extracts tenant (company_id) from JWT token and attaches it to the request.
    This enables automatic tenant-scoping in queries.
    """
    
    def __init__(self, get_response):
        self.get_response = get_response
    
    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Extract JWT token and decode it
        jwt_auth = JWTAuthentication()
        
        try:
            # Attempt to authenticate the request
            auth_result = jwt_auth.authenticate(request)
            
            if auth_result is not None:
                user, token = auth_result
                
                # Extract custom claims from token
                actor_type = token.get("actor_type")
                company_id = token.get("company_id")
                is_owner = token.get("is_owner", False)
                
                # Attach to request for use in views
                request.actor_type = actor_type
                request.company_id = company_id
                request.is_owner = is_owner
                request.token_payload = dict(token)
            else:
                # No authentication - public endpoints
                request.actor_type = None
                request.company_id = None
                request.is_owner = False
                request.token_payload = {}
        
        except Exception:
            # Authentication failed or no token present
            request.actor_type = None
            request.company_id = None
            request.is_owner = False
            request.token_payload = {}
        
        response = self.get_response(request)
        return response
