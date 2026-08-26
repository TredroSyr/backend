# Products App API Documentation

## Overview

The Products app provides a complete API for managing products, categories, pricing, images, custom fields, and warehouse inventory. All endpoints are company-scoped, meaning users can only access data belonging to their own company.

## Authentication

All endpoints require authentication via JWT token. Include the token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

The JWT token contains `company_id` which is automatically extracted by middleware to scope all queries.

## Base URL

All endpoints are prefixed with: `/api`

---

## Common Lookup Tables (Global)

### Unit of Measure

#### List Units of Measure
```http
GET /api/units-of-measure/
```

**Query Parameters:**
- `show_all` (optional): `true` to include inactive units, default is `false`

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "units": [
      {
        "id": 1,
        "code": "kg",
        "name": "Kilogram",
        "is_active": true
      },
      {
        "id": 2,
        "code": "liter",
        "name": "Liter",
        "is_active": true
      }
    ]
  }
}
```

#### Get Unit of Measure Details
```http
GET /api/units-of-measure/{id}/
```

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "unit": {
      "id": 1,
      "code": "kg",
      "name": "Kilogram",
      "is_active": true
    }
  }
}
```

---

### Currency

#### List Currencies
```http
GET /api/currencies/
```

**Query Parameters:**
- `show_all` (optional): `true` to include inactive currencies

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "currencies": [
      {
        "id": 1,
        "code": "USD",
        "name": "US Dollar",
        "symbol": "$",
        "is_active": true
      },
      {
        "id": 2,
        "code": "EUR",
        "name": "Euro",
        "symbol": "€",
        "is_active": true
      }
    ]
  }
}
```

---

## Product Categories

### List Product Categories
```http
GET /api/companies/product-categories/
```

**Query Parameters:**
- `is_active` (optional): `true` or `false`
- `parent_id` (optional): Filter by parent category ID, empty string for root categories
- `search` (optional): Search by name

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "categories": [
      {
        "id": 1,
        "name": "Electronics",
        "parent": null,
        "parent_name": null,
        "children_count": 3,
        "is_active": true,
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z"
      },
      {
        "id": 2,
        "name": "Laptops",
        "parent": 1,
        "parent_name": "Electronics",
        "children_count": 0,
        "is_active": true,
        "created_at": "2026-08-20T10:05:00Z",
        "updated_at": "2026-08-20T10:05:00Z"
      }
    ]
  }
}
```

### Create Product Category
```http
POST /api/companies/product-categories/
```

**Request Body:**
```json
{
  "name": "Smartphones",
  "parent": 1,
  "is_active": true
}
```

**Response:**
```json
{
  "success": true,
  "message": "تم إنشاء التصنيف بنجاح",
  "data": {
    "category": {
      "id": 3,
      "name": "Smartphones",
      "parent": 1,
      "parent_name": "Electronics",
      "children_count": 0,
      "is_active": true,
      "created_at": "2026-08-26T15:00:00Z",
      "updated_at": "2026-08-26T15:00:00Z"
    }
  }
}
```

### Update Product Category
```http
PATCH /api/companies/product-categories/{id}/
```

**Request Body:**
```json
{
  "name": "Mobile Phones",
  "is_active": true
}
```

### Delete Product Category (Soft Delete)
```http
DELETE /api/companies/product-categories/{id}/
```

**Response:**
```json
{
  "success": true,
  "message": "تم حذف التصنيف بنجاح"
}
```

---

## Products

### List Products (Lightweight)
```http
GET /api/companies/products/
```

