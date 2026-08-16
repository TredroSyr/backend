# Authentication & Onboarding API Documentation

## ✅ Implementation Status

**CURRENT STATE:** Authentication endpoints are fully implemented and ready for frontend integration.

**WHAT EXISTS:**
- ✅ Database models: Company, SubUser, Rep, Customer, Role, ModulePermission
- ✅ Health check endpoint: `GET /api/health/`
- ✅ All authentication endpoints (signup, signin, token refresh, signout)
- ✅ JWT authentication system using djangorestframework-simplejwt
- ✅ Company model fields for onboarding (logo, cover, governorate, region, description, business_type)
- ✅ Password hashing and verification utilities
- ✅ Company onboarding endpoint with optional fields
- ✅ Onboarding status endpoint
- ✅ Location and business type reference data endpoints

**WHAT NEEDS TO BE BUILT:**
- Nothing! All authentication and onboarding endpoints are implemented and ready.

This document specifies the complete API contract for frontend integration.

---

## Quick Reference for Frontend Integration

### Available Endpoints

#### ✅ Implemented & Ready
- `POST /api/auth/company/signup` - Register new company
- `POST /api/auth/company/signin` - Company user login
- `POST /api/auth/rep/signin` - Sales rep login
- `POST /api/auth/token/refresh` - Refresh access token
- `POST /api/auth/signout` - Logout (blacklist token)

#### ✅ Implemented (Onboarding Flow)
- `GET /api/companies/onboarding/status` - Get onboarding progress and company data
- `POST /api/companies/onboarding` - Complete onboarding in one step (all fields optional)
- `GET /api/companies/locations` - Get governorates & regions list
- `GET /api/companies/business-types` - Get business type options

### Typical Frontend Flow

1. **Registration**: `POST /api/auth/company/signup` → Returns tokens + company data
2. **Check Onboarding**: Check `onboarding_completed` flag in company data
3. **Onboarding**: If `false`, redirect to 4-step onboarding wizard
4. **Dashboard**: If `true`, redirect to main dashboard
5. **Login**: `POST /api/auth/company/signin` → Returns tokens + user data
6. **Token Refresh**: `POST /api/auth/token/refresh` when access token expires
7. **Logout**: `POST /api/auth/signout` to invalidate refresh token

### File Upload Notes for Onboarding
- Logo/Cover endpoints will use `multipart/form-data` (not JSON)
- Other onboarding steps use `application/json`
- Company model already has logo/cover fields ready for file uploads

---

## Overview
This document describes the authentication and onboarding endpoints for the Tredro platform, supporting **Company Sign-up/Sign-in** and **Sales Representative Sign-in**, followed by a 4-step company onboarding process.

### Endpoints Summary

| Endpoint | Method | Status | Purpose |
|----------|--------|--------|---------|
| `/api/auth/company/signup` | POST | ✅ Ready | Register new company with owner account |
| `/api/auth/company/signin` | POST | ✅ Ready | Login for company users (owner/staff) |
| `/api/auth/rep/signin` | POST | ✅ Ready | Login for sales representatives |
| `/api/auth/token/refresh` | POST | ✅ Ready | Refresh expired access token |
| `/api/auth/signout` | POST | ✅ Ready | Logout and blacklist token |
| `/api/companies/onboarding/status` | GET | ❌ Pending | Get onboarding progress |
| `/api/companies/onboarding/branding` | POST | ❌ Pending | Upload logo & cover (Step 1) |
| `/api/companies/onboarding/location` | POST | ❌ Pending | Set company location (Step 2) |
| `/api/companies/onboarding/description` | POST | ❌ Pending | Add company description (Step 3) |
| `/api/companies/onboarding/business-type` | POST | ❌ Pending | Select business type (Step 4) |
| `/api/companies/locations` | GET | ❌ Pending | Get governorates & regions list |
| `/api/companies/business-types` | GET | ❌ Pending | Get business type options |

---

## Base URL
```
/api/auth/
```

**✅ IMPLEMENTATION STATUS:** All authentication endpoints are fully implemented and ready for use.

---

## 1. Company Sign-up (إنشاء حساب شركة)

### Endpoint
```http
POST /api/auth/company/signup
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Creates a new company account with an owner user. This is the initial registration for a new business.

### Request Body
```json
{
  "company_name": "string",        // اسم الشركة (required, max 255 chars)
  "phone": "string",                // رقم الهاتف (required, format: +963XXXXXXXXX)
  "password": "string",             // كلمة المرور (required, min 8 chars)
  "password_confirm": "string",     // تأكيد كلمة المرور (required, must match password)
  "currency": "string"              // optional, defaults to "SYP" (3-letter code)
}
```

### Request Example
```json
{
  "company_name": "شركة الأمل التجارية",
  "phone": "+963944123456",
  "password": "SecurePass123!",
  "password_confirm": "SecurePass123!",
  "currency": "SYP"
}
```

### Response (Success - 201 Created)
```json
{
  "success": true,
  "message": "تم إنشاء الحساب بنجاح",
  "data": {
    "company": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "slug": "amal-trading",
      "currency": "SYP",
      "is_active": true,
      "created_at": "2026-08-16T10:30:00Z"
    },
    "user": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "phone": "+963944123456",
      "email": null,
      "is_owner": true,
      "is_active": true
    },
    "tokens": {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "فشل إنشاء الحساب",
  "errors": {
    "phone": ["رقم الهاتف مستخدم من قبل"],
    "password": ["كلمة المرور يجب أن تكون 8 أحرف على الأقل"],
    "password_confirm": ["كلمة المرور غير متطابقة"]
  }
}
```

### Validation Rules
- **company_name**: Required, 1-255 characters
- **phone**: Required, must be valid Syrian phone number (+963XXXXXXXXX), unique across the system
- **password**: Required, minimum 8 characters, should contain letters and numbers
- **password_confirm**: Required, must match password
- **currency**: Optional, defaults to "SYP", must be 3-letter ISO code

### Business Logic
1. ✅ Validate all input fields using DRF serializers
2. ✅ Check if phone number is already registered (unique per company)
3. ✅ Hash password using Django's PBKDF2 algorithm with SHA256
4. ✅ Create Company record with auto-generated unique slug
5. ✅ Create SubUser record with `is_owner=True` and no role assignment
6. ✅ Auto-subscribe company to Free trial plan (7 days)
7. ✅ Generate JWT access (1 hour) and refresh (7 days) tokens
8. ✅ Return company details, user details, and tokens
9. ✅ All operations wrapped in database transaction (rollback on error)

---

## 2. Company Sign-in (تسجيل الدخول - الشركات)

### Endpoint
```http
POST /api/auth/company/signin
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Authenticates a company user (owner or staff) and returns access tokens.

### Request Body
```json
{
  "phone": "string",        // رقم الهاتف (required)
  "password": "string"      // كلمة المرور (required)
}
```

