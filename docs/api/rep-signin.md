# Rep Sign-In API Documentation

## Overview
API endpoint for sales representative (rep) authentication. Reps use their phone number and password to sign in and receive JWT tokens for accessing company resources.

---

## Endpoint

**URL:** `POST /api/auth/rep/signin`

**Authentication:** Not required (public endpoint)

---

## Request

### Headers
```
Content-Type: application/json
```

### Request Body
```json
{
  "phone": "0955123456",
  "password": "RepSecurePass123"
}
```

### Field Requirements

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `phone` | string | Yes | Rep's phone number (will be auto-normalized) |
| `password` | string | Yes | Rep's password |

---

## Response

### Success Response (200 OK)

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
        "name": "شركة التوزيع الرائدة",
        "slug": "leading-distribution",
        "currency": "SYP",
        "is_active": true,
        "logo": null,
        "cover": null,
        "governorate": "دمشق",
        "region": "المزة",
        "description": "شركة توزيع منتجات غذائية",
        "business_type": "food_products",
        "onboarding_completed": true,
        "created_at": "2024-01-10T08:00:00Z"
      }
    },
    "tokens": {
      "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
      "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."
    }
  }
}
```

### Error Responses

#### 400 Bad Request - Validation Error
```json
{
  "success": false,
  "message": "بيانات الدخول غير صحيحة",
  "errors": {
    "phone": ["هذا الحقل مطلوب"],
    "password": ["هذا الحقل مطلوب"]
  }
}
```

#### 401 Unauthorized - Invalid Credentials
```json
{
  "success": false,
  "message": "رقم الهاتف أو كلمة المرور غير صحيحة",
  "errors": {
    "credentials": ["بيانات الدخول غير صحيحة"]
  }
}
```

#### 403 Forbidden - Inactive Rep Account
```json
{
  "success": false,
  "message": "الحساب غير نشط",
  "errors": {
    "account": ["تم تعطيل هذا الحساب. يرجى التواصل مع إدارة الشركة"]
  }
}
```

#### 403 Forbidden - Inactive Company
```json
{
  "success": false,
  "message": "حساب الشركة غير نشط",
  "errors": {
    "account": ["تم تعطيل حساب الشركة"]
  }
}
```

---

## Response Fields

### Rep Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Unique rep identifier |
| `name` | string | Rep's full name |
| `phone` | string | Normalized phone number (+963...) |
| `referral_code` | string | Unique referral code for customer acquisition |
| `is_active` | boolean | Rep's active status |
| `company` | object | Full company details (see below) |

### Company Object

| Field | Type | Description |
|-------|------|-------------|
| `id` | integer | Company identifier |
| `name` | string | Company name |
| `slug` | string | URL-friendly company identifier |
| `currency` | string | Company currency (ISO 4217 code) |
| `is_active` | boolean | Company active status |
| `logo` | string/null | Company logo URL |
| `cover` | string/null | Company cover image URL |
| `governorate` | string/null | Company governorate/province |
| `region` | string/null | Company region/city |
| `description` | string/null | Company description |
| `business_type` | string/null | Type of business |
| `onboarding_completed` | boolean | Whether onboarding is complete |
| `created_at` | datetime | Company creation timestamp |

### Tokens Object

| Field | Type | Description |
|-------|------|-------------|
| `access` | string | JWT access token (valid for 1 hour) |
| `refresh` | string | JWT refresh token (valid for 7 days) |

---

## JWT Token Claims

The access token contains the following custom claims:

```json
{
  "actor_type": "rep",
  "company_id": 1,
  "rep_id": 1,
  "user_id": 1,
  "exp": 1705839600,
  "iat": 1705836000
}
```

### Claim Descriptions

| Claim | Description |
|-------|-------------|
| `actor_type` | Always "rep" for rep authentication |
| `company_id` | ID of the company the rep belongs to |
| `rep_id` | Rep's unique identifier |
| `user_id` | Same as rep_id (for compatibility) |
| `exp` | Token expiration timestamp |
| `iat` | Token issued at timestamp |

---

## Phone Number Normalization

Phone numbers are automatically normalized to the Syrian international format:

### Accepted Input Formats
- `0955123456` → `+963955123456`
- `955123456` → `+963955123456`
- `963955123456` → `+963955123456`
- `+963955123456` → `+963955123456` (already normalized)
- `00963955123456` → `+963955123456`

### Validation Rules
- Must result in format: `+963XXXXXXXXX` (country code + 9 digits)
- Spaces and dashes are automatically removed
- Invalid formats will return a 401 error

---

## Authentication Flow

```
1. Rep submits phone + password
   ↓
2. System normalizes phone number
   ↓
3. System looks up rep by phone
   ↓
4. System verifies password (PBKDF2 hash)
   ↓
5. System checks rep.is_active = true
   ↓
6. System checks rep.company.is_active = true
   ↓
7. System generates JWT tokens with custom claims
   ↓
8. Returns rep details + tokens
```

---

## Security Features

1. **Password Hashing**: All passwords are hashed using Django's PBKDF2 algorithm
2. **Never Exposed**: Passwords are never returned in API responses
3. **Account Status Checks**: Both rep and company must be active
4. **JWT Security**: Tokens are signed and include expiration timestamps
5. **Tenant Scoping**: Token includes `company_id` for automatic tenant isolation

---

## Code Examples

### cURL
```bash
curl -X POST https://your-domain.com/api/auth/rep/signin \
  -H "Content-Type: application/json" \
  -d '{
    "phone": "0955123456",
    "password": "RepSecurePass123"
  }'
