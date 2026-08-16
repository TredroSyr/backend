"""Authentication utilities for password hashing, JWT generation, and phone validation."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Literal

from django.contrib.auth.hashers import check_password, make_password
from rest_framework_simplejwt.tokens import RefreshToken

if TYPE_CHECKING:
    from apps.companies.models import SubUser
    from apps.customers.models import Customer
    from apps.reps.models import Rep


def hash_password(password: str) -> str:
    """Hash a password using Django's default hasher (PBKDF2)."""
    return make_password(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a password against its hash."""
    return check_password(password, hashed_password)


def validate_phone(phone: str) -> bool:
    """
    Validate Syrian phone number format.
    Expected: +963XXXXXXXXX (country code + 9 digits)
    """
    pattern = r"^\+963\d{9}$"
    return bool(re.match(pattern, phone))


def normalize_phone(phone: str) -> str:
    """
    Normalize phone number to standard format.
    Removes spaces, dashes, and ensures +963 prefix.
    """
    # Remove spaces and dashes
    phone = phone.replace(" ", "").replace("-", "")
    
    # Handle different input formats
    if phone.startswith("00963"):
        phone = "+" + phone[2:]
    elif phone.startswith("963") and not phone.startswith("+"):
        phone = "+" + phone
    elif phone.startswith("0") and len(phone) == 10:
        # Syrian local format (0944123456 -> +963944123456)
        phone = "+963" + phone[1:]
    
    return phone


def generate_tokens_for_subuser(
    subuser: SubUser,
) -> dict[str, str]:
    """
    Generate JWT access and refresh tokens for a SubUser.
    Includes custom claims: actor_type, company_id, is_owner.
    """
    # Create a minimal user wrapper to avoid OutstandingToken issues
    class TokenUser:
        def __init__(self, pk: int):
            self.pk = pk
            self.id = pk
            self.is_active = True
    
    token_user = TokenUser(subuser.id)
    refresh = RefreshToken.for_user(token_user)
    
    # Add custom claims
    refresh["actor_type"] = "subuser"
    refresh["company_id"] = subuser.company_id
    refresh["is_owner"] = subuser.is_owner
    refresh["user_id"] = subuser.id
    
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def generate_tokens_for_rep(rep: Rep) -> dict[str, str]:
    """
    Generate JWT access and refresh tokens for a Rep.
    Includes custom claims: actor_type, company_id, rep_id.
    """
    # SimpleJWT expects a user object with pk/id attribute
    # We'll create a minimal wrapper
    class TokenUser:
        def __init__(self, pk: int):
            self.pk = pk
            self.id = pk
    
    token_user = TokenUser(rep.id)
    refresh = RefreshToken.for_user(token_user)
    
    # Add custom claims
    refresh["actor_type"] = "rep"
    refresh["company_id"] = rep.company_id
    refresh["rep_id"] = rep.id
    refresh["user_id"] = rep.id
    
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def generate_tokens_for_customer(customer: Customer) -> dict[str, str]:
    """
    Generate JWT access and refresh tokens for a Customer.
    Includes custom claims: actor_type, customer_id.
    Note: Customers are global entities, not tenant-scoped.
    """
    class TokenUser:
        def __init__(self, pk: int):
            self.pk = pk
            self.id = pk
    
    token_user = TokenUser(customer.id)
    refresh = RefreshToken.for_user(token_user)
    
    # Add custom claims
    refresh["actor_type"] = "customer"
    refresh["customer_id"] = customer.id
    refresh["user_id"] = customer.id
    
    return {
        "access": str(refresh.access_token),
        "refresh": str(refresh),
    }


def get_permissions_for_subuser(subuser: SubUser) -> dict[str, dict[str, bool]]:
    """
    Get all module permissions for a SubUser.
    Owners get full access to everything.
    Staff members get permissions based on their role.
    """
    if subuser.is_owner:
        # Owners have full access to all modules
        modules = [
            "products",
            "orders",
            "customers",
            "invoices",
            "billing",
            "reps",
            "notifications",
            "reports",
            "settings",
        ]
        return {
            module: {"can_view": True, "can_action": True} for module in modules
        }
    
    # For staff members, load permissions from their role
    permissions = {}
    if subuser.role:
        module_perms = subuser.role.permissions.all()
        for perm in module_perms:
            permissions[perm.module] = {
                "can_view": perm.can_view,
                "can_action": perm.can_action,
            }
    
    return permissions


ActorType = Literal["subuser", "rep", "customer"]


def get_actor_from_token_payload(
    payload: dict,
) -> tuple[ActorType, int, int | None]:
    """
    Extract actor information from JWT token payload.
    
    Returns:
        tuple: (actor_type, user_id, company_id)
        - actor_type: "subuser", "rep", or "customer"
        - user_id: The ID of the authenticated user
        - company_id: The company ID (None for customers)
    """
    actor_type = payload.get("actor_type")
    user_id = payload.get("user_id")
    company_id = payload.get("company_id")
    
    return actor_type, user_id, company_id