### Request Example
```json
{
  "phone": "+963944123456",
  "password": "SecurePass123!"
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم تسجيل الدخول بنجاح",
  "data": {
    "user": {
      "id": 1,
      "name": "أحمد محمد",
      "phone": "+963944123456",
      "email": "ahmad@example.com",
      "is_owner": true,
      "is_active": true,
      "role": null,
      "company": {
        "id": 1,
        "name": "شركة الأمل التجارية",
        "slug": "amal-trading",
        "currency": "SYP",
        "is_active": true
      },
      "permissions": {
        "products": {"can_view": true, "can_action": true},
        "orders": {"can_view": true, "can_action": true},
        "customers": {"can_view": true, "can_action": true},
        "invoices": {"can_view": true, "can_action": true},
        "billing": {"can_view": true, "can_action": true},
        "reps": {"can_view": true, "can_action": true},
        "notifications": {"can_view": true, "can_action": true}
      }
    },
    "tokens": {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

### Response (Error - 401 Unauthorized)
```json
{
  "success": false,
  "message": "رقم الهاتف أو كلمة المرور غير صحيحة",
  "errors": {
    "credentials": ["بيانات الدخول غير صحيحة"]
  }
}
```

### Response (Error - 403 Forbidden - Inactive Account)
```json
{
  "success": false,
  "message": "الحساب غير نشط",
  "errors": {
    "account": ["تم تعطيل هذا الحساب. يرجى التواصل مع الدعم الفني"]
  }
}
```

### Validation Rules
- **phone**: Required, must be valid format
- **password**: Required

### Business Logic
1. ✅ Find SubUser by phone number (indexed for fast lookup)
2. ✅ Verify password using Django's PBKDF2 hasher
3. ✅ Check if user's `is_active` flag is True
4. ✅ Check if company's `is_active` flag is True
5. ✅ Load user's role and permissions (if not owner)
6. ✅ Generate JWT access (1 hour) and refresh (7 days) tokens with user_id, company_id in payload
7. ✅ Return user details with company context and computed permissions
8. ✅ Owners get implicit full access to all modules without role

---

## 3. Sales Rep Sign-in (تسجيل الدخول - مندوبي المبيعات)

### Endpoint
```http
POST /api/auth/rep/signin
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Authenticates a sales representative and returns access tokens.

### Request Body
```json
{
  "phone": "string",        // رقم الهاتف (required)
  "password": "string"      // كلمة المرور (required)
}
```

### Request Example
```json
{
  "phone": "+963955123456",
  "password": "RepPass123!"
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم تسجيل الدخول بنجاح",
  "data": {
    "rep": {
      "id": 1,
      "name": "خالد العلي",
      "phone": "+963955123456",
      "referral_code": "KH-2024-001",
      "is_active": true,
      "company": {
        "id": 1,
        "name": "شركة الأمل التجارية",
        "slug": "amal-trading",
        "currency": "SYP"
      },
      "warehouse": {
        "id": 5,
        "name": "مستودع خالد العلي",
        "owner_type": "rep",
        "owner_id": 1
      }
    },
    "tokens": {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

### Response (Error - 401 Unauthorized)
```json
{
  "success": false,
  "message": "رقم الهاتف أو كلمة المرور غير صحيحة",
  "errors": {
    "credentials": ["بيانات الدخول غير صحيحة"]
  }
}
```

### Response (Error - 403 Forbidden - Inactive Account)
```json
{
  "success": false,
  "message": "الحساب غير نشط",
  "errors": {
    "account": ["تم تعطيل هذا الحساب. يرجى التواصل مع إدارة الشركة"]
  }
}
```

### Validation Rules
- **phone**: Required, must be valid format
- **password**: Required

### Business Logic
1. ✅ Find Rep by phone number (indexed for fast lookup)
2. ✅ Verify password using Django's PBKDF2 hasher
3. ✅ Check if rep's `is_active` flag is True
4. ✅ Check if company's `is_active` flag is True
5. ✅ Load rep's company information
6. ✅ Generate JWT access (1 hour) and refresh (7 days) tokens with rep_id, company_id, user_type='rep' in payload
7. ✅ Return rep details with company context
8. Note: Warehouse information will be added when warehouse models are implemented

---

## 4. Token Refresh

### Endpoint
```http
POST /api/auth/token/refresh
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Generates a new access token using a valid refresh token.

### Request Body
```json
{
  "refresh": "string"      // Refresh token (required)
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "data": {
    "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }
}
```

### Response (Error - 401 Unauthorized)
```json
{
  "success": false,
  "message": "رمز التحديث غير صالح أو منتهي الصلاحية"
}
```

---

## 5. Sign Out

