# Customer Categories API Documentation

## Overview

This API allows companies to manage customer categories and assign them to customers. Each company can:
- Use global default categories (e.g., "تاجر جملة", "تاجر مفرق")
- Create custom categories specific to their company
- Assign different categories to the same customer (per-company assignment)

### Key Concept: Per-Company Category Assignment

Since customers are global entities shared across companies, **each company can assign their own category to a customer**. This means:
- Customer #123 can be "تاجر جملة" for Company A
- The same Customer #123 can be "مطاعم" for Company B
- Both assignments coexist independently

---

## Authentication

All endpoints require authentication with a company context.

**Headers:**
```http
Authorization: Bearer <access_token>
X-Company-ID: <company_id>
```

---

## Endpoints

### 1. List Available Categories

Get all categories available to your company (global defaults + your custom categories).

**Endpoint:**
```http
GET /api/companies/customer-categories
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": null,
  "data": {
    "categories": [
      {
        "id": 1,
        "name": "تاجر جملة",
        "is_global": true,
        "is_custom": false,
        "created_at": "2024-01-01T00:00:00Z"
      },
      {
        "id": 2,
        "name": "تاجر مفرق",
        "is_global": true,
        "is_custom": false,
        "created_at": "2024-01-01T00:00:00Z"
      },
      {
        "id": 5,
        "name": "مطاعم",
        "is_global": false,
        "is_custom": true,
        "created_at": "2024-02-15T10:30:00Z"
      }
    ]
  }
}
```

**Field Descriptions:**
- `id` - Category ID (use this when assigning to customers)
- `name` - Category name in Arabic
- `is_global` - `true` if this is a default category available to all companies
- `is_custom` - `true` if this category was created by your company
- `created_at` - When the category was created

**Usage Example (JavaScript):**
```javascript
async function loadCategories() {
  const response = await fetch('/api/companies/customer-categories', {
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId
    }
  });
  
  const result = await response.json();
  const categories = result.data.categories;
  
  // Display in dropdown
  categories.forEach(cat => {
    const label = cat.is_global 
      ? `${cat.name} (افتراضي)` 
      : cat.name;
    // Add to UI
  });
}
```

---

### 2. Create Custom Category

Create a new custom category for your company.

**Endpoint:**
```http
POST /api/companies/customer-categories
```

**Request Body:**
```json
{
  "name": "صيدليات"
}
```

**Response:** `201 Created`
```json
{
  "success": true,
  "message": "تم إنشاء التصنيف بنجاح",
  "data": {
    "category": {
      "id": 8,
      "name": "صيدليات",
      "is_global": false,
      "is_custom": true,
      "created_at": "2024-03-20T14:30:00Z"
    }
  }
}
```

**Error Response:** `400 Bad Request`
```json
{
  "success": false,
  "message": "هذا التصنيف موجود مسبقاً",
  "errors": {
    "name": ["يوجد تصنيف بنفس الاسم"]
  }
}
```

**Validation Rules:**
- `name` is required and cannot be empty
- `name` must be unique within your company's categories
- Maximum length: 100 characters

**Usage Example (JavaScript):**
```javascript
async function createCategory(categoryName) {
  const response = await fetch('/api/companies/customer-categories', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ name: categoryName })
  });
  
  const result = await response.json();
  
  if (result.success) {
    // Add new category to local list
    const newCategory = result.data.category;
    console.log('Created category:', newCategory);
  } else {
    // Show error
    console.error('Error:', result.message);
  }
}
```

---

### 3. Update Custom Category

