# Frontend API Documentation

## Table of Contents
- [Work Days Management](#work-days-management)
  - [Company Endpoints](#company-endpoints)
  - [Rep Endpoints](#rep-endpoints)
- [Customer Management](#customer-management)
- [Authentication](#authentication)

---

## Work Days Management

Work days management allows companies to assign reps to customers with specific work schedules. Reps can also update customer locations and their assigned work days.

### Data Structures

#### Work Days Format
Work days are represented as an array of day names (lowercase):

```json
["sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday"]
```

**Supported Languages:**
- English: `"sunday"`, `"monday"`, `"tuesday"`, `"wednesday"`, `"thursday"`, `"friday"`, `"saturday"`
- Arabic: `"الأحد"`, `"الإثنين"`, `"الثلاثاء"`, `"الأربعاء"`, `"الخميس"`, `"الجمعة"`, `"السبت"`

#### Assignment Model
Each customer-rep assignment has:
- `rep_id`: The assigned rep's ID
- `work_days`: Array of days (empty array means use rep's default work days)

---

## Company Endpoints

These endpoints are for company owners and staff to manage customer-rep assignments.

### 1. Assign Reps to Customer (with Work Days)

Assign one or more reps to a customer with specific work days for each assignment.

**Endpoint:** `POST /api/companies/customers/{customer_id}/assign-reps`

**Authentication:** Required (Company SubUser token)

**Request Body:**

**New Format (Recommended):**
```json
{
  "assignments": [
    {
      "rep_id": 123,
      "work_days": ["sunday", "monday", "tuesday"]
    },
    {
      "rep_id": 456,
      "work_days": []  // Empty means use rep's default work_days
    }
  ]
}
```

**Legacy Format (Backward Compatible):**
```json
{
  "rep_ids": [123, 456]  // All assignments will use rep's default work_days
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تعيين المندوبين للعميل بنجاح",
  "data": {
    "customer": {
      "id": 789,
      "name": "أحمد محمد",
      "phone": "+963991234567",
      "email": "ahmad@example.com",
      "assigned_reps_count": 2,
      "assigned_reps_details": [
        {
          "id": 123,
          "name": "مندوب 1",
          "phone": "+963992222222",
          "company_id": 1,
          "referral_code": "REP123",
          "work_days": ["sunday", "monday", "tuesday"]
        },
        {
          "id": 456,
          "name": "مندوب 2",
          "phone": "+963993333333",
          "company_id": 1,
          "referral_code": "REP456",
          "work_days": ["sunday", "wednesday", "friday"]
        }
      ],
      "latitude": 33.513805,
      "longitude": 36.276527,
      "is_active": true,
      "created_at": "2026-08-20T10:30:00Z",
      "updated_at": "2026-08-23T14:20:00Z"
    }
  }
}
```

**Error Responses:**

- **400 Bad Request** - Invalid assignment data
```json
{
  "success": false,
  "message": "بيانات التعيين غير صالحة",
  "errors": {
    "work_days": ["أيام غير صالحة: xyz"]
  }
}
```

- **404 Not Found** - Rep doesn't exist or doesn't belong to company
```json
{
  "success": false,
  "message": "بعض المندوبين غير موجودين",
  "errors": {
    "rep_ids": ["بعض المندوبين غير موجودين أو غير نشطين في هذه الشركة"]
  }
}
```

---

### 2. Remove Rep Assignments from Customer

Remove one or more reps from a customer.

**Endpoint:** `POST /api/companies/customers/{customer_id}/remove-reps`

**Authentication:** Required (Company SubUser token)

**Request Body:**

```json
{
  "rep_ids": [123, 456]  // Optional: if not provided, removes all company reps
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم إزالة تعيين المندوبين بنجاح",
  "data": {
    "customer": {
      "id": 789,
      "name": "أحمد محمد",
      "assigned_reps_count": 0,
      "assigned_reps_details": []
    }
  }
}
```

---

### 3. Bulk Assign Rep to Multiple Customers

Assign a single rep to multiple customers at once with optional work days.

**Endpoint:** `POST /api/companies/customers/bulk-action/`

**Authentication:** Required (Company SubUser token)

**Request Body:**
```json
{
  "action": "assign_rep",
  "customer_ids": [789, 790, 791],
  "rep_id": 123,
  "work_days": ["sunday", "monday", "tuesday"]  // Optional
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تعيين المندوب لـ 3 عميل بنجاح",
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "failed_ids": []
  }
}
```

---

### 4. Bulk Remove Rep from Multiple Customers

Remove a rep from multiple customers at once.

**Endpoint:** `POST /api/companies/customers/bulk-action/`

**Authentication:** Required (Company SubUser token)

**Request Body:**
```json
{
  "action": "remove_rep",
  "customer_ids": [789, 790, 791],
  "rep_id": 123
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم إزالة المندوب من 3 عميل بنجاح",
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "failed_ids": []
  }
}
```

---

## Rep Endpoints

These endpoints are for sales representatives to manage their profile and assigned customers.

### 1. Get Rep Profile

Get the authenticated rep's profile information including their default work days.

**Endpoint:** `GET /api/reps/profile/`

**Authentication:** Required (Rep token)

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "profile": {
      "id": 123,
      "name": "مندوب المبيعات",
      "phone": "+963991234567",
      "referral_code": "REP123",
      "work_days": ["sunday", "monday", "tuesday", "wednesday", "thursday"],
      "is_active": true,
      "company": {
        "id": 1,
        "name": "شركة التجارة"
      },
      "created_at": "2026-01-15T10:00:00Z",
      "updated_at": "2026-08-23T14:30:00Z"
    }
  }
}
```

---

### 2. Update Rep Work Days

Update the rep's default work days (applies to all new assignments).

**Endpoint:** `PATCH /api/reps/profile/`

**Authentication:** Required (Rep token)

**Request Body:**
```json
{
  "work_days": ["sunday", "monday", "tuesday", "wednesday"]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تحديث أيام العمل بنجاح",
  "data": {
    "profile": {
      "id": 123,
      "name": "مندوب المبيعات",
      "work_days": ["sunday", "monday", "tuesday", "wednesday"]
    }
  }
}
```

**Error Response (400 Bad Request):**
```json
{
  "success": false,
  "message": "أيام العمل غير صالحة",
  "errors": {
    "work_days": ["أيام غير صالحة: xyz"]
  }
}
```

---

### 3. List Assigned Customers

Get list of all customers assigned to the authenticated rep.

**Endpoint:** `GET /api/reps/customers/`

**Authentication:** Required (Rep token)

**Query Parameters:**
- `is_active` (optional): Filter by active status (`true` or `false`)
- `search` (optional): Search by customer name or phone

**Examples:**
```
GET /api/reps/customers/
GET /api/reps/customers/?is_active=true
GET /api/reps/customers/?search=أحمد
```

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "customers": [
      {
        "id": 789,
        "name": "أحمد محمد",
        "phone": "+963991234567",
        "email": "ahmad@example.com",
        "latitude": 33.513805,
        "longitude": 36.276527,
        "is_active": true,
        "assigned_reps_count": 2,
        "assigned_reps_details": [
          {
            "id": 123,
            "name": "مندوب المبيعات",
            "phone": "+963992222222",
            "company_id": 1,
            "referral_code": "REP123",
            "work_days": ["sunday", "monday", "tuesday"]
          }
        ],
        "created_at": "2026-08-20T10:30:00Z",
        "updated_at": "2026-08-23T14:20:00Z"
      }
    ],
    "total": 1
  }
}
```

---

### 4. Get Customer Details

Get detailed information about a specific customer assigned to the rep.

**Endpoint:** `GET /api/reps/customers/{customer_id}/`

**Authentication:** Required (Rep token)

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "customer": {
      "id": 789,
      "name": "أحمد محمد",
      "phone": "+963991234567",
      "email": "ahmad@example.com",
      "latitude": 33.513805,
      "longitude": 36.276527,
      "is_active": true,
      "assigned_reps_details": [
        {
          "id": 123,
          "name": "مندوب المبيعات",
          "phone": "+963992222222",
          "company_id": 1,
          "referral_code": "REP123",
          "work_days": ["sunday", "monday", "tuesday"]
        }
      ],
      "created_at": "2026-08-20T10:30:00Z",
      "updated_at": "2026-08-23T14:20:00Z"
    }
  }
}
```

**Error Response (403 Forbidden):**
```json
{
  "success": false,
  "message": "غير مصرح لك بالوصول إلى هذا العميل"
}
```

---

### 5. Update Customer Location and Work Days

Update a customer's GPS location and/or work days for this specific assignment.

**Endpoint:** `PATCH /api/reps/customers/{customer_id}/`

**Authentication:** Required (Rep token)

**Request Body:**

**Update Location Only:**
```json
{
  "latitude": 33.513805,
  "longitude": 36.276527
}
```

**Update Work Days Only:**
```json
{
  "work_days": ["sunday", "wednesday", "friday"]
}
```

**Update Both:**
```json
{
  "latitude": 33.513805,
  "longitude": 36.276527,
  "work_days": ["sunday", "monday", "tuesday"]
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تحديث الموقع و أيام العمل بنجاح",
  "data": {
    "customer": {
      "id": 789,
      "name": "أحمد محمد",
      "phone": "+963991234567",
      "latitude": 33.513805,
      "longitude": 36.276527,
      "assigned_reps_details": [
        {
          "id": 123,
          "name": "مندوب المبيعات",
          "work_days": ["sunday", "monday", "tuesday"]
        }
      ]
    }
  }
}
```

**Error Responses:**

- **400 Bad Request** - Invalid data
```json
{
  "success": false,
  "message": "بيانات غير صالحة",
  "errors": {
    "location": ["يجب تقديم خطوط الطول والعرض معاً أو تركهما فارغين"],
    "work_days": ["أيام غير صالحة: xyz"]
  }
}
```

- **403 Forbidden** - Customer not assigned to this rep
```json
{
  "success": false,
  "message": "غير مصرح لك بتعديل هذا العميل"
}
```

---

### 6. Get Customer Statistics

Get statistics about the rep's assigned customers.

**Endpoint:** `GET /api/reps/customers/stats/`

**Authentication:** Required (Rep token)

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "total_customers": 50,
    "active_customers": 45,
    "inactive_customers": 5
  }
}
```

---

## Customer Management

### Get Customer with Assignments

When fetching customer details, the response includes all rep assignments with their work days.

**Endpoint:** `GET /api/companies/customers/{customer_id}/`

**Authentication:** Required (Company SubUser token)

**Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "customer": {
      "id": 789,
      "name": "أحمد محمد",
      "phone": "+963991234567",
      "email": "ahmad@example.com",
      "latitude": 33.513805,
      "longitude": 36.276527,
      "is_active": true,
      "assigned_reps_count": 2,
      "assigned_reps_details": [
        {
          "id": 123,
          "name": "مندوب 1",
          "phone": "+963992222222",
          "company_id": 1,
          "referral_code": "REP123",
          "work_days": ["sunday", "monday", "tuesday"]
        },
        {
          "id": 456,
          "name": "مندوب 2",
          "phone": "+963993333333",
          "company_id": 1,
          "referral_code": "REP456",
          "work_days": []  // Empty means uses rep's default
        }
      ],
      "category_details": {
        "id": 1,
        "name": "تاجر جملة",
        "is_global": true
      },
      "created_at": "2026-08-20T10:30:00Z",
      "updated_at": "2026-08-23T14:20:00Z"
    }
  }
}
```

---

## Authentication

### Rep Sign In

**Endpoint:** `POST /api/auth/rep/signin`

**Request Body:**
```json
{
  "phone": "+963991234567",
  "password": "securepassword"
}
```

**Response (200 OK):**
```json
{
  "success": true,
  "message": "تم تسجيل الدخول بنجاح",
  "data": {
    "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
    "rep": {
      "id": 123,
      "name": "مندوب المبيعات",
      "phone": "+963991234567",
      "company_id": 1,
      "referral_code": "REP123"
    }
  }
}
```

**Token Claims:**
The JWT token includes:
- `actor_type`: `"rep"`
- `rep_id`: Rep's ID
- `company_id`: Rep's company ID
- `user_id`: Rep's ID (same as rep_id)

---

## Business Logic

### Work Days Inheritance

Work days follow a hierarchical system:

1. **Rep Default Work Days**: Set on the rep's profile (`/api/reps/profile/`)
2. **Assignment Work Days**: Set when assigning customer to rep (`/api/companies/customers/{id}/assign-reps`)
3. **Effective Work Days**: Assignment work days OR rep's default if assignment work days is empty

**Example:**
```
Rep Default Work Days: ["sunday", "monday", "tuesday", "wednesday", "thursday"]