### Endpoint
```http
POST /api/auth/signout
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Invalidates the current refresh token (blacklist mechanism).

### Headers
```
Authorization: Bearer <access_token>
```

### Request Body
```json
{
  "refresh": "string"      // Refresh token to invalidate (required)
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم تسجيل الخروج بنجاح"
}
```

---

## Common Specifications

### JWT Token Structure

#### Access Token Payload (Company User)
```json
{
  "user_id": 1,
  "user_type": "subuser",
  "company_id": 1,
  "is_owner": true,
  "exp": 1692185400,
  "iat": 1692181800
}
```

#### Access Token Payload (Sales Rep)
```json
{
  "user_id": 1,
  "user_type": "rep",
  "company_id": 1,
  "rep_id": 1,
  "exp": 1692185400,
  "iat": 1692181800
}
```

### Token Expiration
- **Access Token**: 1 hour
- **Refresh Token**: 7 days

### Phone Number Format
- Must include country code: `+963` for Syria
- Total length: 13 characters (+963 + 9 digits)
- Example: `+963944123456`

### Password Requirements
- Minimum 8 characters
- Must contain at least one letter
- Must contain at least one number
- Recommended: Include special characters for stronger security

### HTTP Status Codes
- `200 OK`: Successful sign-in or token refresh
- `201 Created`: Successful sign-up
- `400 Bad Request`: Invalid input data
- `401 Unauthorized`: Invalid credentials
- `403 Forbidden`: Account inactive
- `404 Not Found`: Resource not found
- `409 Conflict`: Phone number already exists
- `500 Internal Server Error`: Server error

### Error Response Format
All error responses follow this structure:
```json
{
  "success": false,
  "message": "Human-readable error message in Arabic",
  "errors": {
    "field_name": ["Error description 1", "Error description 2"]
  }
}
```

### CORS Headers
The backend should include appropriate CORS headers for frontend domains:
```
Access-Control-Allow-Origin: https://your-frontend-domain.com
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS
Access-Control-Allow-Headers: Content-Type, Authorization
Access-Control-Allow-Credentials: true
```

---

## Security Considerations

### Password Storage
- All passwords are hashed using Django's PBKDF2 algorithm with SHA256
- Never store or return plain-text passwords

### Rate Limiting
Authentication endpoints should be rate-limited:
- Sign-up: 5 attempts per hour per IP
- Sign-in: 10 attempts per 15 minutes per phone number
- Token refresh: 20 attempts per hour per user

### HTTPS Only
All authentication endpoints must be accessed over HTTPS in production.

### Token Storage (Frontend Guidance)
- Store access token in memory or secure HTTP-only cookie
- Store refresh token in HTTP-only, secure, SameSite cookie
- Never store tokens in localStorage or sessionStorage (XSS vulnerability)

---

## Implementation Notes

### Phone Number Uniqueness
- Company users (SubUser): Phone must be unique **within the company** (constraint: `company_id + phone`)
- Sales reps (Rep): Phone must be unique **within the company** (constraint: `company_id + phone`)
- Different companies CAN have users with the same phone number
- Global phone index exists for fast login lookups across all companies
- During sign-in, the system finds the user by phone first, then validates against their specific company

### Permissions System
- Company owners (`is_owner=True`) have implicit full access to all modules
- Staff members get permissions from their assigned Role
- Permissions are returned in sign-in response to avoid repeated queries

### Multi-tenancy
- Each request must include company context
- JWT tokens include `company_id` to enforce tenant isolation
- All queries must filter by company_id

---

## Testing Recommendations

### Test Cases for Sign-up
1. Valid sign-up with all required fields
2. Duplicate phone number within same company
3. Mismatched password confirmation
4. Invalid phone number format
5. Weak password (less than 8 characters)
6. Missing required fields

### Test Cases for Sign-in
1. Valid credentials
2. Invalid password
3. Non-existent phone number
4. Inactive user account
5. Inactive company account
6. Rate limiting after multiple failed attempts

### Test Cases for Token Management
1. Valid token refresh
2. Expired refresh token
3. Tampered access token
4. Sign-out invalidates refresh token

---

## Contact
For questions or clarifications about these endpoints, contact the backend development team.

**Version**: 1.0  
**Last Updated**: August 16, 2026


---

# Company Onboarding Endpoints

## Overview
After successful registration, new companies must complete a 4-step onboarding process. Based on the UI mockups, this collects company branding, location, description, and business type.

**⚠️ IMPLEMENTATION STATUS:** These endpoints need to be built. The Company model needs additional fields to support onboarding data.

---

## Base URL
All authentication and company endpoints should use:
```
/api/auth/
/api/companies/
```

---

## Onboarding Flow

The onboarding process consists of 4 sequential steps:

1. **الشعار والغلاف** (Logo & Cover) - Upload company branding
2. **الموقع** (Location) - Set company location (governorate and region)
3. **وصف الشركة** (Company Description) - Provide business description
4. **نوع النشاط** (Business Type) - Select business activity type

### Progress Tracking
The backend should track which steps have been completed and return the current step in responses.

---

## 6. Get Onboarding Status

### Endpoint
```http
GET /api/companies/onboarding/status
```

**⚠️ TO BE IMPLEMENTED**

### Description
Returns the current onboarding progress for the authenticated company.

### Headers
```
Authorization: Bearer <access_token>
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "data": {
    "is_completed": false,
    "current_step": 1,
    "completed_steps": [],
    "steps": [
      {
        "step_number": 1,
        "step_name": "logo_cover",
        "step_title": "الشعار والغلاف",
        "is_completed": false
      },
      {
        "step_number": 2,
        "step_name": "location",
        "step_title": "الموقع",
        "is_completed": false
      },
      {
        "step_number": 3,
        "step_name": "description",
        "step_title": "وصف الشركة",
        "is_completed": false
      },
      {
        "step_number": 4,
        "step_name": "business_type",
        "step_title": "نوع النشاط",
        "is_completed": false
      }
    ]
  }
}
```

---

## 7. Step 1: Upload Logo & Cover (الشعار والغلاف)

### Endpoint
```http
POST /api/companies/onboarding/branding
```

**⚠️ TO BE IMPLEMENTED**

### Description
Uploads company logo and cover image. Both images are optional but at least one should be provided for the step to be considered complete.

### Headers
```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

### Request Body (Form Data)
```
logo: File (optional, image file)
cover: File (optional, image file)
```

### Request Details
- **logo**: 
  - Optional
  - Accepted formats: PNG, JPG, JPEG, SVG
  - Recommended size: 512x512px (square)
  - Maximum file size: 2MB
  - Note: "يفضل رفع شعار الشركة على الأقل للمتابعة"

- **cover**: 
  - Optional
  - Accepted formats: PNG, JPG, JPEG
  - Recommended aspect ratio: 16:9 or 21:9
  - Maximum file size: 5MB

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم رفع الصور بنجاح",
  "data": {
    "logo_url": "/media/companies/logos/logo_abc123.png",
    "cover_url": "/media/companies/covers/cover_xyz789.jpg",
    "step_completed": true,
    "next_step": 2
  }
}
```

**Note**: URLs will be relative paths to Django's `MEDIA_URL`. Frontend should prepend the base URL (e.g., `http://localhost:8000/media/companies/logos/logo_abc123.png`).

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "فشل رفع الصور",
  "errors": {
    "logo": ["حجم الملف كبير جداً. الحد الأقصى 2 ميغابايت"],
    "cover": ["نوع الملف غير مدعوم. استخدم PNG أو JPG"]
  }
}
```

### Validation Rules
- At least one file (logo or cover) should be provided
- File size limits: logo (2MB), cover (5MB)
- Supported formats: PNG, JPG, JPEG (SVG for logo only)
- Images should be validated for correct MIME type
- Optional: Image dimensions validation

### Business Logic
1. Validate file uploads (type, size, format)
2. Resize/optimize images if needed (optional enhancement)
3. Save files to `MEDIA_ROOT/companies/logos/` or `MEDIA_ROOT/companies/covers/`
4. Store file paths in Company model's `logo` and `cover` FileField
5. Mark step 1 as completed (`onboarding_step_1_completed = True`)
6. Return relative media URLs for immediate display
7. **Note**: In production, consider serving media files through CDN or object storage (S3, etc.)

### UI Notes
- Show image upload areas with dashed borders (as shown in UI)
- Allow drag-and-drop or click to browse
- Display "اضغط لرفع صورة غلاف الشركة" and "اضغط لرفع شعار الشركة"
- Show note: "إختياري — تظهر صفحة شعار شركتك في المتجر"
- Red text warning: "يفضل رفع شعار الشركة على الأقل للمتابعة"

---

## 8. Step 2: Set Location (الموقع)

### Endpoint
```http
POST /api/companies/onboarding/location
```

**⚠️ TO BE IMPLEMENTED**

### Description
Sets the company's physical location by selecting governorate and region.

### Headers
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request Body
```json
{
  "governorate": "string",    // المحافظة (required)
  "region": "string"          // المنطقة (required)
}
```

### Request Example
```json
{
  "governorate": "دمشق",
  "region": "المزة"
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم حفظ الموقع بنجاح",
  "data": {
    "governorate": "دمشق",
    "region": "المزة",
    "step_completed": true,
    "next_step": 3
  }
}
```

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "فشل حفظ الموقع",
  "errors": {
    "governorate": ["هذا الحقل مطلوب"],
    "region": ["المنطقة المحددة غير صالحة للمحافظة المختارة"]
  }
}
```

### Validation Rules
- **governorate**: Required, must be from predefined list of Syrian governorates
- **region**: Required, must be valid region within selected governorate

