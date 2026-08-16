# Company Onboarding Implementation Summary

## Overview
This document summarizes the implementation of the simplified company onboarding feature.

## Design Philosophy
Instead of implementing 4 separate endpoints for each onboarding step, we implemented a **single, flexible endpoint** where:
- ✅ All fields are optional
- ✅ Frontend collects data across multiple UI steps
- ✅ Single submission at the end (or skip entirely)
- ✅ Can be completed later via company profile

## Implementation Details

### 1. Files Created

#### `apps/companies/views.py` (New)
Four view classes implementing the onboarding functionality:

1. **CompanyOnboardingView** (`POST /api/companies/onboarding`)
   - Single endpoint for all onboarding data
   - All fields optional (logo, cover, governorate, region, description, business_type)
   - Marks onboarding as completed when called
   - Updates company record with provided data
   - Returns updated company serializer data

2. **CompanyOnboardingStatusView** (`GET /api/companies/onboarding/status`)
   - Returns company data and onboarding status
   - Used by frontend to check if onboarding is needed

3. **CompanyLocationsView** (`GET /api/companies/locations`)
   - Returns list of Syrian governorates with regions
   - Hardcoded data (no DB queries needed)
   - 14 governorates with multiple regions each

4. **CompanyBusinessTypesView** (`GET /api/companies/business-types`)
   - Returns available business type options
   - Matches Company model choices
   - 6 business types (food, electronics, cosmetics, medical, home, clothing)

#### `apps/companies/urls.py` (New)
URL routing configuration for companies app:
- `/api/companies/onboarding` - POST - Submit onboarding data
- `/api/companies/onboarding/status` - GET - Check onboarding status
- `/api/companies/locations` - GET - Get location options
- `/api/companies/business-types` - GET - Get business type options

#### `apps/companies/serializers.py` (Updated)
Added `CompanyOnboardingSerializer`:
- All fields optional (partial=True)
- Handles logo, cover, governorate, region, description, business_type
- Automatically marks onboarding_completed=True on save
- Sets onboarding_completed_at timestamp

#### `config/urls.py` (Updated)
- Added companies app URLs: `path("api/", include("apps.companies.urls"))`
- Added media file serving for development mode

### 2. Existing Models Used

The `Company` model already had all required fields:
```python
# Onboarding fields (already existed)
logo = models.FileField(upload_to="companies/logos/", null=True, blank=True)
cover = models.FileField(upload_to="companies/covers/", null=True, blank=True)
governorate = models.CharField(max_length=100, null=True, blank=True)
region = models.CharField(max_length=100, null=True, blank=True)
description = models.TextField(max_length=500, null=True, blank=True)
business_type = models.CharField(max_length=50, null=True, blank=True, choices=[...])
onboarding_completed = models.BooleanField(default=False)
onboarding_completed_at = models.DateTimeField(null=True, blank=True)
```

No database migrations needed!

### 3. Authentication & Permissions

All endpoints require authentication:
- Uses `IsAuthenticated` permission class
- Company ID extracted from JWT token via `TenantScopingMiddleware`
- Middleware already configured in settings
- Each request is automatically scoped to the authenticated user's company

### 4. File Upload Handling

File uploads handled via `multipart/form-data`:
- Logo: max 2MB, formats: PNG, JPG, JPEG, SVG
- Cover: max 5MB, formats: PNG, JPG, JPEG
- Stored in: `MEDIA_ROOT/companies/logos/` and `MEDIA_ROOT/companies/covers/`
- Media serving configured for development mode

### 5. Location Data

Syrian governorates and regions (14 governorates):
1. دمشق - 12 regions
2. ريف دمشق - 13 regions
3. حلب - 9 regions
4. حمص - 8 regions
5. حماة - 7 regions
6. اللاذقية - 4 regions
7. طرطوس - 5 regions
8. إدلب - 6 regions
9. درعا - 6 regions
10. السويداء - 5 regions
11. القنيطرة - 3 regions
12. دير الزور - 5 regions
13. الرقة - 4 regions
14. الحسكة - 6 regions

### 6. Business Types

