# Customer Management API Documentation

## Overview
Complete API documentation for customer management. Includes both customer self-registration and company-managed customer CRUD operations. Customers are global entities that can interact with multiple companies.

---

## Table of Contents
1. [Customer Authentication](#customer-authentication)
   - [Customer Signup](#1-customer-signup-self-registration)
   - [Customer Signin](#2-customer-signin)
2. [Company-Managed Customer Operations](#company-managed-customer-operations)
   - [List Customers](#3-list-customers)
   - [Create Customer](#4-create-customer-by-company)
   - [Get Customer Details](#5-get-customer-details)
   - [Update Customer](#6-update-customer-full-update)
   - [Partial Update Customer](#7-partial-update-customer)
   - [Deactivate Customer](#8-deactivate-customer)
   - [Assign Rep to Customer](#9-assign-rep-to-customer)

---

## Customer Authentication

### 1. Customer Signup (Self-Registration)
Customer self-registration with optional referral code for auto-assignment to a rep.

**Endpoint:** `POST /api/auth/customer/signup`

**Authentication:** Not required

**Request Body:**
```json
{
  "name": "محمد أحمد",
  "phone": "0912345678",
  "password": "SecurePass123",
  "email": "customer@example.com",
  "referral_code": "REF123",
  "latitude": 33.5138,
  "longitude": 36.2765
}
```

**Field Requirements:**
- `name` (required): Customer's full name (max 255 chars)
- `phone` (required): Phone number (must be unique globally)
- `password` (required): Password (min 6 characters)
- `email` (optional): Customer email address
- `referral_code` (optional): Rep's referral code for auto-assignment
- `latitude` (optional): GPS latitude for first visit location
- `longitude` (optional): GPS longitude (required if latitude provided)

**Success Response (201 Created):**
```json
{
  "success": true,
  "message": "تم إنشاء الحساب بنجاح",
  "data": {
    "customer": {
      "id": 1,
      "name": "محمد أحمد",
      "phone": "+963912345678",
      "email": "customer@example.com",
      "assigned_rep": {
        "id": 5,
        "name": "أحمد محمد",
        "phone": "+963955123456"
      },
      "has_location": true
    },
    "tokens": {
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "success": false,
  "message": "فشل إنشاء الحساب",
  "errors": {
    "phone": ["رقم الهاتف مستخدم من قبل"],
    "referral_code": ["كود الإحالة غير صحيح أو غير نشط"],
    "location": ["يجب تقديم خطوط الطول والعرض معاً أو تركهما فارغين"]
  }
}
```

---

### 2. Customer Signin
Authenticate a customer and receive JWT tokens.

**Endpoint:** `POST /api/auth/customer/signin`

**Authentication:** Not required

**Request Body:**
```json
{
  "phone": "0912345678",
  "password": "SecurePass123"
}
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تسجيل الدخول بنجاح",
  "data": {
    "customer": {
      "id": 1,
      "name": "محمد أحمد",
      "phone": "+963912345678",
      "email": "customer@example.com",
      "assigned_rep": {
        "id": 5,
        "name": "أحمد محمد",
        "phone": "+963955123456"
      },
      "referral_code_used": "REF123",
      "has_location": true,
      "is_active": true
    },
    "tokens": {
      "access": "eyJ0eXAiOiJKV1QiLCJhbGc...",
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
    }
  }
}
```

**Error Responses:**

**401 Unauthorized - Invalid Credentials:**
```json
{
  "success": false,
  "message": "رقم الهاتف أو كلمة المرور غير صحيحة",
  "errors": {
    "credentials": ["بيانات الدخول غير صحيحة"]
  }
}
```

**403 Forbidden - Inactive Account:**
```json
{
  "success": false,
  "message": "الحساب غير نشط",
  "errors": {
    "account": ["تم تعطيل هذا الحساب. يرجى التواصل مع الدعم الفني"]
  }
}
```

---

## Company-Managed Customer Operations

All endpoints below require authentication with a company JWT token.

**Base URL:** `/api/companies/customers`

**Authentication:** Required (Company SubUser or Owner)

---

### 3. List Customers
Get a list of all customers with optional filtering.

**Endpoint:** `GET /api/companies/customers`

**Query Parameters:**
- `is_active` (optional): Filter by active status (`true` or `false`)
- `my_company_only` (optional): Filter customers assigned to company's reps (`true`)

**Example Requests:**
- All customers: `GET /api/companies/customers`
- Active only: `GET /api/companies/customers?is_active=true`
- Company's customers: `GET /api/companies/customers?my_company_only=true`

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "customers": [
      {
        "id": 1,
        "name": "محمد أحمد",
        "phone": "+963912345678",
        "email": "customer@example.com",
        "assigned_rep_name": "أحمد محمد",
        "referral_code_used": "REF123",
        "is_active": true,
        "created_at": "2024-01-15T10:30:00Z"
      },
      {
        "id": 2,
        "name": "فاطمة علي",
        "phone": "+963923456789",
        "email": null,
        "assigned_rep_name": null,
        "referral_code_used": null,
        "is_active": true,
        "created_at": "2024-01-16T14:20:00Z"
      }
    ]
  }
}
```

---

### 4. Create Customer (by Company)
Manually create a new customer.

**Endpoint:** `POST /api/companies/customers`

**Request Body:**
```json
{
  "name": "محمد أحمد",
  "phone": "0912345678",
  "password": "TempPass123",
  "email": "customer@example.com",
  "assigned_rep": 5,
  "latitude": 33.5138,
  "longitude": 36.2765,
  "is_active": true
}
```

**Field Requirements:**
- `name` (required): Customer's full name
- `phone` (required): Phone number (globally unique)
- `password` (required): Initial password (min 6 chars)
- `email` (optional): Customer email
- `assigned_rep` (optional): Rep ID (must belong to this company)
- `latitude` (optional): GPS latitude
- `longitude` (optional): GPS longitude
- `is_active` (optional): Active status (default: true)

**Success Response (201 Created):**
```json
{
  "success": true,
  "message": "تم إضافة العميل بنجاح",
  "data": {
    "customer": {
      "id": 3,
      "name": "محمد أحمد",
      "phone": "+963912345678",
      "email": "customer@example.com",
      "assigned_rep": 5,
      "assigned_rep_name": "أحمد محمد",
      "assigned_rep_phone": "+963955123456",
      "latitude": "33.513800",
      "longitude": "36.276500",
      "is_active": true,
      "created_at": "2024-01-17T09:15:00Z",
      "updated_at": "2024-01-17T09:15:00Z"
    }
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "success": false,
  "message": "بيانات غير صالحة",
  "errors": {
    "phone": ["رقم الهاتف مستخدم من قبل"],
    "assigned_rep": ["المندوب لا ينتمي لهذه الشركة"]
  }
}
```

---

### 5. Get Customer Details
Retrieve details of a specific customer.

**Endpoint:** `GET /api/companies/customers/{id}`

**URL Parameters:**
- `id` (integer): Customer ID

**Success Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "customer": {
      "id": 1,
      "name": "محمد أحمد",
      "phone": "+963912345678",
      "email": "customer@example.com",
      "assigned_rep": 5,
      "assigned_rep_name": "أحمد محمد",
      "assigned_rep_phone": "+963955123456",
      "latitude": "33.513800",
      "longitude": "36.276500",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-15T10:30:00Z"
    }
  }
}
```

**Error Response (404 Not Found):**
```json
{
  "success": false,
  "message": "Not found."
}
```

---

### 6. Update Customer (Full Update)
Replace all fields of a customer.

**Endpoint:** `PUT /api/companies/customers/{id}`

**Request Body:**
```json
{
  "name": "محمد أحمد المحدث",
  "phone": "+963912345678",
  "email": "newemail@example.com",
  "password": "NewPass456",
  "assigned_rep": 5,
  "latitude": 33.5138,
  "longitude": 36.2765,
  "is_active": true
}
```

**Note:** Password is optional - only include if changing.

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تحديث بيانات العميل بنجاح",
  "data": {
    "customer": {
      "id": 1,
      "name": "محمد أحمد المحدث",
      "phone": "+963912345678",
      "email": "newemail@example.com",
      "assigned_rep": 5,
      "assigned_rep_name": "أحمد محمد",
      "assigned_rep_phone": "+963955123456",
      "latitude": "33.513800",
      "longitude": "36.276500",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-17T11:45:00Z"
    }
  }
}
```

---

### 7. Partial Update Customer
Update specific fields of a customer.

**Endpoint:** `PATCH /api/companies/customers/{id}`

**Request Body (any combination):**
```json
{
  "email": "updated@example.com",
  "is_active": false
}
```

Or update assigned rep:
```json
{
  "assigned_rep": 7
}
```

Or update password only:
```json
{
  "password": "NewSecurePass789"
}
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تحديث بيانات العميل بنجاح",
  "data": {
    "customer": {
      "id": 1,
      "name": "محمد أحمد",
      "phone": "+963912345678",
      "email": "updated@example.com",
      "assigned_rep": 5,
      "assigned_rep_name": "أحمد محمد",
      "assigned_rep_phone": "+963955123456",
      "latitude": "33.513800",
      "longitude": "36.276500",
      "is_active": false,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-17T12:00:00Z"
    }
  }
}
```

---

### 8. Deactivate Customer
Soft delete - deactivate customer instead of permanent deletion.

**Endpoint:** `DELETE /api/companies/customers/{id}`

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تعطيل العميل بنجاح"
}
```

**Note:** This sets `is_active = false` rather than deleting the record. Customer data and order history are preserved.

---

### 9. Assign Rep to Customer
Assign a customer to one of the company's reps.

**Endpoint:** `POST /api/companies/customers/{id}/assign-rep`

**Request Body:**
```json
{
  "rep_id": 5
}
```

**Success Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تعيين المندوب للعميل بنجاح",
  "data": {
    "customer": {
      "id": 1,
      "name": "محمد أحمد",
      "phone": "+963912345678",
      "email": "customer@example.com",
      "assigned_rep": 5,
      "assigned_rep_name": "أحمد محمد",
      "assigned_rep_phone": "+963955123456",
      "latitude": "33.513800",
      "longitude": "36.276500",
      "is_active": true,
      "created_at": "2024-01-15T10:30:00Z",
      "updated_at": "2024-01-17T13:30:00Z"
    }
  }
}
```

**Error Responses:**

**400 Bad Request - Missing rep_id:**
```json
{
  "success": false,
  "message": "معرف المندوب مطلوب",
  "errors": {
    "rep_id": ["هذا الحقل مطلوب"]
  }
}
```

**404 Not Found - Invalid Rep:**
```json
{
  "success": false,
  "message": "المندوب غير موجود",
  "errors": {
    "rep_id": ["المندوب غير موجود أو غير نشط في هذه الشركة"]
  }
}
```

---

## Data Model

### Customer Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique identifier (read-only) |
| `name` | string | Customer's full name (max 255 chars) |
| `phone` | string | Phone number (max 32 chars, globally unique) |
| `email` | string/null | Email address (optional) |
| `password` | string | Hashed password (write-only) |
| `assigned_rep` | integer/null | ID of assigned rep (optional) |
| `assigned_rep_name` | string/null | Name of assigned rep (read-only) |
| `assigned_rep_phone` | string/null | Phone of assigned rep (read-only) |
| `referral_code_used` | string/null | Original referral code from signup (read-only, immutable) |
| `latitude` | decimal/null | GPS latitude (9 digits, 6 decimals) |
| `longitude` | decimal/null | GPS longitude (9 digits, 6 decimals) |
| `is_active` | boolean | Active status |
| `created_at` | datetime | Creation timestamp (read-only) |
| `updated_at` | datetime | Last update timestamp (read-only) |

---

## Error Codes

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 201 | Created successfully |
| 400 | Bad request (validation errors) |
| 401 | Unauthorized (missing or invalid token) |
| 403 | Forbidden (inactive account) |
| 404 | Customer or rep not found |
| 500 | Internal server error |

---

## Validation Rules

### Phone Number
- Must be in Syrian format: +963XXXXXXXXX
- Auto-normalized from various input formats (0944..., 963..., +963...)
- Globally unique across all customers
- Required for all operations

### Password
- Minimum 6 characters
- Automatically hashed with Django's PBKDF2
- Never returned in responses (write-only)
- Optional on updates

### Email
- Valid email format if provided
- Optional field
- Can be null/blank

### GPS Coordinates
- Both latitude and longitude must be provided together
- Latitude: decimal with max 9 digits, 6 decimal places
- Longitude: decimal with max 9 digits, 6 decimal places
- Optional - used for first-visit location tracking

### Assigned Rep
- Must belong to the requesting company
- Must be active (`is_active = true`)
- Optional - customers can exist without assignment

### Referral Code Tracking
- `referral_code_used` is **immutable** - stored only during signup
- Used for tracking and analytics (who brought in the customer)
- Separate from `assigned_rep` which can be changed by company admin
- Enables proper attribution even if rep assignment changes later

---

## Code Examples

### Customer Self-Registration with cURL
```bash
curl -X POST https://your-domain.com/api/auth/customer/signup \
  -H "Content-Type: application/json" \
  -d '{
    "name": "محمد أحمد",
    "phone": "0912345678",
    "password": "SecurePass123",
    "referral_code": "REF123",
    "latitude": 33.5138,
    "longitude": 36.2765
  }'
```

### Customer Signin with JavaScript (Fetch)
```javascript
fetch('https://your-domain.com/api/auth/customer/signin', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    phone: '0912345678',
    password: 'SecurePass123'
  })
})
.then(response => response.json())
.then(data => {
  // Store tokens
  localStorage.setItem('access_token', data.data.tokens.access);
  localStorage.setItem('refresh_token', data.data.tokens.refresh);
  console.log('Logged in:', data.data.customer);
});
```

### List Company's Customers with Axios
```javascript
axios.get('https://your-domain.com/api/companies/customers', {
  headers: {
    'Authorization': `Bearer ${companyAccessToken}`
  },
  params: {
    my_company_only: true,
    is_active: true
  }
})
.then(response => {
  console.log('Customers:', response.data.data.customers);
});
```

### Create Customer Manually
```javascript
axios.post('https://your-domain.com/api/companies/customers', {
  name: 'محمد أحمد',
  phone: '0912345678',
  password: 'TempPass123',
  email: 'customer@example.com',
  assigned_rep: 5
}, {
  headers: {
    'Authorization': `Bearer ${companyAccessToken}`,
    'Content-Type': 'application/json'
  }
})
.then(response => console.log('Created:', response.data.data.customer));
```

### Assign Rep to Customer
```javascript
axios.post('https://your-domain.com/api/companies/customers/1/assign-rep', {
  rep_id: 5
}, {
  headers: {
    'Authorization': `Bearer ${companyAccessToken}`,
    'Content-Type': 'application/json'
  }
})
.then(response => console.log('Assigned:', response.data.data.customer));
```

---

## Business Logic Notes

1. **Global Entity**: Customers are global - they can register once and interact with any company. They're not tenant-scoped like products or reps.

2. **Rep Assignment**: 
   - During signup: automatically assigned if valid `referral_code` provided
   - By company: manually assigned via update or dedicated assign-rep endpoint
   - A customer can only be assigned to reps from a single company at a time

3. **Referral Code Tracking**:
   - `referral_code_used` is stored **immutably** during signup
   - Used for tracking which rep brought in the customer
   - Remains unchanged even if `assigned_rep` is later modified by admin
   - Enables proper commission/attribution tracking

4. **GPS Location**: 
   - Captured during first signup for location tracking
   - Both coordinates required together
   - Used for delivery/logistics optimization

5. **Soft Delete**: 
   - Customers are deactivated, not deleted
   - Preserves order history and data integrity
   - Can be reactivated by setting `is_active = true`

6. **Password Management**:
   - Hashed with Django's PBKDF2 algorithm
   - Never exposed in API responses
   - Can be updated by both customer and company

7. **Phone Normalization**:
   - Accepts multiple formats (0944..., 963..., +963...)
   - Stored in normalized format: +963XXXXXXXXX
   - Used as primary identifier for login

---

## Related Endpoints

- [Rep Management API](./reps-api.md) - For managing sales representatives
- [Company Onboarding API](./onboarding-api.md) - For company setup
- [Authentication API](./auth-api.md) - For token management

---

## Support

For questions or issues with these endpoints, contact the development team or refer to the main API documentation.