### Business Logic
1. Validate governorate from predefined list
2. Validate region belongs to selected governorate
3. Store location data in Company model (add governorate and region fields)
4. Mark step 2 as completed
5. Return confirmation

### Helper Endpoint: Get Governorates & Regions
```http
GET /api/companies/locations
```

**⚠️ TO BE IMPLEMENTED**

#### Response
```json
{
  "success": true,
  "data": {
    "governorates": [
      {
        "id": 1,
        "name": "دمشق",
        "regions": ["المزة", "المالكي", "أبو رمانة", "الميدان", "باب توما"]
      },
      {
        "id": 2,
        "name": "ريف دمشق",
        "regions": ["داريا", "دوما", "جرمانا", "قطنا", "الزبداني"]
      },
      {
        "id": 3,
        "name": "حلب",
        "regions": ["الفرقان", "الأزيزية", "الشهباء", "الحمدانية", "العزيزية"]
      },
      {
        "id": 4,
        "name": "حمص",
        "regions": ["الخالدية", "الوعر", "الإنشاءات", "الزهراء", "الغوطة"]
      },
      {
        "id": 5,
        "name": "حماة",
        "regions": ["المدينة", "الحاضر", "السلمية", "مصياف"]
      },
      {
        "id": 6,
        "name": "اللاذقية",
        "regions": ["الصليبة", "الرمل الجنوبي", "الرمل الشمالي", "الأونيسي"]
      },
      {
        "id": 7,
        "name": "طرطوس",
        "regions": ["المدينة", "الحميدية", "الدريكيش", "بانياس"]
      },
      {
        "id": 8,
        "name": "إدلب",
        "regions": ["المدينة", "جسر الشغور", "معرة النعمان", "أريحا"]
      },
      {
        "id": 9,
        "name": "درعا",
        "regions": ["المدينة", "إزرع", "الصنمين", "نوى"]
      },
      {
        "id": 10,
        "name": "السويداء",
        "regions": ["المدينة", "صلخد", "شهبا", "القريا"]
      },
      {
        "id": 11,
        "name": "القنيطرة",
        "regions": ["المدينة", "خان أرنبة", "الرفيد"]
      },
      {
        "id": 12,
        "name": "دير الزور",
        "regions": ["المدينة", "البوكمال", "الميادين", "العشارة"]
      },
      {
        "id": 13,
        "name": "الرقة",
        "regions": ["المدينة", "تل أبيض", "الثورة"]
      },
      {
        "id": 14,
        "name": "الحسكة",
        "regions": ["المدينة", "القامشلي", "المالكية", "رأس العين"]
      }
    ]
  }
}
```

### UI Notes
- Show title: "أين تقع شركتك؟"
- Subtitle: "حدد المحافظة والمنطقة ليتمكن العملاء من إيجادك"
- Two dropdowns: "إختر المحافظة" and "إختر المنطقة"
- Region dropdown should be populated based on selected governorate
- "العودة" (Back) and "التالي" (Next) buttons

---

## 9. Step 3: Company Description (وصف الشركة)

### Endpoint
```http
POST /api/companies/onboarding/description
```

**⚠️ TO BE IMPLEMENTED**

### Description
Saves a detailed description of the company's business activities.

### Headers
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request Body
```json
{
  "description": "string"    // وصف الشركة (required, max 500 chars)
}
```

### Request Example
```json
{
  "description": "شركة متخصصة لتوزيع المواد الغذائية الجافة والمعلبات لمحلات التجزئة والجملة في دمشق وريفها. نقدم خدمة التوصيل السريع وأسعار منافسة مع ضمان الجودة."
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم حفظ الوصف بنجاح",
  "data": {
    "description": "شركة متخصصة لتوزيع المواد الغذائية...",
    "character_count": 142,
    "step_completed": true,
    "next_step": 4
  }
}
```

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "فشل حفظ الوصف",
  "errors": {
    "description": ["هذا الحقل مطلوب"],
    "description": ["الوصف يجب ألا يتجاوز 500 حرف"]
  }
}
```

### Validation Rules
- **description**: Required, minimum 20 characters, maximum 500 characters
- Should be meaningful text (not just spaces or repeated characters)

### Business Logic
1. Validate description length and content
2. Trim whitespace
3. Store description in Company model
4. Mark step 3 as completed
5. Return confirmation with character count

### UI Notes
- Show title: "عرّفنا على شركتك"
- Subtitle: "أكتب وصفاً دقيقاً لنشاط شركتك ليظهر للعملاء والمناديب"
- Textarea with placeholder example text
- Character counter: "0/500" (bottom right)
- "العودة" (Back) and "التالي" (Next) buttons

---

## 10. Step 4: Business Type (نوع النشاط)

### Endpoint
```http
POST /api/companies/onboarding/business-type
```

**⚠️ TO BE IMPLEMENTED**

### Description
Selects the primary business activity type from predefined categories.

### Headers
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request Body
```json
{
  "business_type": "string"    // نوع النشاط (required)
}
```

### Request Example
```json
{
  "business_type": "food_products"
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم إتمام الإعداد بنجاح! مرحباً بك في تريدرو",
  "data": {
    "business_type": "food_products",
    "business_type_label": "مواد غذائية",
    "onboarding_completed": true,
    "redirect_to": "/dashboard"
  }
}
```

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "فشل حفظ نوع النشاط",
  "errors": {
    "business_type": ["هذا الحقل مطلوب"],
    "business_type": ["نوع النشاط المحدد غير صالح"]
  }
}
```

### Validation Rules
- **business_type**: Required, must be from predefined list of business types

### Business Logic
1. Validate business type from predefined list
2. Store business_type in Company model
3. Mark step 4 as completed
4. Mark entire onboarding process as completed
5. Update company status if needed
6. Return completion confirmation

### Helper Endpoint: Get Business Types
```http
GET /api/companies/business-types
```

**⚠️ TO BE IMPLEMENTED**

#### Response
```json
{
  "success": true,
  "data": {
    "business_types": [
      {
        "id": "food_products",
        "name": "مواد غذائية",
        "icon": "🛒",
        "description": "توزيع وبيع المواد الغذائية"
      },
      {
        "id": "electronics",
        "name": "إلكترونيات",
        "icon": "⭐",
        "description": "أجهزة إلكترونية وتقنية"
      },
      {
        "id": "cosmetics",
        "name": "مستحضرات تجميل",
        "icon": "⭐",
        "description": "منتجات التجميل والعناية"
      },
      {
        "id": "medical_supplies",
        "name": "أدوية ومستلزمات طبية",
        "icon": "✓",
        "description": "المستلزمات والأدوات الطبية"
      },
      {
        "id": "home_tools",
        "name": "أدوات منزلية",
        "icon": "📦",
        "description": "أدوات وأجهزة منزلية"
      },
      {
        "id": "clothing",
        "name": "ألبسة",
        "icon": "👔",
        "description": "ملابس وإكسسوارات"
      }
    ]
  }
}
```