Update an existing custom category (only your company's categories, not global defaults).

**Endpoint:**
```http
PATCH /api/companies/customer-categories/{id}
```

**Request Body:**
```json
{
  "name": "صيدليات كبيرة"
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم تحديث التصنيف بنجاح",
  "data": {
    "category": {
      "id": 8,
      "name": "صيدليات كبيرة",
      "is_global": false,
      "is_custom": true,
      "created_at": "2024-03-20T14:30:00Z"
    }
  }
}
```

**Error Responses:**

`403 Forbidden` (trying to update global category):
```json
{
  "success": false,
  "message": "لا يمكن تعديل التصنيفات الافتراضية",
  "errors": null
}
```

`403 Forbidden` (trying to update another company's category):
```json
{
  "success": false,
  "message": "غير مصرح بتعديل هذا التصنيف",
  "errors": null
}
```

`404 Not Found`:
```json
{
  "success": false,
  "message": "التصنيف غير موجود",
  "errors": null
}
```

---

### 4. Delete Custom Category

Soft-delete a custom category (only your company's categories, not global defaults).

**Endpoint:**
```http
DELETE /api/companies/customer-categories/{id}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم حذف التصنيف بنجاح",
  "data": null
}
```

**Important Notes:**
- This is a soft delete (category is marked inactive, not removed from database)
- Customers assigned to this category will have their category set to `null` for your company
- Other companies' assignments are not affected
- You cannot delete global default categories

**Error Responses:**
Same as Update endpoint (403 for global/other company's categories, 404 for not found)

---

### 5. Assign Category to Customer (Create)

Assign a category to a customer when creating them.

**Endpoint:**
```http
POST /api/companies/customers
```

**Request Body:**
```json
{
  "name": "أحمد محمود",
  "phone": "+963991234567",
  "email": "ahmad@example.com",
  "category": 5,
  "assigned_reps": [1, 2],
  "latitude": 33.510414,
  "longitude": 36.278336,
  "is_active": true
}
```

**Field Descriptions:**
- `name` - Required. Customer name
- `phone` - Required. Phone number in format `+963XXXXXXXXX`
- `email` - Optional. Email address
- `category` - Optional. Category ID from the list of available categories
- `assigned_reps` - Optional. Array of rep IDs from your company
- `latitude` / `longitude` - Optional. GPS coordinates
- `is_active` - Optional. Default: `true`

**Response:** `201 Created`
```json
{
  "success": true,
  "message": "تم إضافة العميل بنجاح",
  "data": {
    "customer": {
      "id": 123,
      "name": "أحمد محمود",
      "phone": "+963991234567",
      "email": "ahmad@example.com",
      "category_details": {
        "id": 5,
        "name": "مطاعم",
        "is_global": false
      },
      "assigned_reps_details": [
        {
          "id": 1,
          "name": "مندوب 1",
          "phone": "+963991111111",
          "company_id": 10,
          "referral_code": "REP001"
        }
      ],
      "referral_code_used": null,
      "latitude": "33.510414",
      "longitude": "36.278336",
      "is_active": true,
      "created_at": "2024-03-20T15:00:00Z",
      "updated_at": "2024-03-20T15:00:00Z"
    }
  }
}
```

**Important:**
- `category_details` shows the category **your company assigned**
- If another company views this customer, they will see their own `category_details`

**Usage Example (JavaScript):**
```javascript
async function createCustomer(customerData) {
  const response = await fetch('/api/companies/customers', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      name: customerData.name,
      phone: customerData.phone,
      email: customerData.email,
      category: customerData.categoryId,  // Category ID from dropdown
      assigned_reps: customerData.repIds,
      is_active: true
    })
  });
  
  const result = await response.json();
  return result;
}
```

---

### 6. Update Customer Category

Update a customer's category assignment for your company.

**Endpoint:**
```http
PATCH /api/companies/customers/{id}
```

**Request Body:**
```json
{
  "category": 8
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم تحديث بيانات العميل بنجاح",
  "data": {
    "customer": {
      "id": 123,
      "name": "أحمد محمود",
      "phone": "+963991234567",
      "category_details": {
        "id": 8,
        "name": "صيدليات",
        "is_global": false
      },
      ...
    }
  }
}
```

**To Remove Category Assignment:**
```json
{
  "category": null
}
```

**Important:**
- This only updates the category assignment **for your company**
- Other companies' category assignments for this customer remain unchanged
- You can update other fields at the same time (name, phone, email, etc.)

**Usage Example (JavaScript):**
```javascript
async function updateCustomerCategory(customerId, categoryId) {
  const response = await fetch(`/api/companies/customers/${customerId}`, {
    method: 'PATCH',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ category: categoryId })
  });
  
  const result = await response.json();
  return result;
}

// Remove category
await updateCustomerCategory(123, null);
```

---

### 7. List Customers (with Category Filter)

Get list of customers with optional filtering by category.

**Endpoint:**
```http
GET /api/companies/customers?category_id={id}
```

**Query Parameters:**
- `category_id` - Optional. Filter by category ID (shows customers **your company** assigned to this category)
- `is_active` - Optional. Filter by active status (`true` or `false`)
- `my_company_only` - Optional. If `true`, only show customers assigned to your company's reps

**Response:** `200 OK`
```json
{
  "success": true,
  "message": null,
  "data": {
    "customers": [
      {
        "id": 123,
        "name": "أحمد محمود",
        "phone": "+963991234567",
        "email": "ahmad@example.com",
        "category_name": "مطاعم",
        "assigned_reps_count": 2,
        "referral_code_used": null,
        "is_active": true,
        "created_at": "2024-03-20T15:00:00Z"
      },
      {
        "id": 124,
        "name": "فاطمة علي",
        "phone": "+963992345678",
        "email": null,
        "category_name": "مطاعم",
        "assigned_reps_count": 1,
        "referral_code_used": null,
        "is_active": true,
        "created_at": "2024-03-21T10:00:00Z"
      }
    ]
  }
}
```

**Field Descriptions:**
- `category_name` - The category name **your company assigned** (or `null` if no category)
- `assigned_reps_count` - Number of reps assigned from all companies

**Usage Examples:**

**Filter by category:**
```javascript
// Get all customers in "مطاعم" category (for your company)
const response = await fetch(
  '/api/companies/customers?category_id=5',
  { headers: { 'Authorization': `Bearer ${token}`, 'X-Company-ID': companyId } }
);
```

**Filter by category + active status:**
```javascript
// Get active customers in "تاجر جملة" category
const response = await fetch(
  '/api/companies/customers?category_id=1&is_active=true',
  { headers: { 'Authorization': `Bearer ${token}`, 'X-Company-ID': companyId } }
);
```

**Get only customers assigned to your company's reps:**
```javascript
const response = await fetch(
  '/api/companies/customers?my_company_only=true&category_id=5',
  { headers: { 'Authorization': `Bearer ${token}`, 'X-Company-ID': companyId } }
);
```

---

### 8. Get Customer Details

Get detailed information about a customer, including the category your company assigned.

**Endpoint:**
```http
GET /api/companies/customers/{id}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": null,
  "data": {
    "customer": {
      "id": 123,
      "name": "أحمد محمود",
      "phone": "+963991234567",
      "email": "ahmad@example.com",
      "category_details": {
        "id": 5,
        "name": "مطاعم",
        "is_global": false
      },
      "assigned_reps_details": [
        {
          "id": 1,
          "name": "مندوب 1",
          "phone": "+963991111111",
          "company_id": 10,
          "referral_code": "REP001"
        },
        {
          "id": 2,
          "name": "مندوب 2",
          "phone": "+963992222222",
          "company_id": 10,
          "referral_code": "REP002"
        }
      ],
      "referral_code_used": null,
      "latitude": "33.510414",
      "longitude": "36.278336",
      "is_active": true,
      "created_at": "2024-03-20T15:00:00Z",
      "updated_at": "2024-03-20T15:00:00Z"
    }
  }
}
```

**Important:**
- `category_details` shows the category **your company assigned** to this customer
- If this customer has no category from your company, `category_details` will be `null`
- Other companies will see their own `category_details` for the same customer

---

## Complete Frontend Integration Example

### React Hook for Category Management

```javascript
import { useState, useEffect } from 'react';

export function useCustomerCategories() {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  // Load categories
  const loadCategories = async () => {
    setLoading(true);
    try {
      const response = await fetch('/api/companies/customer-categories', {
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'X-Company-ID': getCompanyId()
        }
      });
      const result = await response.json();
      
      if (result.success) {
        setCategories(result.data.categories);
      } else {
        setError(result.message);
      }
    } catch (err) {
      setError('فشل في تحميل التصنيفات');
    } finally {
      setLoading(false);
    }
  };

  // Create category
  const createCategory = async (name) => {
    try {
      const response = await fetch('/api/companies/customer-categories', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'X-Company-ID': getCompanyId(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });
      
      const result = await response.json();
      
      if (result.success) {
        // Add to local state
        setCategories([...categories, result.data.category]);
        return { success: true, category: result.data.category };
      } else {
        return { success: false, error: result.message };
      }
    } catch (err) {
      return { success: false, error: 'فشل في إنشاء التصنيف' };
    }
  };

  // Update category
  const updateCategory = async (id, name) => {
    try {
      const response = await fetch(`/api/companies/customer-categories/${id}`, {
        method: 'PATCH',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'X-Company-ID': getCompanyId(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ name })
      });
      
      const result = await response.json();
      
      if (result.success) {
        // Update local state
        setCategories(categories.map(cat => 
          cat.id === id ? result.data.category : cat
        ));
        return { success: true };
      } else {
        return { success: false, error: result.message };
      }
    } catch (err) {
      return { success: false, error: 'فشل في تحديث التصنيف' };
    }
  };

  // Delete category
  const deleteCategory = async (id) => {
    try {
      const response = await fetch(`/api/companies/customer-categories/${id}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'X-Company-ID': getCompanyId()
        }
      });
      
      const result = await response.json();
      
      if (result.success) {
        // Remove from local state
        setCategories(categories.filter(cat => cat.id !== id));
        return { success: true };
      } else {
        return { success: false, error: result.message };
      }
    } catch (err) {
      return { success: false, error: 'فشل في حذف التصنيف' };
    }
  };

  useEffect(() => {
    loadCategories();
  }, []);

  return {
    categories,
    loading,
    error,
    createCategory,
    updateCategory,
    deleteCategory,
    reloadCategories: loadCategories
  };
}
```

### React Component Example

```javascript
import React, { useState } from 'react';
import { useCustomerCategories } from './hooks/useCustomerCategories';

