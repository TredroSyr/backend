# Sub-User Permissions API Documentation

## Overview

This API allows company owners to create sub-users with granular permissions for the six available modules:
- `customers` (العملاء)
- `invoices` (الفواتير)
- `orders` (الطلبات)
- `products` (المنتجات)
- `reps` (المندوبين)
- `notifications` (الإشعارات)

Each module can have two permission levels:
- **CAN_VIEW** (`can_view`): Read-only access
- **CAN_ACTION** (`can_action`): Read and write access

## Endpoints

### 1. Get Available Modules

**GET** `/api/companies/modules`

Returns list of all available modules with their labels in Arabic and English.

**Response:**
```json
{
  "success": true,
  "data": {
    "modules": [
      {
        "value": "customers",
        "label": "العملاء",
        "label_en": "Customers"
      },
      {
        "value": "invoices",
        "label": "الفواتير",
        "label_en": "Invoices"
      }
      // ... other modules
    ]
  }
}
```

---

### 2. Create Sub-User

**POST** `/api/companies/subusers`

Creates a new sub-user with specified module permissions. Only company owners can create sub-users.

**Request Body:**
```json
{
  "name": "أحمد محمد",
  "phone": "0912345678",
  "email": "ahmed@example.com",  // optional
  "password": "secure_password",
  "permissions": [
    {
      "module": "customers",
      "can_view": true,
      "can_action": false
    },
    {
      "module": "orders",
      "can_view": true,
      "can_action": true
    },
    {
      "module": "products",
      "can_view": true,
      "can_action": false
    }
  ]
}
```

**Validation Rules:**
- At least one permission must be provided
- Each permission must have either `can_view` or `can_action` enabled (or both)
- No duplicate modules allowed
- Phone number must be unique within the company
- Password minimum 6 characters

**Response:**
```json
{
  "success": true,
  "message": "تم إنشاء المستخدم الفرعي بنجاح",
  "data": {
    "subuser": {
      "id": 123,
      "name": "أحمد محمد",
      "phone": "0912345678",
      "email": "ahmed@example.com",
      "is_owner": false,
      "is_active": true,
      "role_name": "أحمد محمد - Role",
      "permissions": [
        {
          "module": "customers",
          "can_view": true,
          "can_action": false
        },
        {
          "module": "orders",
          "can_view": true,
          "can_action": true
        },
        {
          "module": "products",
          "can_view": true,
          "can_action": false
        }
      ],
      "created_at": "2026-08-16T10:30:00Z"
    }
  }
}
```

---

### 3. List All Sub-Users

**GET** `/api/companies/subusers/list`

Returns all sub-users for the company with their permissions.

**Response:**
```json
{
  "success": true,
  "data": {
    "subusers": [
      {
        "id": 1,
        "name": "مالك الشركة",
        "phone": "0911111111",
        "email": "owner@example.com",
        "is_owner": true,
        "is_active": true,
        "role_name": null,
        "permissions": [
          {
            "module": "customers",
            "can_view": true,
            "can_action": true
          }
          // ... all modules with full permissions
        ],
        "created_at": "2026-08-01T10:00:00Z"
      },
      {
        "id": 2,
        "name": "أحمد محمد",
        "phone": "0912345678",
        "email": "ahmed@example.com",
        "is_owner": false,
        "is_active": true,
        "role_name": "أحمد محمد - Role",
        "permissions": [
          {
            "module": "customers",
            "can_view": true,
            "can_action": false
          }
          // ... assigned permissions only
        ],
        "created_at": "2026-08-16T10:30:00Z"
      }
    ]
  }
}
```

---

## Frontend Integration Guide

### Permission Levels Mapping

For the frontend UX, you can present two simple options:
- **"قراءة فقط" (Read Only)**: Sets `can_view: true, can_action: false`
- **"قراءة وكتابة" (Read & Write)**: Sets `can_view: true, can_action: true`

### Example Frontend Form

```javascript
// Module selection with permission levels
const modules = [
  { value: 'customers', label: 'العملاء' },
  { value: 'invoices', label: 'الفواتير' },
  { value: 'orders', label: 'الطلبات' },
  { value: 'products', label: 'المنتجات' },
  { value: 'reps', label: 'المندوبين' },
  { value: 'notifications', label: 'الإشعارات' },
];

// User selects modules and permission level
const selectedPermissions = {
  customers: 'read',           // قراءة فقط
  orders: 'read_write',        // قراءة وكتابة
  products: 'read',            // قراءة فقط
};

// Convert to API format
const permissions = Object.entries(selectedPermissions).map(([module, level]) => ({
  module,
  can_view: true,  // Always true if module is selected
  can_action: level === 'read_write',
}));

// Send to API
const payload = {
  name: 'أحمد محمد',
  phone: '0912345678',
  email: 'ahmed@example.com',
  password: 'secure_password',
  permissions,
};
```

---

## Technical Details

### Database Structure

**Role Table:**
- Each sub-user gets their own role automatically
- Role name format: `{user_name} - Role`
- Company owner doesn't need a role (has implicit full access)

**ModulePermission Table:**
- Links roles to modules with permissions
- Unique constraint: one permission record per role+module combination

**SubUser Table:**
- Links to company and role
- Owner has `is_owner: true` and `role: null`
- Phone number must be unique within company

### Implementation Notes

1. **Transaction Safety**: Sub-user creation uses database transactions to ensure atomicity
2. **Password Hashing**: Passwords are hashed using Django's `make_password()`
3. **Permission Inheritance**: Role permissions are inherited by the sub-user
4. **Owner Privileges**: Company owner always has all permissions regardless of role

### Error Responses

```json
{
  "success": false,
  "message": "بيانات غير صالحة",
  "errors": {
    "phone": ["رقم الهاتف مستخدم بالفعل في هذه الشركة"],
    "permissions": ["يجب تحديد صلاحية واحدة على الأقل"]
  }
}
```

Common validation errors:
- `phone`: Duplicate phone number
- `permissions`: Empty permissions, duplicate modules, or invalid module names
- `password`: Too short (minimum 6 characters)
- `permission`: Only owner can create sub-users

---

## Security Considerations

1. **Authentication Required**: All endpoints require valid authentication
2. **Owner-Only Access**: Only company owners can create sub-users
3. **Company Isolation**: All operations are scoped to the authenticated user's company
4. **Password Security**: Passwords are hashed before storage
5. **Phone Uniqueness**: Enforced at database level per company