**Query Parameters:**
- `category` (optional): Filter by category ID
- `is_active` (optional): `true` or `false`
- `is_sellable` (optional): `true` or `false`
- `is_purchasable` (optional): `true` or `false`
- `brand` (optional): Filter by brand (exact match)
- `search` (optional): Search by name, SKU, or barcode
- `ordering` (optional): Sort field (`name`, `-name`, `created_at`, `-created_at`, `sku`, `-sku`)

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "products": [
      {
        "id": 1,
        "name": "Laptop Dell XPS 15",
        "sku": "DELL-XPS-15",
        "barcode": "1234567890123",
        "brand": "Dell",
        "category": 2,
        "category_name": "Laptops",
        "unit": 1,
        "unit_name": "Piece",
        "is_active": true,
        "is_sellable": true,
        "is_purchasable": true,
        "primary_image": {
          "id": 1,
          "image": "/media/products/dell-xps-15.jpg",
          "alt_text": "Dell XPS 15"
        },
        "default_price": {
          "price": "1500.00",
          "currency_code": "USD",
          "currency_symbol": "$",
          "price_type": "standard"
        },
        "created_at": "2026-08-25T10:00:00Z"
      }
    ]
  }
}
```

### Get Product Details (Full)
```http
GET /api/companies/products/{id}/
```

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "product": {
      "id": 1,
      "name": "Laptop Dell XPS 15",
      "description": "High-performance laptop with 15-inch display",
      "sku": "DELL-XPS-15",
      "barcode": "1234567890123",
      "brand": "Dell",
      "category": 2,
      "category_name": "Laptops",
      "unit": 1,
      "unit_name": "Piece",
      "unit_code": "pcs",
      "weight": "2.500",
      "weight_unit": "kg",
      "length": "35.000",
      "width": "25.000",
      "height": "2.000",
      "dimension_unit": "cm",
      "reorder_point": "10.000",
      "reorder_quantity": "50.000",
      "is_taxable": true,
      "tax_rate": "10.00",
      "is_sellable": true,
      "is_purchasable": true,
      "external_reference": "EXT-12345",
      "notes": "Premium model",
      "is_active": true,
      "images": [
        {
          "id": 1,
          "image": "/media/products/dell-xps-15.jpg",
          "alt_text": "Dell XPS 15",
          "is_primary": true,
          "sort_order": 0,
          "created_at": "2026-08-25T10:10:00Z",
          "updated_at": "2026-08-25T10:10:00Z"
        }
      ],
      "prices": [
        {
          "id": 1,
          "currency": 1,
          "currency_code": "USD",
          "currency_symbol": "$",
          "price_type": "standard",
          "customer_category": null,
          "customer_category_name": null,
          "price": "1500.00",
          "is_default": true,
          "valid_from": null,
          "valid_until": null,
          "created_at": "2026-08-25T10:15:00Z",
          "updated_at": "2026-08-25T10:15:00Z"
        },
        {
          "id": 2,
          "currency": 1,
          "currency_code": "USD",
          "currency_symbol": "$",
          "price_type": "standard",
          "customer_category": 5,
          "customer_category_name": "Wholesale",
          "price": "1300.00",
          "is_default": false,
          "valid_from": null,
          "valid_until": null,
          "created_at": "2026-08-25T10:16:00Z",
          "updated_at": "2026-08-25T10:16:00Z"
        }
      ],
      "custom_fields": {
        "warranty_months": "24",
        "processor": "Intel Core i7"
      },
      "created_at": "2026-08-25T10:00:00Z",
      "updated_at": "2026-08-25T10:00:00Z"
    }
  }
}
```

### Create Product
```http
POST /api/companies/products/
```

**Request Body:**
```json
{
  "name": "Laptop Dell XPS 15",
  "description": "High-performance laptop",
  "sku": "DELL-XPS-15",
  "barcode": "1234567890123",
  "brand": "Dell",
  "category": 2,
  "unit": 1,
  "weight": "2.500",
  "weight_unit": "kg",
  "is_taxable": true,
  "tax_rate": "10.00",
  "is_sellable": true,
  "is_purchasable": true,
  "custom_fields": {
    "warranty_months": "24",
    "processor": "Intel Core i7"
  }
}
```

**Response:**
```json
{
  "success": true,
  "message": "تم إنشاء المنتج بنجاح",
  "data": {
    "product": {
      "id": 1,
      "name": "Laptop Dell XPS 15",
      ...
    }
  }
}
```

### Update Product
```http
PATCH /api/companies/products/{id}/
```

**Request Body (partial update):**
```json
{
  "name": "Dell XPS 15 - Updated",
  "custom_fields": {
    "warranty_months": "36"
  }
}
```

### Resolve Product Price
```http
GET /api/companies/products/{id}/resolved-price/?currency=1&customer_category=5&price_type=standard
```

