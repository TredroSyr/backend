"""Custom JWT authentication for multi-actor system."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework_simplejwt.exceptions import AuthenticationFailed

if TYPE_CHECKING:
    from django.http import HttpRequest
    from rest_framework_simplejwt.tokens import Token

    from apps.companies.models import SubUser
    from apps.customers.models import Customer
    from apps.reps.models import Rep


class MultiActorJWTAuthentication(JWTAuthentication):
    """
    Custom JWT authentication that supports multiple actor types.
    
    Handles authentication for:
    - SubUser (owner or staff): actor_type="subuser"
    - Rep (sales representative): actor_type="rep"
    - Customer: actor_type="customer"
    
    The stock JWTAuthentication only queries AUTH_USER_MODEL, which doesn't work
    for our multi-actor system where different actor types live in different tables.
    
    This authenticator:
    1. Validates the JWT token using the parent's validation logic
    2. Extracts actor_type from the token payload
    3. Queries the appropriate model based on actor_type
    4. Enforces company_id scoping for tenant-scoped actors
    5. Sets request.actor_type, request.is_owner, and request.token_payload
    """
    
    def get_user(self, validated_token: Token) -> SubUser | Rep | Customer:
        """
        Resolve the authenticated user based on actor_type in the token.
        
        Args:
            validated_token: The validated JWT token containing custom claims
            
        Returns:
            The authenticated actor (SubUser, Rep, or Customer instance)
            
        Raises:
            AuthenticationFailed: If actor_type is missing/invalid or user not found
        """
        from apps.companies.models import SubUser
        from apps.customers.models import Customer
        from apps.reps.models import Rep
        
        # Extract claims from token
        actor_type = validated_token.get("actor_type")
        user_id = validated_token.get("user_id")
        company_id = validated_token.get("company_id")
        is_owner = validated_token.get("is_owner", False)
        
        # Validate required claims
        if not actor_type:
            raise AuthenticationFailed(
                "Token missing actor_type claim",
                code="missing_actor_type",
            )
        
        if not user_id:
            raise AuthenticationFailed(
                "Token missing user_id claim",
                code="missing_user_id",
            )
        
        # Route to appropriate model based on actor_type
        try:
            if actor_type == "subuser":
                user = self._get_subuser(user_id, company_id)
            elif actor_type == "rep":
                user = self._get_rep(user_id, company_id)
            elif actor_type == "customer":
                user = self._get_customer(user_id)
            else:
                raise AuthenticationFailed(
                    f"Unknown actor_type: {actor_type}",
                    code="unknown_actor_type",
                )
        except AuthenticationFailed:
            raise
        except Exception as e:
            raise AuthenticationFailed(
                f"Error loading user: {str(e)}",
                code="user_load_error",
            )
        
        # DRF permission classes (IsAuthenticated, etc.) and other Django/DRF
        # internals expect request.user to expose is_authenticated/is_anonymous.
        # Our actor models don't inherit from AbstractBaseUser so they lack
        # these natively. A token that reached this point has already passed
        # full JWT validation, so it's safe to stamp these on directly.
        user.is_authenticated = True
        user.is_anonymous = False
        
        return user
    
    def _get_subuser(self, user_id: int, company_id: int | None) -> SubUser:
        """
        Get SubUser by ID with company_id scoping.
        
        Args:
            user_id: SubUser primary key
            company_id: Company ID from token (required for scoping)
            
        Returns:
            SubUser instance
            
        Raises:
            AuthenticationFailed: If user not found or inactive
        """
        from apps.companies.models import SubUser
        
        if company_id is None:
            raise AuthenticationFailed(
                "SubUser token missing company_id",
                code="missing_company_id",
            )
        
        try:
            subuser = SubUser.objects.select_related("company").get(
                id=user_id,
                company_id=company_id,
            )
        except SubUser.DoesNotExist:
            raise AuthenticationFailed(
                "User not found",
                code="user_not_found",
            )
        
        # Check if user is active
        if not subuser.is_active:
            raise AuthenticationFailed(
                "User is inactive",
                code="user_inactive",
            )
        
        # Check if company is active
        if not subuser.company.is_active:
            raise AuthenticationFailed(
                "Company is inactive",
                code="company_inactive",
            )
        
        return subuser
    
    def _get_rep(self, user_id: int, company_id: int | None) -> Rep:
        """
        Get Rep by ID with company_id scoping.
        
        Args:
            user_id: Rep primary key
            company_id: Company ID from token (required for scoping)
            
        Returns:
            Rep instance
            
        Raises:
            AuthenticationFailed: If user not found or inactive
        """
        from apps.reps.models import Rep
        
        if company_id is None:
            raise AuthenticationFailed(
                "Rep token missing company_id",
                code="missing_company_id",
            )
        
        try:
            rep = Rep.objects.select_related("company").get(
                id=user_id,
                company_id=company_id,
            )
        except Rep.DoesNotExist:
            raise AuthenticationFailed(
                "User not found",
                code="user_not_found",
            )
        
        # Check if rep is active
        if not rep.is_active:
            raise AuthenticationFailed(
                "User is inactive",
                code="user_inactive",
            )
        
        # Check if company is active
        if not rep.company.is_active:
            raise AuthenticationFailed(
                "Company is inactive",
                code="company_inactive",
            )
        
        return rep
    
    def _get_customer(self, user_id: int) -> Customer:
        """
        Get Customer by ID (no company scoping - customers are global).
        
        Args:
            user_id: Customer primary key
            
        Returns:
            Customer instance
            
        Raises:
            AuthenticationFailed: If user not found or inactive
        """
        from apps.customers.models import Customer
        
        try:
            customer = Customer.objects.get(id=user_id)
        except Customer.DoesNotExist:
            raise AuthenticationFailed(
                "User not found",
                code="user_not_found",
            )
        
        # Check if customer is active
        if not customer.is_active:
            raise AuthenticationFailed(
                "User is inactive",
                code="user_inactive",
            )
        
        return customer
    
    def authenticate(self, request: HttpRequest) -> tuple[SubUser | Rep | Customer, Token] | None:
        """
        Authenticate the request and attach custom attributes.
        
        This method:
        1. Validates the JWT token (via parent class)
        2. Resolves the actor (via get_user)
        3. Attaches request.actor_type, request.is_owner, request.token_payload
        
        Args:
            request: The HTTP request
            
        Returns:
            Tuple of (user, validated_token) or None if no token present
        """
        result = super().authenticate(request)
        
        if result is None:
            return None
        
        user, validated_token = result
        
        # Extract token payload as dict for middleware/permissions
        token_payload = dict(validated_token.payload)
        
        # Attach custom attributes to request for permissions/middleware
        request.actor_type = token_payload.get("actor_type")
        request.is_owner = token_payload.get("is_owner", False)
        request.token_payload = token_payload
        
        return user, validated_token