### UI Notes
- Show title: "ما هو نشاط شركتك؟"
- Subtitle: "إختر التصنيف الأقرب لطبيعة عمل شركتك"
- Display 6 business type cards in a 3x2 grid
- Each card shows icon and business type name
- Cards should have visual selection state
- "العودة" (Back) and "إنهاء الإعداد" (Complete Setup) buttons

---

## 11. Skip Onboarding Step

### Endpoint
```http
POST /api/companies/onboarding/skip
```

**⚠️ TO BE IMPLEMENTED**

### Description
Allows skipping certain optional steps during onboarding.

### Headers
```
Authorization: Bearer <access_token>
Content-Type: application/json
```

### Request Body
```json
{
  "step_number": 1    // Step to skip (1-4)
}
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم تخطي الخطوة",
  "data": {
    "skipped_step": 1,
    "next_step": 2
  }
}
```

### Business Logic
- Steps 1 (logo/cover) and 3 (description) can be skipped
- Steps 2 (location) and 4 (business type) should not be skippable
- Mark skipped steps but don't count them as completed

---

## 12. Complete Onboarding

### Endpoint
```http
POST /api/companies/onboarding/complete
```

**⚠️ TO BE IMPLEMENTED**

### Description
Finalizes the onboarding process after all required steps are completed.

### Headers
```
Authorization: Bearer <access_token>
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "مرحباً بك في تريدرو! تم إعداد حسابك بنجاح",
  "data": {
    "onboarding_completed": true,
    "company": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "slug": "amal-trading",
      "logo_url": "https://cdn.tredro.com/companies/1/logo.png",
      "cover_url": "https://cdn.tredro.com/companies/1/cover.jpg",
      "governorate": "دمشق",
      "region": "المزة",
      "description": "شركة متخصصة لتوزيع المواد الغذائية...",
      "business_type": "food_products",
      "currency": "SYP",
      "is_active": true,
      "onboarding_completed_at": "2026-08-16T11:00:00Z"
    },
    "redirect_to": "/dashboard"
  }
}
```

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "لم يتم إكمال جميع الخطوات المطلوبة",
  "errors": {
    "onboarding": ["يجب إكمال الخطوات 2 و 4 قبل المتابعة"]
  }
}
```

### Business Logic
1. Check that all required steps (2 and 4) are completed
2. Update Company model with onboarding_completed flag and timestamp
3. Optionally trigger welcome email or notification
4. Return full company profile

---

## Onboarding Data Model

### Company Model - Onboarding Fields
The Company model already includes these onboarding fields (✅ implemented):

```python
class Company(models.Model):
    # Core fields
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=64, unique=True)
    currency = models.CharField(max_length=3, default="SYP")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    # ✅ Onboarding fields (already in database)
    logo = models.FileField(upload_to="companies/logos/", null=True, blank=True)
    cover = models.FileField(upload_to="companies/covers/", null=True, blank=True)
    governorate = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    description = models.TextField(max_length=500, null=True, blank=True)
    business_type = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        choices=[
            ("food_products", "مواد غذائية"),
            ("electronics", "إلكترونيات"),
            ("cosmetics", "مستحضرات تجميل"),
            ("medical_supplies", "أدوية ومستلزمات طبية"),
            ("home_tools", "أدوات منزلية"),
            ("clothing", "ألبسة"),
        ],
    )
    
    # ✅ Onboarding tracking
    onboarding_completed = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
```

### What Still Needs to Be Built

1. **Step Tracking**: Add boolean fields for individual step completion:
   - `onboarding_step_1_completed` (logo/cover)
   - `onboarding_step_2_completed` (location)
   - `onboarding_step_3_completed` (description)
   - `onboarding_step_4_completed` (business_type)

2. **API Endpoints**: Views and serializers for the 4-step onboarding flow

3. **File Upload Handling**: Configure Django storage and file serving (logo/cover)

4. **Helper Endpoints**: Location data (governorates/regions) and business types

---

## Frontend Flow Recommendations

### 1. Onboarding Entry Point
- After successful sign-up, check `onboarding_completed` flag
- If `false`, redirect to `/onboarding`
- If `true`, redirect to `/dashboard`

### 2. Step Navigation
- Display progress indicator at top (1→2→3→4)
- Show current step number as active
- Show completed steps with checkmark
- Allow navigation back to previous steps
- "التالي" (Next) button advances to next step
- "العودة" (Back) button returns to previous step
- "إنهاء الإعداد" (Complete Setup) on final step

### 3. Step Persistence
- Save data immediately when user clicks "Next"
- Allow users to leave and resume later
- Fetch current progress on page load via `/api/v1/onboarding/status`

### 4. Validation
- Validate inputs client-side before submission
- Show error messages in Arabic below input fields
- Disable "Next" button until required fields are valid

### 5. Image Uploads
- Show image preview after selection
- Display upload progress
- Allow re-upload if user wants to change
- Compress large images client-side before upload

### 6. Completion
- Show success message after final step
- Optionally show confetti or celebration animation
- Auto-redirect to dashboard after 2-3 seconds
- Provide manual "Go to Dashboard" button

---

## Additional Endpoints

### Get Company Profile (with Onboarding Data)
```http
GET /api/companies/profile
```

**⚠️ TO BE IMPLEMENTED**

Returns complete company profile including all onboarding data. This is useful for editing company information later.

---

## Required Database Changes

### Company Model Additions
The following fields need to be added to `apps/companies/models.py` Company model to support onboarding:

```python
class Company(models.Model):
    # Existing fields: name, slug, currency, is_active, created_at, updated_at
    
    # NEW: Branding
    logo = models.FileField(upload_to='companies/logos/', null=True, blank=True)
    cover = models.FileField(upload_to='companies/covers/', null=True, blank=True)
    
    # NEW: Location
    governorate = models.CharField(max_length=100, null=True, blank=True)
    region = models.CharField(max_length=100, null=True, blank=True)
    
    # NEW: Description & Business Type
    description = models.TextField(max_length=500, null=True, blank=True)
    business_type = models.CharField(max_length=50, null=True, blank=True, 
        choices=[
            ('food_products', 'مواد غذائية'),
            ('electronics', 'إلكترونيات'),
            ('cosmetics', 'مستحضرات تجميل'),
            ('medical_supplies', 'أدوية ومستلزمات طبية'),
            ('home_tools', 'أدوات منزلية'),
            ('clothing', 'ألبسة'),
        ])
    
    # NEW: Onboarding Tracking
    onboarding_completed = models.BooleanField(default=False)
    onboarding_completed_at = models.DateTimeField(null=True, blank=True)