Assignment 1 (Customer A):
  work_days: ["sunday", "wednesday"]
  Effective: ["sunday", "wednesday"]

Assignment 2 (Customer B):
  work_days: []
  Effective: ["sunday", "monday", "tuesday", "wednesday", "thursday"] (uses rep's default)
```

### Permission Model

- **Companies** can:
  - Assign any of their reps to customers
  - Specify work days for each assignment
  - Remove rep assignments
  - View all customer-rep assignments

- **Reps** can:
  - View only customers assigned to them
  - Update their own default work days
  - Update customer locations
  - Update work days for their specific assignments
  - Cannot access customers not assigned to them

---

## Error Codes

| HTTP Status | Error Code | Description |
|-------------|------------|-------------|
| 400 | `BAD_REQUEST` | Invalid request data or validation error |
| 401 | `UNAUTHORIZED` | Missing or invalid authentication token |
| 403 | `FORBIDDEN` | Insufficient permissions for the operation |
| 404 | `NOT_FOUND` | Resource not found |
| 500 | `INTERNAL_SERVER_ERROR` | Server error |

---

## Best Practices

### 1. Work Days Validation
Always validate work days on the frontend before sending:
```javascript
const validDays = [
  'sunday', 'monday', 'tuesday', 'wednesday', 
  'thursday', 'friday', 'saturday'
];

function validateWorkDays(days) {
  return days.every(day => validDays.includes(day.toLowerCase()));
}
```

### 2. GPS Coordinates
Always send latitude and longitude together:
```javascript
function updateLocation(customerId, lat, lng) {
  if ((lat && !lng) || (!lat && lng)) {
    throw new Error('Both latitude and longitude are required');
  }
  // Make API call
}
```

### 3. Token Management
Store and use the correct token type:
```javascript
// For rep operations
headers: {
  'Authorization': `Bearer ${repAccessToken}`
}

// For company operations
headers: {
  'Authorization': `Bearer ${companyAccessToken}`
}
```

### 4. Error Handling
Handle specific error cases:
```javascript
try {
  await assignReps(customerId, assignments);
} catch (error) {
  if (error.status === 403) {
    // Handle permission denied
  } else if (error.status === 404) {
    // Handle rep not found
  } else if (error.status === 400) {
    // Show validation errors
    displayErrors(error.errors);
  }
}
```

---

## Change Log

### v1.1.0 (2026-08-23)
- Added work days management for reps
- Added customer-rep assignment with work days
- Added rep endpoints to update customer location and work days
- Added rep profile management endpoints
- Backward compatible with existing assignment APIs

---

## Support

For questions or issues with the API:
- Backend Team: backend@company.com
- API Documentation: https://api.company.com/docs