```

### JavaScript (Fetch API)
```javascript
fetch('https://your-domain.com/api/auth/rep/signin', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    phone: '0955123456',
    password: 'RepSecurePass123'
  })
})
.then(response => response.json())
.then(data => {
  if (data.success) {
    // Store tokens
    localStorage.setItem('access_token', data.data.tokens.access);
    localStorage.setItem('refresh_token', data.data.tokens.refresh);
    
    // Store rep info
    localStorage.setItem('rep_id', data.data.rep.id);
    localStorage.setItem('company_id', data.data.rep.company.id);
    
    console.log('Logged in as:', data.data.rep.name);
    console.log('Company:', data.data.rep.company.name);
    console.log('Referral code:', data.data.rep.referral_code);
  } else {
    console.error('Login failed:', data.message);
  }
})
.catch(error => console.error('Error:', error));
```

### JavaScript (Axios)
```javascript
axios.post('https://your-domain.com/api/auth/rep/signin', {
  phone: '0955123456',
  password: 'RepSecurePass123'
})
.then(response => {
  const { rep, tokens } = response.data.data;
  
  // Store tokens
  localStorage.setItem('access_token', tokens.access);
  localStorage.setItem('refresh_token', tokens.refresh);
  
  // Use rep data
  console.log('Welcome', rep.name);
  console.log('Your referral code:', rep.referral_code);
})
.catch(error => {
  if (error.response) {
    console.error('Login failed:', error.response.data.message);
  }
});
```

### Python (Requests)
```python
import requests

url = "https://your-domain.com/api/auth/rep/signin"
payload = {
    "phone": "0955123456",
    "password": "RepSecurePass123"
}

response = requests.post(url, json=payload)
data = response.json()

if data.get("success"):
    rep = data["data"]["rep"]
    tokens = data["data"]["tokens"]
    
    print(f"Logged in as: {rep['name']}")
    print(f"Company: {rep['company']['name']}")
    print(f"Access token: {tokens['access']}")
else:
    print(f"Login failed: {data.get('message')}")
```

---

## Using the Access Token

After successful authentication, include the access token in the `Authorization` header for all subsequent API requests:

```javascript
fetch('https://your-domain.com/api/some-protected-endpoint', {
  method: 'GET',
  headers: {
    'Authorization': `Bearer ${accessToken}`,
    'Content-Type': 'application/json'
  }
})
```

---

## Token Refresh

When the access token expires (after 1 hour), use the refresh token to obtain a new access token:

**Endpoint:** `POST /api/auth/token/refresh`

**Request:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "تم تحديث الرمز بنجاح",
  "data": {
    "access": "eyJ0eXAiOiJKV1QiLCJhbGc..."
  }
}
```

---

## Sign Out

To sign out, call the signout endpoint (client-side token removal is also recommended):

**Endpoint:** `POST /api/auth/signout`

**Request:**
```json
{
  "refresh": "eyJ0eXAiOiJKV1QiLCJhbGc..."
}
```

**Response:**
```json
{
  "success": true,
  "message": "تم تسجيل الخروج بنجاح"
}
```

**Note:** Also remove tokens from local storage on the client side.

---

## Common Issues & Troubleshooting

### Issue: "رقم الهاتف أو كلمة المرور غير صحيحة"
**Possible Causes:**
- Incorrect phone number or password
- Phone number not properly formatted
- Rep account doesn't exist

**Solutions:**
- Verify credentials with company admin
- Ensure phone number matches registered format
- Check if account was created

### Issue: "الحساب غير نشط"
**Cause:** Rep account has been deactivated by company admin

**Solution:** Contact company administrator to reactivate the account

### Issue: "حساب الشركة غير نشط"
**Cause:** The company account has been suspended or deactivated

**Solution:** Company owner should contact support

### Issue: Token expired
**Cause:** Access token is valid for only 1 hour

**Solution:** Use the refresh token to get a new access token

---

## Error Codes Summary

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 200 | Success | Continue with tokens |
| 400 | Bad request | Check request format and required fields |
| 401 | Unauthorized | Verify credentials |
| 403 | Forbidden | Check account/company status |
| 500 | Server error | Contact support |

---

## Business Logic Notes

1. **No Self-Service Password Reset**: Reps cannot reset their own passwords. Company admins must reset passwords through the company dashboard.

2. **Company Scoping**: All rep operations are automatically scoped to their company via the `company_id` in the JWT token.

3. **Referral Code Usage**: The `referral_code` returned can be shared with customers for automatic rep assignment during customer signup.

4. **Account Deactivation**: Deactivated reps cannot sign in. Company admins can reactivate accounts as needed.

5. **Company Status**: If a company account is deactivated, all its reps are effectively unable to sign in, even if their individual accounts are active.

---

## Related Endpoints

- [Company Sign-In](./company-signin.md) - For company users (owners/staff)
- [Customer Sign-In](./customers-api.md#2-customer-signin) - For customers
- [Token Refresh](./auth-api.md#token-refresh) - To refresh expired tokens
- [Rep Management](./reps-api.md) - CRUD operations for reps

---

## Support

For authentication issues or questions, contact your company administrator or technical support.