**Query Parameters:**
- `currency` (required): Currency ID
- `customer_category` (optional): Customer category ID
- `price_type` (optional): Price type, default is `standard`

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "price": "1300.00",
    "currency": {
      "id": 1,
      "code": "USD",
      "symbol": "$"
    },
    "price_type": "standard",
    "is_default": false,
    "is_category_specific": true,
    "customer_category": {
      "id": 5,
      "name": "Wholesale"
    },
    "valid_from": null,
    "valid_until": null
  }
}
```

**Price Resolution Logic:**
1. If `customer_category` is provided, look for category-specific price
2. Fall back to general price (no customer_category)
3. Return 404 if no matching price found

---

## Product Images (Nested)

### List Product Images
```http
GET /api/companies/products/{product_id}/images/
```

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "images": [
      {
        "id": 1,
        "image": "/media/products/laptop-1.jpg",
        "alt_text": "Front view",
        "is_primary": true,
        "sort_order": 0,
        "created_at": "2026-08-25T10:10:00Z",
        "updated_at": "2026-08-25T10:10:00Z"
      }
    ]
  }
}
```

### Upload Product Image
```http
POST /api/companies/products/{product_id}/images/
Content-Type: multipart/form-data
```

**Request Body:**
```
image: <file>
alt_text: "Front view"
is_primary: true
sort_order: 0
```

**Notes:**
- First image uploaded is automatically set as primary
- Setting `is_primary=true` automatically unsets other primary images

### Update Product Image
```http
PATCH /api/companies/products/{product_id}/images/{id}/
```

**Request Body:**
```json
{
  "is_primary": true,
  "alt_text": "Updated description"
}
```

### Delete Product Image
```http
DELETE /api/companies/products/{product_id}/images/{id}/
```

---

## Product Prices (Nested)

### List Product Prices
```http
GET /api/companies/products/{product_id}/prices/
```

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "prices": [
      {
        "id": 1,
        "currency": 1,
        "currency_code": "USD",
        "currency_symbol": "$",
        "price_type": "standard",
        "customer_category": null,
        "customer_category_name": null,
        "price": "1500.00",
        "is_default": true,
        "valid_from": null,
        "valid_until": null,
        "created_at": "2026-08-25T10:15:00Z",
        "updated_at": "2026-08-25T10:15:00Z"
      }
    ]
  }
}
```

### Create Product Price
```http
POST /api/companies/products/{product_id}/prices/
```

**Request Body:**
```json
{
  "currency": 1,
  "price_type": "standard",
  "customer_category": null,
  "price": "1500.00",
  "is_default": true,
  "valid_from": "2026-09-01T00:00:00Z",
  "valid_until": null
}
```

**Validation Rules:**
- Only one general price per `(currency, price_type)` combination
- Only one category-specific price per `(currency, price_type, customer_category)`
- Only one `is_default=true` price per product (must be general, not category-specific)
- `is_default` price cannot have a `customer_category`

### Update Product Price
```http
PATCH /api/companies/products/{product_id}/prices/{id}/
```

### Delete Product Price
```http
DELETE /api/companies/products/{product_id}/prices/{id}/
```

---

## Product Warehouse Stock (Read-Only)

### List Stock by Product
```http
GET /api/companies/products/{product_id}/warehouse-stock/
```

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "stock": [
      {
        "id": 1,
        "warehouse": 1,
        "warehouse_name": "Main Warehouse",
        "product": 1,
        "product_name": "Laptop Dell XPS 15",
        "product_sku": "DELL-XPS-15",
        "quantity": "150.000",
        "created_at": "2026-08-25T10:00:00Z",
        "updated_at": "2026-08-25T12:00:00Z"
      }
    ]
  }
}
```

### List Stock by Warehouse
```http
GET /api/companies/warehouses/{warehouse_id}/product-stock/
```

**Note:** Stock quantities are read-only projections from `StockMovement` records. To modify stock, create stock movements through the orders/invoices apps.

---

## Custom Field Definitions

### List Custom Field Definitions
```http
GET /api/companies/custom-field-definitions/
```