```

### Migration Required
```bash
python manage.py makemigrations companies
python manage.py migrate
```

---

## Implementation Notes

### File Storage
- Use Django's `FileField` (already configured in the model with `Product.image`)
- Configure storage backend in settings (local for development, S3/CloudStorage for production)
- Generate unique filenames to prevent overwrites
- Return full URLs in API responses

### Authentication Layer
Per the plan document (Phase 1 - Identity & Access):
- Implement JWT with `actor_type` + `company_id` claims
- SubUser/Rep/Customer are three separate credential tables (existing models)
- Company owner is SubUser with `is_owner=True`
- Tenant-scoping middleware filters by `company_id`

### Syrian Locations Data
The locations data (14 governorates with their regions) should be:
- Stored as static data (JSON file or Python dict)
- Loaded via helper endpoint - no database table needed
- Can be moved to database later if location data needs to be dynamic

### Business Types
Business types are a fixed choice field on Company model (see above)
- No separate table needed at this stage
- Can be refactored to a BusinessType model later if categories become dynamic

---

## Security Notes

### Authorization
- All onboarding endpoints require valid JWT access token
- Only company owners (`is_owner=True`) can complete onboarding
- Verify company_id from JWT matches the company being modified

### File Upload Security
- Validate file types using MIME type checking (not just extensions)
- Scan uploaded files for malware
- Implement file size limits
- Store files with random names to prevent overwriting
- Use CDN or separate storage service (not application server)
- Set proper CORS and content-type headers for images

### Input Sanitization
- Sanitize description text to prevent XSS
- Validate dropdown selections against server-side lists
- Prevent SQL injection in all database queries

---

## Testing Recommendations

### Test Cases for Onboarding
1. Complete onboarding with all steps in order
2. Skip optional steps (logo/cover, description)
3. Navigate back and forth between steps
4. Leave onboarding and resume later
5. Try to access step 4 before completing step 2
6. Upload invalid image files (wrong format, too large)
7. Submit description with special characters and emojis
8. Select non-existent governorate or region
9. Complete onboarding with minimum required data
10. Try to complete onboarding twice

---

**Version**: 1.0  
**Last Updated**: August 16, 2026  
**Status**: Authentication endpoints ✅ IMPLEMENTED | Onboarding endpoints ❌ TO BE IMPLEMENTED

---

## Appendix: Actual Response Formats

### Company Signup Response (Actual Implementation)
Based on implemented serializers in `apps/authentication/views.py`:

```json
{
  "success": true,
  "message": "تم إنشاء الحساب بنجاح",
  "data": {
    "company": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "slug": "amal-trading",
      "currency": "SYP",
      "is_active": true,
      "created_at": "2026-08-16T10:30:00Z",
      "updated_at": "2026-08-16T10:30:00Z",
      "logo": null,
      "cover": null,
      "governorate": null,
      "region": null,
      "description": null,
      "business_type": null,
      "onboarding_completed": false,
      "onboarding_completed_at": null
    },
    "user": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "phone": "+963944123456",
      "email": null,
      "is_owner": true,
      "is_active": true,
      "role": null,
      "company": 1,
      "created_at": "2026-08-16T10:30:00Z",
      "updated_at": "2026-08-16T10:30:00Z"
    },
    "tokens": {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

### Company Signin Response (Actual Implementation)
```json
{
  "success": true,
  "message": "تم تسجيل الدخول بنجاح",
  "data": {
    "user": {
      "id": 1,
      "name": "أحمد محمد",
      "phone": "+963944123456",
      "email": "ahmad@example.com",
      "is_owner": true,
      "is_active": true,
      "role": null,
      "company": 1,
      "created_at": "2026-08-16T10:30:00Z",
      "updated_at": "2026-08-16T10:30:00Z",
      "permissions": {
        "products": {"can_view": true, "can_action": true},
        "orders": {"can_view": true, "can_action": true},
        "customers": {"can_view": true, "can_action": true},
        "invoices": {"can_view": true, "can_action": true},
        "billing": {"can_view": true, "can_action": true},
        "reps": {"can_view": true, "can_action": true},
        "notifications": {"can_view": true, "can_action": true}
      }
    },
    "tokens": {
      "access": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
      "refresh": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
    }
  }
}
```

---

## Key Implementation Details

### Password Hashing (✅ Implemented)
- Algorithm: Django's default PBKDF2 with SHA256
- 600,000 iterations for security
- Salt automatically generated per password
- Implementation: `apps/authentication/utils.py`

### JWT Token Configuration (✅ Implemented)
Uses `djangorestframework-simplejwt`:
- Access token lifetime: 60 minutes
- Refresh token lifetime: 7 days
- Token blacklisting enabled for logout
- Algorithm: HS256 (HMAC with SHA-256)
- Configuration: `config/settings/base.py`

### Database Constraints (✅ Implemented)
```sql
-- SubUser unique constraint
UNIQUE (company_id, phone)

-- Only one owner per company
UNIQUE (company_id) WHERE is_owner = TRUE

-- Indexed fields for performance
INDEX ON subuser(company_id)
INDEX ON subuser(phone)
INDEX ON company(slug)
```

### File Upload Settings (To Be Configured for Onboarding)
```python
# settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# File upload handlers
FILE_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 5242880  # 5MB

# Allowed extensions (to be enforced in views)
ALLOWED_IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.svg']
MAX_LOGO_SIZE = 2 * 1024 * 1024  # 2MB
MAX_COVER_SIZE = 5 * 1024 * 1024  # 5MB
```

### CORS Configuration (Required for Frontend)
```python
# settings.py
CORS_ALLOWED_ORIGINS = [
    "http://localhost:3000",  # React dev server
    "http://localhost:5173",  # Vite dev server
    "https://your-frontend-domain.com",  # Production
]

CORS_ALLOW_CREDENTIALS = True

CORS_ALLOW_HEADERS = [
    'accept',
    'authorization',
    'content-type',
    'origin',
]
```

---

## Frontend Integration Checklist

### Before Development
- [ ] Confirm Django server is running (default: `http://localhost:8000`)
- [ ] Test `/api/health/` endpoint to verify connectivity
- [ ] Configure CORS in Django for your frontend origin
- [ ] Set up environment variables for API base URL

### Registration Flow ✅
- [ ] Create signup form with phone number formatting
- [ ] Validate phone number format (+963XXXXXXXXX) client-side
- [ ] Validate password match client-side
- [ ] Store tokens securely (HttpOnly cookies or secure memory)
- [ ] Redirect based on `onboarding_completed` flag

### Login Flow ✅
- [ ] Create login form for company users
- [ ] Create separate login form for sales reps
- [ ] Handle error messages in Arabic
- [ ] Implement "Remember Me" functionality (optional)
- [ ] Store user context (company info, permissions) in state

### Token Management ✅
- [ ] Implement automatic token refresh before expiry
- [ ] Handle 401 errors with token refresh retry
- [ ] Clear tokens on logout
- [ ] Handle token expiry during inactivity

### Onboarding Flow ❌ (Pending Backend)
- [ ] Create 4-step wizard component
- [ ] Implement progress indicator
- [ ] Add image upload with preview
- [ ] Fetch and display location options
- [ ] Fetch and display business types
- [ ] Save progress after each step
- [ ] Allow back navigation with preserved data

---

## Testing Endpoints with cURL

### Test Company Signup
```bash
curl -X POST http://localhost:8000/api/auth/company/signup \
  -H "Content-Type: application/json" \
  -d '{
    "company_name": "شركة الأمل التجارية",
    "phone": "+963944123456",
    "password": "SecurePass123!",
    "password_confirm": "SecurePass123!",
    "currency": "SYP"
  }'
```

### Test Company Signin
```bash
curl -X POST http://localhost:8000/api/auth/company/signin \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+963944123456",
    "password": "SecurePass123!"
  }'
```

### Test Rep Signin
```bash
curl -X POST http://localhost:8000/api/auth/rep/signin \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "+963955123456",
    "password": "RepPass123!"
  }'
```

### Test Token Refresh
```bash
curl -X POST http://localhost:8000/api/auth/token/refresh \
  -H "Content-Type: application/json" \
  -d '{
    "refresh": "YOUR_REFRESH_TOKEN_HERE"
  }'
```

### Test Signout
```bash
curl -X POST http://localhost:8000/api/auth/signout \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -d '{
    "refresh": "YOUR_REFRESH_TOKEN_HERE"
  }'
```

---

## Support & Questions

### For Backend Implementation
- Check authentication views: `apps/authentication/views.py`
- Check serializers: `apps/authentication/serializers.py`
- Check models: `apps/companies/models.py`, `apps/reps/models.py`
- Review utility functions: `apps/authentication/utils.py`

### For Frontend Integration
- All auth endpoints are at: `/api/auth/*`
- Onboarding endpoints (when ready) will be at: `/api/companies/onboarding/*`
- Helper endpoints will be at: `/api/companies/locations` and `/api/companies/business-types`

### Common Issues & Solutions

**Issue: CORS errors**
- Ensure frontend origin is in `CORS_ALLOWED_ORIGINS`
- Check that credentials are included in requests
- Verify `Authorization` header format: `Bearer <token>`

**Issue: 401 Unauthorized**
- Check token is not expired (60 min for access token)
- Verify `Authorization: Bearer <token>` header is present
- Try refreshing the token with `/api/auth/token/refresh`

**Issue: Phone number already exists**
- Phone numbers must be unique within a company
- Different companies can reuse the same phone number
- Error returns 400 with field-level errors

**Issue: Inactive account**
- Check `is_active` flag on SubUser/Rep
- Check `is_active` flag on Company
- Returns 403 with descriptive Arabic message

---

## Next Steps for Backend Implementation

### ✅ Completed (Phase 1: Authentication)
1. ✅ Installed Django REST Framework and Simple JWT
2. ✅ Created authentication app structure
3. ✅ Implemented all authentication endpoints:
   - ✅ POST `/api/auth/company/signup`
   - ✅ POST `/api/auth/company/signin`
   - ✅ POST `/api/auth/rep/signin`
   - ✅ POST `/api/auth/token/refresh`
   - ✅ POST `/api/auth/signout`
4. ✅ Added JWT configuration to settings
5. ✅ Created password hashing and token generation utilities
6. ✅ Added Company model fields for onboarding

### 🔄 Next: Phase 2 - Onboarding Endpoints

#### 2.1 Create Onboarding Views & Serializers
```bash
# In apps/companies/
# Create: views.py (add onboarding views)
# Create: serializers.py (add onboarding serializers)
# Update: urls.py (add onboarding routes)
```

#### 2.2 Implement Onboarding Endpoints
1. ❌ GET `/api/companies/onboarding/status` - Get current progress
2. ❌ POST `/api/companies/onboarding/branding` - Upload logo/cover (multipart/form-data)
3. ❌ POST `/api/companies/onboarding/location` - Save governorate/region
4. ❌ POST `/api/companies/onboarding/description` - Save company description
5. ❌ POST `/api/companies/onboarding/business-type` - Select business type
6. ❌ POST `/api/companies/onboarding/complete` - Finalize onboarding

#### 2.3 Implement Helper Endpoints
1. ❌ GET `/api/companies/locations` - Return Syrian governorates with regions
2. ❌ GET `/api/companies/business-types` - Return business type choices

#### 2.4 Add Step Tracking to Company Model
Add migration to include step completion tracking:
```python
# In apps/companies/migrations/000X_add_onboarding_steps.py
onboarding_step_1_completed = models.BooleanField(default=False)  # logo/cover
onboarding_step_2_completed = models.BooleanField(default=False)  # location
onboarding_step_3_completed = models.BooleanField(default=False)  # description
onboarding_step_4_completed = models.BooleanField(default=False)  # business_type
```

#### 2.5 Configure File Storage & Media Serving
```python
# settings.py
MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# urls.py (development only)
from django.conf import settings
from django.conf.urls.static import static
urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

#### 2.6 Create Location Data
Create `apps/companies/data/locations.py` with Syrian location data (see helper endpoint spec)

### 🔜 Phase 3: Testing & Documentation
1. ❌ Write unit tests for onboarding flow
2. ❌ Test file upload security and validation
3. ❌ Test step completion logic
4. ❌ Update Postman/Thunder Client collection
5. ❌ Frontend integration testing

---


---

# Simplified Company Onboarding API (IMPLEMENTED)

## Overview
The company onboarding has been implemented with a simplified approach:
- **Single endpoint** for submitting all onboarding data
- **All fields are optional** - users can skip onboarding entirely
- **Frontend collects data** across multiple steps, then submits all at once
- **Can be completed later** via company profile settings

This design gives maximum flexibility to users while simplifying the backend.

---

## 1. Get Onboarding Status

### Endpoint
```http
GET /api/companies/onboarding/status
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Returns the current company's onboarding status and all company data.

### Headers
```
Authorization: Bearer <access_token>
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "data": {
    "onboarding_completed": false,
    "company": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "slug": "amal-trading",
      "currency": "SYP",
      "is_active": true,
      "logo": null,
      "cover": null,
      "governorate": null,
      "region": null,
      "description": null,
      "business_type": null,
      "onboarding_completed": false,
      "created_at": "2026-08-16T10:30:00Z"
    }
  }
}
```

### Response (Error - 403 Forbidden)
```json
{
  "success": false,
  "message": "لم يتم العثور على معلومات الشركة",
  "errors": {
    "company": ["يجب أن تكون مسجلاً كمستخدم شركة"]
  }
}
```

### Business Logic
1. Extract company_id from JWT token (via middleware)
2. Load company record
3. Return onboarding status and company data
4. Used by frontend to check if onboarding is needed

---

## 2. Complete Company Onboarding

### Endpoint
```http
POST /api/companies/onboarding
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Completes company onboarding in a single request. All fields are optional - the user can provide as much or as little information as they want. This endpoint marks onboarding as completed regardless of which fields are provided.

### Headers
```
Authorization: Bearer <access_token>
Content-Type: multipart/form-data
```

### Request Body (Form Data)
All fields are optional:
```
logo: File (optional, image file - PNG, JPG, JPEG, SVG)
cover: File (optional, image file - PNG, JPG, JPEG)
governorate: string (optional, e.g., "دمشق")
region: string (optional, e.g., "المزة")
description: string (optional, max 500 chars)
business_type: string (optional, e.g., "food_products")
```

### Request Examples

**Example 1: Complete onboarding with all fields**
```
logo: [File upload]
cover: [File upload]
governorate: "دمشق"
region: "المزة"
description: "شركة متخصصة لتوزيع المواد الغذائية"
business_type: "food_products"
```

**Example 2: Skip onboarding (submit empty request)**
```
(no fields provided)
```

**Example 3: Partial data**
```
governorate: "حلب"
region: "الشهباء"
business_type: "electronics"
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "message": "تم حفظ بيانات الشركة بنجاح",
  "data": {
    "company": {
      "id": 1,
      "name": "شركة الأمل التجارية",
      "slug": "amal-trading",
      "currency": "SYP",
      "is_active": true,
      "logo": "/media/companies/logos/logo_abc123.png",
      "cover": "/media/companies/covers/cover_xyz789.jpg",
      "governorate": "دمشق",
      "region": "المزة",
      "description": "شركة متخصصة لتوزيع المواد الغذائية",
      "business_type": "food_products",
      "onboarding_completed": true,
      "created_at": "2026-08-16T10:30:00Z"
    }
  }
}
```

### Response (Error - 400 Bad Request)
```json
{
  "success": false,
  "message": "بيانات غير صالحة",
  "errors": {
    "logo": ["حجم الملف كبير جداً. الحد الأقصى 2 ميغابايت"],
    "description": ["الوصف يجب ألا يتجاوز 500 حرف"],
    "business_type": ["نوع النشاط المحدد غير صالح"]
  }
}
```

### Validation Rules
All fields are optional, but when provided:
- **logo**: Image file (PNG, JPG, JPEG, SVG), max 2MB
- **cover**: Image file (PNG, JPG, JPEG), max 5MB
- **governorate**: Valid Syrian governorate name
- **region**: Valid region name (should match governorate)
- **description**: Text, max 500 characters
- **business_type**: One of: `food_products`, `electronics`, `cosmetics`, `medical_supplies`, `home_tools`, `clothing`

### Business Logic
1. Extract company_id from authenticated user's JWT token
2. Load company record
3. Validate only the fields that were provided
4. Update company with provided data
5. Mark `onboarding_completed = True` (even if no fields provided)
6. Set `onboarding_completed_at` timestamp
7. Save company record
8. Return updated company data

**Key Design Decision**: Marking onboarding as completed happens regardless of whether any fields were provided. This allows users to skip onboarding entirely and fill in company details later through the profile/settings page.

---

## 3. Get Locations (Governorates & Regions)

### Endpoint
```http
GET /api/companies/locations
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Returns a list of all Syrian governorates with their regions.

