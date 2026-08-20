"""Views for authentication."""

from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.serializers import (
    CompanySigninSerializer,
    CompanySignupSerializer,
    CustomerSigninSerializer,
    CustomerSignupSerializer,
    RepSigninSerializer,
    SignoutSerializer,
    TokenRefreshSerializer,
)
from apps.authentication.utils import (
    generate_tokens_for_customer,
    generate_tokens_for_rep,
    generate_tokens_for_subuser,
    get_permissions_for_subuser,
    hash_password,
    verify_password,
)
from apps.billing.services import create_trial_subscription
from apps.companies.models import Company, SubUser
from apps.companies.serializers import CompanySerializer, SubUserSerializer
from apps.customers.models import Customer
from apps.reps.models import Rep
from core.responses import error_response, success_response


class CompanySignupView(APIView):
    """
    POST /api/auth/company/signup
    
    Register a new company with an owner SubUser.
    Auto-subscribes to the Free plan.
    """
    
    permission_classes = [AllowAny]
    
    @transaction.atomic
    def post(self, request):
        """Handle company signup."""
        serializer = CompanySignupSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="فشل إنشاء الحساب",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        data = serializer.validated_data
        
        # Generate unique slug from company name
        base_slug = slugify(data["company_name"])
        slug = base_slug
        counter = 1
        while Company.objects.filter(slug=slug).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        
        # Create Company
        company = Company.objects.create(
            name=data["company_name"],
            slug=slug,
            currency=data.get("currency", "SYP"),
            is_active=True,
        )
        
        # Create owner SubUser
        subuser = SubUser.objects.create(
            company=company,
            name=data["company_name"],  # Use company name as owner name initially
            phone=data["phone"],
            password=hash_password(data["password"]),
            is_owner=True,
            is_active=True,
            role=None,  # Owners don't need a role
        )
        
        # Auto-subscribe to Free plan
        try:
            subscription = create_trial_subscription(company)
        except Exception as e:
            # If subscription creation fails, rollback is automatic due to @transaction.atomic
            return error_response(
                message="فشل إنشاء الاشتراك",
                errors={"subscription": [str(e)]},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        
        # Generate JWT tokens
        tokens = generate_tokens_for_subuser(subuser)
        
        # Prepare response
        return success_response(
            data={
                "company": CompanySerializer(company).data,
                "user": SubUserSerializer(subuser).data,
                "tokens": tokens,
            },
            message="تم إنشاء الحساب بنجاح",
            status_code=status.HTTP_201_CREATED,
        )


class CompanySigninView(APIView):
    """
    POST /api/auth/company/signin
    
    Authenticate a company user (owner or staff) and return JWT tokens.
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle company signin."""
        serializer = CompanySigninSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات الدخول غير صحيحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        phone = serializer.validated_data["phone"]
        password = serializer.validated_data["password"]
        
        # Find SubUser by phone
        try:
            subuser = SubUser.objects.select_related("company", "role").get(phone=phone)
        except SubUser.DoesNotExist:
            return error_response(
                message="رقم الهاتف أو كلمة المرور غير صحيحة",
                errors={"credentials": ["بيانات الدخول غير صحيحة"]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Verify password
        if not verify_password(password, subuser.password):
            return error_response(
                message="رقم الهاتف أو كلمة المرور غير صحيحة",
                errors={"credentials": ["بيانات الدخول غير صحيحة"]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Check if user is active
        if not subuser.is_active:
            return error_response(
                message="الحساب غير نشط",
                errors={"account": ["تم تعطيل هذا الحساب. يرجى التواصل مع الدعم الفني"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Check if company is active
        if not subuser.company.is_active:
            return error_response(
                message="حساب الشركة غير نشط",
                errors={"account": ["تم تعطيل حساب الشركة. يرجى التواصل مع الدعم الفني"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Generate JWT tokens
        tokens = generate_tokens_for_subuser(subuser)
        
        # Get user permissions
        permissions = get_permissions_for_subuser(subuser)
        
        # Prepare response
        user_data = SubUserSerializer(subuser).data
        user_data["permissions"] = permissions
        
        return success_response(
            data={
                "user": user_data,
                "tokens": tokens,
            },
            message="تم تسجيل الدخول بنجاح",
            status_code=status.HTTP_200_OK,
        )


class RepSigninView(APIView):
    """
    POST /api/auth/rep/signin
    
    Authenticate a sales representative and return JWT tokens.
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle rep signin."""
        serializer = RepSigninSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات الدخول غير صحيحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        phone = serializer.validated_data["phone"]
        password = serializer.validated_data["password"]
        
        # Find Rep by phone
        try:
            rep = Rep.objects.select_related("company").get(phone=phone)
        except Rep.DoesNotExist:
            return error_response(
                message="رقم الهاتف أو كلمة المرور غير صحيحة",
                errors={"credentials": ["بيانات الدخول غير صحيحة"]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Verify password
        if not verify_password(password, rep.password):
            return error_response(
                message="رقم الهاتف أو كلمة المرور غير صحيحة",
                errors={"credentials": ["بيانات الدخول غير صحيحة"]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Check if rep is active
        if not rep.is_active:
            return error_response(
                message="الحساب غير نشط",
                errors={"account": ["تم تعطيل هذا الحساب. يرجى التواصل مع إدارة الشركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Check if company is active
        if not rep.company.is_active:
            return error_response(
                message="حساب الشركة غير نشط",
                errors={"account": ["تم تعطيل حساب الشركة"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Generate JWT tokens
        tokens = generate_tokens_for_rep(rep)
        
        # Prepare response
        rep_data = {
            "id": rep.id,
            "name": rep.name,
            "phone": rep.phone,
            "referral_code": rep.referral_code,
            "is_active": rep.is_active,
            "company": CompanySerializer(rep.company).data,
        }
        
        return success_response(
            data={
                "rep": rep_data,
                "tokens": tokens,
            },
            message="تم تسجيل الدخول بنجاح",
            status_code=status.HTTP_200_OK,
        )


class TokenRefreshView(APIView):
    """
    POST /api/auth/token/refresh
    
    Generate a new access token using a valid refresh token.
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle token refresh."""
        serializer = TokenRefreshSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="رمز التحديث مطلوب",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        try:
            refresh = RefreshToken(serializer.validated_data["refresh"])
            access_token = str(refresh.access_token)
            
            return success_response(
                data={"access": access_token},
                message="تم تحديث الرمز بنجاح",
                status_code=status.HTTP_200_OK,
            )
        except (InvalidToken, TokenError) as e:
            return error_response(
                message="رمز التحديث غير صالح أو منتهي الصلاحية",
                errors={"refresh": [str(e)]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )


class SignoutView(APIView):
    """
    POST /api/auth/signout
    
    Client-side signout (token invalidation happens on client).
    Note: Token blacklisting is disabled due to custom user models.
    """
    
    def post(self, request):
        """Handle signout."""
        serializer = SignoutSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="رمز التحديث مطلوب",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        # Note: Token blacklisting is disabled in this implementation
        # Clients should remove tokens from local storage
        # Access tokens will expire naturally after 1 hour
        # Refresh tokens will expire after 7 days
        
        return success_response(
            message="تم تسجيل الخروج بنجاح",
            status_code=status.HTTP_200_OK,
        )



class CustomerSignupView(APIView):
    """
    POST /api/auth/customer/signup
    
    Customer self-registration. Optionally accepts referral_code for auto-assignment to rep.
    """
    
    permission_classes = [AllowAny]
    
    @transaction.atomic
    def post(self, request):
        """Handle customer signup."""
        serializer = CustomerSignupSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="فشل إنشاء الحساب",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        data = serializer.validated_data
        
        # Find rep by referral code if provided
        assigned_rep = None
        if data.get("referral_code"):
            try:
                assigned_rep = Rep.objects.get(
                    referral_code=data["referral_code"],
                    is_active=True,
                )
            except Rep.DoesNotExist:
                pass  # Validation already caught this, but be defensive
        
        # Create customer
        customer = Customer.objects.create(
            name=data["name"],
            phone=data["phone"],
            email=data.get("email") or None,
            password=hash_password(data["password"]),
            assigned_rep=assigned_rep,
            referral_code_used=data.get("referral_code") or None,  # Store original referral code
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            is_active=True,
        )
        
        # Generate JWT tokens
        tokens = generate_tokens_for_customer(customer)
        
        # Prepare response
        customer_data = {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "assigned_rep": {
                "id": assigned_rep.id,
                "name": assigned_rep.name,
                "phone": assigned_rep.phone,
            } if assigned_rep else None,
            "referral_code_used": customer.referral_code_used,
            "has_location": customer.latitude is not None,
        }
        
        return success_response(
            data={
                "customer": customer_data,
                "tokens": tokens,
            },
            message="تم إنشاء الحساب بنجاح",
            status_code=status.HTTP_201_CREATED,
        )


class CustomerSigninView(APIView):
    """
    POST /api/auth/customer/signin
    
    Authenticate a customer and return JWT tokens.
    """
    
    permission_classes = [AllowAny]
    
    def post(self, request):
        """Handle customer signin."""
        serializer = CustomerSigninSerializer(data=request.data)
        
        if not serializer.is_valid():
            return error_response(
                message="بيانات الدخول غير صحيحة",
                errors=serializer.errors,
                status_code=status.HTTP_400_BAD_REQUEST,
            )
        
        phone = serializer.validated_data["phone"]
        password = serializer.validated_data["password"]
        
        # Find Customer by phone
        try:
            customer = Customer.objects.select_related("assigned_rep").get(phone=phone)
        except Customer.DoesNotExist:
            return error_response(
                message="رقم الهاتف أو كلمة المرور غير صحيحة",
                errors={"credentials": ["بيانات الدخول غير صحيحة"]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Verify password
        if not verify_password(password, customer.password):
            return error_response(
                message="رقم الهاتف أو كلمة المرور غير صحيحة",
                errors={"credentials": ["بيانات الدخول غير صحيحة"]},
                status_code=status.HTTP_401_UNAUTHORIZED,
            )
        
        # Check if customer is active
        if not customer.is_active:
            return error_response(
                message="الحساب غير نشط",
                errors={"account": ["تم تعطيل هذا الحساب. يرجى التواصل مع الدعم الفني"]},
                status_code=status.HTTP_403_FORBIDDEN,
            )
        
        # Generate JWT tokens
        tokens = generate_tokens_for_customer(customer)
        
        # Prepare response
        customer_data = {
            "id": customer.id,
            "name": customer.name,
            "phone": customer.phone,
            "email": customer.email,
            "assigned_rep": {
                "id": customer.assigned_rep.id,
                "name": customer.assigned_rep.name,
                "phone": customer.assigned_rep.phone,
            } if customer.assigned_rep else None,
            "referral_code_used": customer.referral_code_used,
            "has_location": customer.latitude is not None,
            "is_active": customer.is_active,
        }
        
        return success_response(
            data={
                "customer": customer_data,
                "tokens": tokens,
            },
            message="تم تسجيل الدخول بنجاح",
            status_code=status.HTTP_200_OK,
        )