**Query Parameters:**
- `is_active` (optional): `true` or `false`

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "definitions": [
      {
        "id": 1,
        "key": "warranty_months",
        "label": "Warranty (Months)",
        "is_active": true,
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z"
      },
      {
        "id": 2,
        "key": "processor",
        "label": "Processor Type",
        "is_active": true,
        "created_at": "2026-08-20T10:01:00Z",
        "updated_at": "2026-08-20T10:01:00Z"
      }
    ]
  }
}
```

### Create Custom Field Definition
```http
POST /api/companies/custom-field-definitions/
```

**Request Body:**
```json
{
  "key": "warranty_months",
  "label": "Warranty (Months)",
  "is_active": true
}
```

**Notes:**
- `key` must be unique within the company (slug format recommended)
- Once defined, custom fields can be used on any product via the `custom_fields` dict

---

## Warehouses

### List Warehouses
```http
GET /api/companies/warehouses/
```

**Query Parameters:**
- `is_active` (optional): `true` or `false`
- `owner_type` (optional): `company` or `rep`

**Response:**
```json
{
  "success": true,
  "message": "",
  "data": {
    "warehouses": [
      {
        "id": 1,
        "name": "Main Warehouse",
        "address": "123 Main St, City",
        "kind": "central",
        "owner_type": "company",
        "rep": null,
        "rep_name": null,
        "is_active": true,
        "created_at": "2026-08-20T10:00:00Z",
        "updated_at": "2026-08-20T10:00:00Z"
      }
    ]
  }
}
```

### Create Warehouse
```http
POST /api/companies/warehouses/
```

**Request Body:**
```json
{
  "name": "Main Warehouse",
  "address": "123 Main St, City",
  "kind": "central",
  "owner_type": "company",
  "rep": null,
  "is_active": true
}
```

**Validation Rules:**
- If `owner_type` is `company`, `rep` must be `null`
- If `owner_type` is `rep`, `rep` must be set to a valid rep ID from the company

---

## Error Responses

All endpoints return errors in a consistent format:

```json
{
  "success": false,
  "message": "بيانات غير صالحة",
  "errors": {
    "sku": ["رمز المنتج (SKU) مستخدم بالفعل"],
    "category": ["التصنيف يجب أن ينتمي لنفس الشركة"]
  }
}
```

### Common HTTP Status Codes

- `200 OK` - Successful GET, PATCH, DELETE
- `201 Created` - Successful POST
- `400 Bad Request` - Validation errors
- `401 Unauthorized` - Missing or invalid authentication
- `403 Forbidden` - Insufficient permissions
- `404 Not Found` - Resource not found or not in company scope
- `500 Internal Server Error` - Server error

---

## Data Constraints & Business Rules

### Product Categories
- Must belong to the same company as the parent (if parent is set)
- Cannot be its own parent (circular reference prevention)

### Products
- `sku` must be unique within the company (if provided)
- `category` must belong to the same company (if provided)
- `unit` must be an active unit from the global catalog

### Product Images
- Only one primary image per product
- First image uploaded is automatically set as primary
- Setting a new primary image unsets the previous one

### Product Prices
- Only one general price per `(product, currency, price_type)` combination
- Only one category-specific price per `(product, currency, price_type, customer_category)`
- Only one `is_default` price per product (must be general, not category-specific)
- `is_default` price cannot have a `customer_category` set

### Custom Fields
- `key` must be unique within the company
- Keys must be defined before they can be used on products
- Values are stored as text (application layer handles type conversion)

---

## Performance Optimizations

The API implements several optimizations to avoid N+1 queries:

- Product list: Uses `select_related("category", "unit")` and prefetches primary image and default price
- Product detail: Prefetches `images`, `prices` with related currency/category, and `custom_field_values`
- All list endpoints support pagination via DRF's pagination classes
- Filtering and search use indexed database fields

---

## Integration Notes

### For Order/Invoice Creation

Use the price resolution endpoint or service to get the correct price for a product:

```python
from apps.products.services.pricing import resolve_product_price

price_info = resolve_product_price(
    product=product,
    currency=currency,
    customer_category=customer.get_category_for_company(company_id),
    price_type="standard"
)

# Returns price with fallback logic
```

### For Stock Management

Stock quantities in `ProductWarehouseStock` are read-only projections. To modify stock:

1. Create `StockMovement` records via the orders/invoices apps
2. The quantity will be automatically updated (via signals or periodic sync)

### Custom Fields Usage

1. Define custom field definitions first
2. Use them on products via the `custom_fields` dict in create/update requests
3. Values are returned as a flat dict in product detail responses

---

## Testing

Run the test suite:

```bash
pytest apps/products/tests/
```

Tests cover:
- Company scoping (cross-company access prevention)
- Primary image and default price uniqueness validation
- Price resolution fallback logic
- Tax calculations

---

## Support

For issues or questions, please contact the backend team or refer to the main project documentation.