### Headers
```
Authorization: Bearer <access_token>
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "data": {
    "locations": [
      {
        "governorate": "دمشق",
        "regions": [
          "المزة",
          "المالكي",
          "أبو رمانة",
          "القصاع",
          "المهاجرين",
          "الشاغور",
          "ساروجة",
          "ركن الدين",
          "القابون",
          "برزة",
          "دمر",
          "كفرسوسة"
        ]
      },
      {
        "governorate": "ريف دمشق",
        "regions": [
          "دوما",
          "الزبداني",
          "يبرود",
          "النبك",
          "القطيفة",
          "التل",
          "صيدنايا",
          "جرمانا",
          "عربين",
          "حرستا",
          "داريا",
          "المليحة",
          "القدم"
        ]
      },
      {
        "governorate": "حلب",
        "regions": [
          "حلب المدينة",
          "منبج",
          "عفرين",
          "جرابلس",
          "إعزاز",
          "الباب",
          "عين العرب",
          "السفيرة",
          "اعزاز"
        ]
      }
    ]
  }
}
```

### Business Logic
- Returns hardcoded list of Syrian governorates and regions
- No database queries required
- Can be cached on frontend for performance

---

## 4. Get Business Types

### Endpoint
```http
GET /api/companies/business-types
```

**✅ IMPLEMENTED** - Ready for frontend integration

