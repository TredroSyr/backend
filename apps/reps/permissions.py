"""Permissions for rep-specific views."""

from __future__ import annotations

from rest_framework.permissions import BasePermission


class IsRep(BasePermission):
    """
    Permission class to verify that the authenticated user is a rep.
    
    Checks that:
    - User is authenticated
    - Actor type is "rep" (from token_payload)
    - Rep is active (already validated by authentication)
    """
    
    def has_permission(self, request, view):
        """Check if user is an authenticated rep."""
        # Check actor_type from request (set by MultiActorJWTAuthentication)
        actor_type = getattr(request, "actor_type", None)
        
        if actor_type != "rep":
            return False
        
        # Check if token_payload exists and has rep_id
        token_payload = getattr(request, "token_payload", {})
        rep_id = token_payload.get("rep_id")
        
        if not rep_id:
            return False
        
        return True
    
    def has_object_permission(self, request, view, obj):
        """Check if rep has permission to access specific object."""
        # For now, rely on queryset filtering
        # Object-level permissions can be added per viewset
        return True