function CustomerForm({ customer, onSave }) {
  const { categories, loading, createCategory } = useCustomerCategories();
  const [formData, setFormData] = useState({
    name: customer?.name || '',
    phone: customer?.phone || '',
    email: customer?.email || '',
    category: customer?.category_details?.id || null
  });
  const [showNewCategoryInput, setShowNewCategoryInput] = useState(false);
  const [newCategoryName, setNewCategoryName] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const customerData = {
      name: formData.name,
      phone: formData.phone,
      email: formData.email,
      category: formData.category  // Category ID or null
    };
    
    await onSave(customerData);
  };

  const handleCreateNewCategory = async () => {
    const result = await createCategory(newCategoryName);
    
    if (result.success) {
      // Auto-select the newly created category
      setFormData({ ...formData, category: result.category.id });
      setNewCategoryName('');
      setShowNewCategoryInput(false);
    } else {
      alert(result.error);
    }
  };

  return (
    <form onSubmit={handleSubmit}>
      <div>
        <label>الاسم *</label>
        <input
          value={formData.name}
          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
          required
        />
      </div>

      <div>
        <label>رقم الهاتف *</label>
        <input
          value={formData.phone}
          onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
          placeholder="+963991234567"
          required
        />
      </div>

      <div>
        <label>البريد الإلكتروني</label>
        <input
          type="email"
          value={formData.email}
          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
        />
      </div>

      <div>
        <label>التصنيف</label>
        <select
          value={formData.category || ''}
          onChange={(e) => setFormData({ 
            ...formData, 
            category: e.target.value ? parseInt(e.target.value) : null 
          })}
        >
          <option value="">بدون تصنيف</option>
          {categories.map(cat => (
            <option key={cat.id} value={cat.id}>
              {cat.name} {cat.is_global && '(افتراضي)'}
            </option>
          ))}
        </select>
        
        <button 
          type="button" 
          onClick={() => setShowNewCategoryInput(true)}
        >
          + إضافة تصنيف جديد
        </button>
      </div>

      {showNewCategoryInput && (
        <div>
          <input
            value={newCategoryName}
            onChange={(e) => setNewCategoryName(e.target.value)}
            placeholder="اسم التصنيف الجديد"
          />
          <button type="button" onClick={handleCreateNewCategory}>
            حفظ التصنيف
          </button>
          <button type="button" onClick={() => setShowNewCategoryInput(false)}>
            إلغاء
          </button>
        </div>
      )}

      <button type="submit">حفظ العميل</button>
    </form>
  );
}
```

### Customer List with Category Filter

```javascript
function CustomerList() {
  const { categories } = useCustomerCategories();
  const [customers, setCustomers] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState(null);

  const loadCustomers = async (categoryId = null) => {
    const url = categoryId 
      ? `/api/companies/customers?category_id=${categoryId}`
      : '/api/companies/customers';
      
    const response = await fetch(url, {
      headers: {
        'Authorization': `Bearer ${getAccessToken()}`,
        'X-Company-ID': getCompanyId()
      }
    });
    
    const result = await response.json();
    if (result.success) {
      setCustomers(result.data.customers);
    }
  };

  const handleCategoryFilter = (categoryId) => {
    setSelectedCategory(categoryId);
    loadCustomers(categoryId);
  };

  return (
    <div>
      <div className="filters">
        <label>تصفية حسب التصنيف:</label>
        <select 
          value={selectedCategory || ''} 
          onChange={(e) => handleCategoryFilter(e.target.value || null)}
        >
          <option value="">الكل</option>
          {categories.map(cat => (
            <option key={cat.id} value={cat.id}>
              {cat.name}
            </option>
          ))}
        </select>
      </div>

      <table>
        <thead>
          <tr>
            <th>الاسم</th>
            <th>رقم الهاتف</th>
            <th>التصنيف</th>
            <th>عدد المندوبين</th>
          </tr>
        </thead>
        <tbody>
          {customers.map(customer => (
            <tr key={customer.id}>
              <td>{customer.name}</td>
              <td>{customer.phone}</td>
              <td>{customer.category_name || '-'}</td>
              <td>{customer.assigned_reps_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

### 9. Bulk Actions on Customers

Perform bulk operations on multiple customers at once.

**Endpoint:**
```http
POST /api/companies/customers/bulk-action/
```

**Supported Actions:**
- `assign_rep` - Assign a sales rep to multiple customers
- `assign_category` - Assign a category to multiple customers
- `remove_rep` - Remove a sales rep from multiple customers
- `remove_category` - Remove category assignment from multiple customers
- `delete` - Soft delete (deactivate) multiple customers

#### 9.1. Bulk Assign Rep

Assign a single rep to multiple customers at once.

**Request Body:**
```json
{
  "action": "assign_rep",
  "customer_ids": [123, 124, 125, 126],
  "rep_id": 10
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم تعيين المندوب لـ 4 عميل بنجاح",
  "data": {
    "total": 4,
    "successful": 4,
    "failed": 0,
    "failed_ids": []
  }
}
```

**Error Response (Invalid Rep):** `404 Not Found`
```json
{
  "success": false,
  "message": "المندوب غير موجود",
  "errors": {
    "rep_id": ["المندوب غير موجود أو غير نشط في هذه الشركة"]
  }
}
```

**Usage Example (JavaScript):**
```javascript
async function bulkAssignRep(customerIds, repId) {
  const response = await fetch('/api/companies/customers/bulk-action/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      action: 'assign_rep',
      customer_ids: customerIds,
      rep_id: repId
    })
  });
  
  const result = await response.json();
  
  if (result.success) {
    console.log(`Successfully assigned rep to ${result.data.successful} customers`);
    if (result.data.failed > 0) {
      console.warn(`Failed for customer IDs: ${result.data.failed_ids.join(', ')}`);
    }
  }
  
  return result;
}

// Example: Assign rep #10 to selected customers
await bulkAssignRep([123, 124, 125], 10);
```

---

#### 9.2. Bulk Assign Category

Assign a single category to multiple customers at once.

**Request Body:**
```json
{
  "action": "assign_category",
  "customer_ids": [123, 124, 125],
  "category_id": 5
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم تعيين التصنيف لـ 3 عميل بنجاح",
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "failed_ids": []
  }
}
```

**Error Response (Invalid Category):** `404 Not Found`
```json
{
  "success": false,
  "message": "التصنيف غير موجود",
  "errors": {
    "category_id": ["التصنيف غير موجود أو غير متاح"]
  }
}
```

**Usage Example (JavaScript):**
```javascript
async function bulkAssignCategory(customerIds, categoryId) {
  const response = await fetch('/api/companies/customers/bulk-action/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      action: 'assign_category',
      customer_ids: customerIds,
      category_id: categoryId
    })
  });
  
  const result = await response.json();
  return result;
}

// Example: Assign "مطاعم" category to selected customers
await bulkAssignCategory([123, 124, 125], 5);
```

---

#### 9.3. Bulk Remove Rep

Remove a rep assignment from multiple customers at once.

**Request Body:**
```json
{
  "action": "remove_rep",
  "customer_ids": [123, 124, 125],
  "rep_id": 10
}
```

**Response:** `200 OK`
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

**Usage Example (JavaScript):**
```javascript
async function bulkRemoveRep(customerIds, repId) {
  const response = await fetch('/api/companies/customers/bulk-action/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      action: 'remove_rep',
      customer_ids: customerIds,
      rep_id: repId
    })
  });
  
  const result = await response.json();
  return result;
}
```

---

#### 9.4. Bulk Remove Category

Remove category assignments from multiple customers at once (for your company).

**Request Body:**
```json
{
  "action": "remove_category",
  "customer_ids": [123, 124, 125]
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم إزالة التصنيف من 3 عميل بنجاح",
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "failed_ids": []
  }
}
```

**Important:**
- This removes the category assignment **for your company only**
- Other companies' category assignments are not affected
- No `category_id` needed - removes whatever category your company assigned

**Usage Example (JavaScript):**
```javascript
async function bulkRemoveCategory(customerIds) {
  const response = await fetch('/api/companies/customers/bulk-action/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      action: 'remove_category',
      customer_ids: customerIds
    })
  });
  
  const result = await response.json();
  return result;
}
```

---

#### 9.5. Bulk Delete Customers

Soft delete (deactivate) multiple customers at once.

**Request Body:**
```json
{
  "action": "delete",
  "customer_ids": [123, 124, 125]
}
```

**Response:** `200 OK`
```json
{
  "success": true,
  "message": "تم تعطيل 3 عميل بنجاح",
  "data": {
    "total": 3,
    "successful": 3,
    "failed": 0,
    "failed_ids": []
  }
}
```

**Important:**
- This is a **soft delete** (sets `is_active = false`)
- Customers are not permanently removed from the database
- All customer relationships (reps, categories, orders) are preserved
- Can be reactivated later if needed

**Usage Example (JavaScript):**
```javascript
async function bulkDeleteCustomers(customerIds) {
  // Show confirmation dialog
  const confirmed = confirm(
    `هل أنت متأكد من تعطيل ${customerIds.length} عميل؟`
  );
  
  if (!confirmed) return;
  
  const response = await fetch('/api/companies/customers/bulk-action/', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${accessToken}`,
      'X-Company-ID': companyId,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({
      action: 'delete',
      customer_ids: customerIds
    })
  });
  
  const result = await response.json();
  return result;
}
```

---

#### 9.6. Complete React Example with Bulk Actions

```javascript
import React, { useState } from 'react';

function CustomerListWithBulkActions() {
  const [customers, setCustomers] = useState([]);
  const [selectedCustomerIds, setSelectedCustomerIds] = useState([]);
  const [categories, setCategories] = useState([]);
  const [reps, setReps] = useState([]);
  
  // Toggle customer selection
  const toggleCustomerSelection = (customerId) => {
    setSelectedCustomerIds(prev => 
      prev.includes(customerId)
        ? prev.filter(id => id !== customerId)
        : [...prev, customerId]
    );
  };
  
  // Select all / deselect all
  const toggleSelectAll = () => {
    if (selectedCustomerIds.length === customers.length) {
      setSelectedCustomerIds([]);
    } else {
      setSelectedCustomerIds(customers.map(c => c.id));
    }
  };
  
  // Generic bulk action handler
  const performBulkAction = async (action, additionalData = {}) => {
    if (selectedCustomerIds.length === 0) {
      alert('الرجاء اختيار عملاء أولاً');
      return;
    }
    
    const response = await fetch('/api/companies/customers/bulk-action/', {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${getAccessToken()}`,
        'X-Company-ID': getCompanyId(),
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        action,
        customer_ids: selectedCustomerIds,
        ...additionalData
      })
    });
    
    const result = await response.json();
    
    if (result.success) {
      alert(result.message);
      // Reload customers list
      await loadCustomers();
      // Clear selection
      setSelectedCustomerIds([]);
    } else {
      alert(`خطأ: ${result.message}`);
    }
    
    return result;
  };
  
  // Specific bulk action handlers
  const handleBulkAssignRep = async () => {
    const repId = prompt('أدخل معرف المندوب:');
    if (repId) {
      await performBulkAction('assign_rep', { rep_id: parseInt(repId) });
    }
  };
  
  const handleBulkAssignCategory = async () => {
    const categoryId = prompt('أدخل معرف التصنيف:');
    if (categoryId) {
      await performBulkAction('assign_category', { category_id: parseInt(categoryId) });
    }
  };
  
  const handleBulkRemoveCategory = async () => {
    const confirmed = confirm(
      `إزالة التصنيف من ${selectedCustomerIds.length} عميل؟`
    );
    if (confirmed) {
      await performBulkAction('remove_category');
    }
  };
  
  const handleBulkDelete = async () => {
    const confirmed = confirm(
      `تعطيل ${selectedCustomerIds.length} عميل؟ هذا الإجراء قابل للعكس.`
    );
    if (confirmed) {
      await performBulkAction('delete');
    }
  };
  
  return (
    <div>
      <div className="bulk-actions-toolbar">
        <button 
          onClick={toggleSelectAll}
          disabled={customers.length === 0}
        >
          {selectedCustomerIds.length === customers.length ? 'إلغاء التحديد' : 'تحديد الكل'}
        </button>
        
        <span>
          {selectedCustomerIds.length > 0 && (
            `تم تحديد ${selectedCustomerIds.length} عميل`
          )}
        </span>
        
        {selectedCustomerIds.length > 0 && (
          <div className="bulk-action-buttons">
            <button onClick={handleBulkAssignRep}>
              تعيين مندوب
            </button>
            <button onClick={handleBulkAssignCategory}>
              تعيين تصنيف
            </button>
            <button onClick={handleBulkRemoveCategory}>
              إزالة التصنيف
            </button>
            <button 
              onClick={handleBulkDelete}
              className="danger"
            >
              تعطيل العملاء
            </button>
          </div>
        )}
      </div>
      
      <table>
        <thead>
          <tr>
            <th>
              <input
                type="checkbox"
                checked={selectedCustomerIds.length === customers.length && customers.length > 0}
                onChange={toggleSelectAll}
              />
            </th>
            <th>الاسم</th>
            <th>رقم الهاتف</th>
            <th>التصنيف</th>
            <th>المندوبين</th>
          </tr>
        </thead>
        <tbody>
          {customers.map(customer => (
            <tr key={customer.id}>
              <td>
                <input
                  type="checkbox"
                  checked={selectedCustomerIds.includes(customer.id)}
                  onChange={() => toggleCustomerSelection(customer.id)}
                />
              </td>
              <td>{customer.name}</td>
              <td>{customer.phone}</td>
              <td>{customer.category_name || '-'}</td>
              <td>{customer.assigned_reps_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

---

#### 9.7. Advanced Bulk Actions with Dropdowns

```javascript
function BulkActionsPanel({ selectedCustomerIds, onActionComplete }) {
  const [actionType, setActionType] = useState('');
  const [selectedRepId, setSelectedRepId] = useState('');
  const [selectedCategoryId, setSelectedCategoryId] = useState('');
  const [reps, setReps] = useState([]);
  const [categories, setCategories] = useState([]);
  const [isProcessing, setIsProcessing] = useState(false);
  
  // Load reps and categories on mount
  useEffect(() => {
    loadReps();
    loadCategories();
  }, []);
  
  const executeBulkAction = async () => {
    if (selectedCustomerIds.length === 0) {
      alert('لم يتم تحديد أي عملاء');
      return;
    }
    
    if (!actionType) {
      alert('الرجاء اختيار نوع العملية');
      return;
    }
    
    // Validate required fields based on action
    const requestData = {
      action: actionType,
      customer_ids: selectedCustomerIds
    };
    
    if (actionType === 'assign_rep' || actionType === 'remove_rep') {
      if (!selectedRepId) {
        alert('الرجاء اختيار مندوب');
        return;
      }
      requestData.rep_id = parseInt(selectedRepId);
    }
    
    if (actionType === 'assign_category') {
      if (!selectedCategoryId) {
        alert('الرجاء اختيار تصنيف');
        return;
      }
      requestData.category_id = parseInt(selectedCategoryId);
    }
    
    // Confirm delete action
    if (actionType === 'delete') {
      const confirmed = confirm(
        `هل أنت متأكد من تعطيل ${selectedCustomerIds.length} عميل؟`
      );
      if (!confirmed) return;
    }
    
    setIsProcessing(true);
    
    try {
      const response = await fetch('/api/companies/customers/bulk-action/', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${getAccessToken()}`,
          'X-Company-ID': getCompanyId(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(requestData)
      });
      
      const result = await response.json();
      
      if (result.success) {
        alert(result.message);
        
        // Show details if there were failures
        if (result.data.failed > 0) {
          console.warn(`Failed customer IDs: ${result.data.failed_ids.join(', ')}`);
        }
        
        // Reset form
        setActionType('');
        setSelectedRepId('');
        setSelectedCategoryId('');
        
        // Notify parent to reload data
        onActionComplete();
      } else {
        alert(`خطأ: ${result.message}`);
      }
    } catch (error) {
      alert('حدث خطأ أثناء تنفيذ العملية');
      console.error(error);
    } finally {
      setIsProcessing(false);
    }
  };
  
  return (
    <div className="bulk-actions-panel">
      <h3>عمليات جماعية ({selectedCustomerIds.length} عميل محدد)</h3>
      
      <div className="form-group">
        <label>نوع العملية:</label>
        <select 
          value={actionType} 
          onChange={(e) => setActionType(e.target.value)}
          disabled={isProcessing}
        >
          <option value="">اختر العملية</option>
          <option value="assign_rep">تعيين مندوب</option>
          <option value="assign_category">تعيين تصنيف</option>
          <option value="remove_rep">إزالة مندوب</option>
          <option value="remove_category">إزالة التصنيف</option>
          <option value="delete">تعطيل العملاء</option>
        </select>
      </div>
      
      {(actionType === 'assign_rep' || actionType === 'remove_rep') && (
        <div className="form-group">
          <label>المندوب:</label>
          <select 
            value={selectedRepId} 
            onChange={(e) => setSelectedRepId(e.target.value)}
            disabled={isProcessing}
          >
            <option value="">اختر المندوب</option>
            {reps.map(rep => (
              <option key={rep.id} value={rep.id}>
                {rep.name} ({rep.referral_code})
              </option>
            ))}
          </select>
        </div>
      )}
      
      {actionType === 'assign_category' && (
        <div className="form-group">
          <label>التصنيف:</label>
          <select 
            value={selectedCategoryId} 
            onChange={(e) => setSelectedCategoryId(e.target.value)}
            disabled={isProcessing}
          >
            <option value="">اختر التصنيف</option>
            {categories.map(cat => (
              <option key={cat.id} value={cat.id}>
                {cat.name} {cat.is_global && '(افتراضي)'}
              </option>
            ))}
          </select>
        </div>
      )}
      
      <button 
        onClick={executeBulkAction}
        disabled={isProcessing || selectedCustomerIds.length === 0 || !actionType}
        className={actionType === 'delete' ? 'danger' : 'primary'}
      >
        {isProcessing ? 'جاري التنفيذ...' : 'تنفيذ'}
      </button>
    </div>
  );
}
```

---

#### 9.8. Error Handling for Bulk Actions

**Common Error Responses:**

**Invalid action type:**
```json
{
  "success": false,
  "message": "نوع العملية غير صحيح",
  "errors": {
    "action": ["العملية 'invalid_action' غير مدعومة"]
  }
}
```

**No customers selected:**
```json
{
  "success": false,
  "message": "قائمة العملاء مطلوبة",
  "errors": {
    "customer_ids": ["يجب تقديم قائمة من معرفات العملاء"]
  }
}
```

**Some customers not found:**
```json
{
  "success": false,
  "message": "بعض العملاء غير موجودين",
  "errors": {
    "customer_ids": ["بعض العملاء غير موجودين أو غير نشطين"]
  }
}
```

**Partial Success Handling:**

Even if some operations fail, the response will indicate which succeeded:

```javascript
const result = await performBulkAction('assign_rep', { rep_id: 10 });

if (result.success) {
  const { total, successful, failed, failed_ids } = result.data;
  
  if (failed > 0) {
    // Some operations failed
    alert(`نجح: ${successful}/${total}. فشل: ${failed} عميل`);
    console.log('Failed customer IDs:', failed_ids);
  } else {
    // All succeeded
    alert(`تمت العملية بنجاح على ${successful} عميل`);
  }
}
```

---

## Important Notes for Frontend Developers

### 1. Per-Company Context
- All category-related data is **per-company**
- `category_details` in customer responses reflects **your company's assignment**
- Different companies see different categories for the same customer
- Always include `X-Company-ID` header in requests

### 2. Category Types
- **Global categories** (`is_global: true`): Read-only, available to all companies
- **Custom categories** (`is_custom: true`): Created by your company, editable/deletable

### 3. Best Practices
- Cache categories list locally (they don't change frequently)
- Show visual distinction between global and custom categories in UI
- Allow inline category creation from customer form
- Use category filter to segment customer lists
- Handle `null` category gracefully (customer has no category from your company)

### 4. Error Handling
- Always check `result.success` in responses
- Display `result.message` or `result.errors` to users
- Handle 403 errors when trying to edit/delete global categories
- Handle 400 errors for duplicate category names

---

## Summary

**Category Management:**
- `GET /api/companies/customer-categories` - List categories
- `POST /api/companies/customer-categories` - Create custom category
- `PATCH /api/companies/customer-categories/{id}` - Update custom category
- `DELETE /api/companies/customer-categories/{id}` - Delete custom category

**Customer Management:**
- `POST /api/companies/customers` - Create customer with category
- `PATCH /api/companies/customers/{id}` - Update customer category
- `GET /api/companies/customers?category_id={id}` - Filter by category
- `GET /api/companies/customers/{id}` - Get customer with category details

**Key Takeaways:**
- Categories are assigned **per company** to customers
- Same customer = different categories from different companies
- Global defaults + custom categories available
- All operations are scoped to your company context