### Description
Returns a list of available business type options.

### Headers
```
Authorization: Bearer <access_token>
```

### Response (Success - 200 OK)
```json
{
  "success": true,
  "data": {
    "business_types": [
      {
        "value": "food_products",
        "label": "مواد غذائية"
      },
      {
        "value": "electronics",
        "label": "إلكترونيات"
      },
      {
        "value": "cosmetics",
        "label": "مستحضرات تجميل"
      },
      {
        "value": "medical_supplies",
        "label": "أدوية ومستلزمات طبية"
      },
      {
        "value": "home_tools",
        "label": "أدوات منزلية"
      },
      {
        "value": "clothing",
        "label": "ألبسة"
      }
    ]
  }
}
```

### Business Logic
- Returns the business type choices from Company model
- No database queries required
- Can be cached on frontend for performance

---

## Frontend Integration Guide

### Recommended Flow

1. **After Signup/Login**: Check `company.onboarding_completed` in the response
   
2. **If not completed**: 
   - Show multi-step onboarding UI (4 steps as designed)
   - Collect data in frontend state (don't submit each step)
   - On final step or "Skip" button, call `POST /api/companies/onboarding` with collected data

3. **Onboarding Steps** (Frontend only, no backend calls per step):
   - **Step 1**: Collect logo/cover files
   - **Step 2**: Call `GET /api/companies/locations`, let user select governorate/region
   - **Step 3**: Collect description text
   - **Step 4**: Call `GET /api/companies/business-types`, let user select type
   - **Final**: Submit all data at once via `POST /api/companies/onboarding`

4. **Skip Onboarding**: 
   - Call `POST /api/companies/onboarding` with empty body
   - User can complete profile later

5. **Edit Later**:
   - Same endpoint (`POST /api/companies/onboarding`) can be used to update company profile
   - Or create a separate `PATCH /api/companies/profile` endpoint for profile updates

### Example Frontend State Management

```javascript
// Onboarding state
const [onboardingData, setOnboardingData] = useState({
  logo: null,
  cover: null,
  governorate: '',
  region: '',
  description: '',
  business_type: ''
});

// On final step or skip
const completeOnboarding = async () => {
  const formData = new FormData();
  
  // Only append fields that have values
  if (onboardingData.logo) formData.append('logo', onboardingData.logo);
  if (onboardingData.cover) formData.append('cover', onboardingData.cover);
  if (onboardingData.governorate) formData.append('governorate', onboardingData.governorate);
  if (onboardingData.region) formData.append('region', onboardingData.region);
  if (onboardingData.description) formData.append('description', onboardingData.description);
  if (onboardingData.business_type) formData.append('business_type', onboardingData.business_type);
  
  const response = await fetch('/api/companies/onboarding', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`
    },
    body: formData
  });
  
  // Redirect to dashboard
  navigate('/dashboard');
};
```

---

## Benefits of This Approach

1. **Flexible**: Users can skip onboarding and fill details later
2. **Simple Backend**: One endpoint instead of four
3. **Better UX**: No failed partial states, everything is optional
4. **Idempotent**: Can call the endpoint multiple times to update data
5. **Frontend Control**: Frontend manages the multi-step UI without backend dependencies
6. **Performance**: Single request instead of four sequential requests

---

**Version**: 2.0 (Simplified Onboarding)  
**Last Updated**: August 16, 2026