Six business type options:
1. `food_products` - مواد غذائية
2. `electronics` - إلكترونيات
3. `cosmetics` - مستحضرات تجميل
4. `medical_supplies` - أدوية ومستلزمات طبية
5. `home_tools` - أدوات منزلية
6. `clothing` - ألبسة

## API Endpoints Summary

### POST /api/companies/onboarding
**Purpose**: Submit onboarding data (all fields optional)

**Request**: `multipart/form-data`
```
logo: File (optional)
cover: File (optional)
governorate: string (optional)
region: string (optional)
description: string (optional, max 500 chars)
business_type: string (optional)
```

**Response**: 200 OK
```json
{
  "success": true,
  "message": "تم حفظ بيانات الشركة بنجاح",
  "data": {
    "company": { /* full company object */ }
  }
}
```

### GET /api/companies/onboarding/status
**Purpose**: Check if onboarding is completed

**Response**: 200 OK
```json
{
  "success": true,
  "data": {
    "onboarding_completed": false,
    "company": { /* full company object */ }
  }
}
```

### GET /api/companies/locations
**Purpose**: Get governorates and regions list

**Response**: 200 OK
```json
{
  "success": true,
  "data": {
    "locations": [
      {
        "governorate": "دمشق",
        "regions": ["المزة", "المالكي", ...]
      }
    ]
  }
}
```

### GET /api/companies/business-types
**Purpose**: Get business type options

**Response**: 200 OK
```json
{
  "success": true,
  "data": {
    "business_types": [
      {
        "value": "food_products",
        "label": "مواد غذائية"
      }
    ]
  }
}
```

## Frontend Integration Guide

### Recommended Flow

1. **After Signup/Login**
   - Check `company.onboarding_completed` in response
   - If `false`, show onboarding UI

2. **Onboarding Steps** (Frontend State Management)
   - Step 1: Collect logo/cover files
   - Step 2: Fetch locations, let user select
   - Step 3: Collect description
   - Step 4: Fetch business types, let user select
   - Store all in frontend state (don't submit per step)

3. **Submit or Skip**
   - On final step: Submit all collected data
   - On skip: Submit empty request
   - Both mark onboarding as completed

4. **Edit Later**
   - Same endpoint can update company profile
   - All fields remain optional

### Example Code

```javascript
// Fetch reference data
const locations = await fetch('/api/companies/locations', {
  headers: { Authorization: `Bearer ${token}` }
});

const businessTypes = await fetch('/api/companies/business-types', {
  headers: { Authorization: `Bearer ${token}` }
});

// Submit onboarding (on final step or skip)
const formData = new FormData();
if (logo) formData.append('logo', logo);
if (cover) formData.append('cover', cover);
if (governorate) formData.append('governorate', governorate);
if (region) formData.append('region', region);
if (description) formData.append('description', description);
if (businessType) formData.append('business_type', businessType);

const response = await fetch('/api/companies/onboarding', {
  method: 'POST',
  headers: { Authorization: `Bearer ${token}` },
  body: formData
});
```

## Benefits

1. **Flexibility**: Users can skip and complete later
2. **Simplicity**: One endpoint vs four
3. **Performance**: Single request vs sequential requests
4. **UX**: No partial failure states
5. **Idempotent**: Can call multiple times to update
6. **Frontend Control**: UI steps managed in frontend

## Testing Checklist

- [ ] Complete onboarding with all fields
- [ ] Skip onboarding (empty submission)
- [ ] Partial onboarding (some fields only)
- [ ] File upload validation (size, format)
- [ ] Invalid governorate/region combinations
- [ ] Invalid business type
- [ ] Description max length (500 chars)
- [ ] Unauthorized access (no token)
- [ ] Status check after completion
- [ ] Edit profile after initial onboarding

## Documentation

Full API specification available in:
- `docs/api_auth_endpoints.md` - Complete API documentation with examples

## Notes

- All endpoints require authentication (JWT token)
- Company ID extracted from token automatically
- Media files served in development mode only
- Production should use CDN/S3 for media files
- All fields nullable in database (can be added later)
- No migrations needed (fields already existed)

## Version

**Version**: 1.0  
**Implemented**: August 16, 2026  
**Status**: ✅ Complete and Ready
