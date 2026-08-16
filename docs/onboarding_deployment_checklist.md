# Company Onboarding - Deployment Checklist

## Pre-Deployment Verification

### ✅ Code Quality
- [x] Python syntax validated (py_compile passed)
- [x] All imports correctly structured
- [x] Views follow DRF conventions
- [x] Serializers properly configured
- [x] URL patterns correctly defined

### ✅ Files Modified/Created
- [x] `apps/companies/views.py` - Created (4 view classes)
- [x] `apps/companies/urls.py` - Created (4 URL patterns)
- [x] `apps/companies/serializers.py` - Updated (added CompanyOnboardingSerializer)
- [x] `config/urls.py` - Updated (added companies app URLs and media serving)
- [x] `docs/api_auth_endpoints.md` - Updated (added simplified onboarding docs)
- [x] `docs/onboarding_implementation_summary.md` - Created
- [x] `docs/onboarding_deployment_checklist.md` - Created

## Deployment Steps

### 1. Environment Setup
```bash
# No new environment variables needed
# Existing .env should have:
# - SECRET_KEY
# - DATABASE_URL
# - ALLOWED_HOSTS
```

### 2. Install Dependencies
```bash
# All required packages already in requirements.txt:
# - Django
# - djangorestframework
# - djangorestframework-simplejwt
# - Pillow (for image handling)

pip install -r requirements.txt
```

### 3. Database Migrations
```bash
# No new migrations needed!
# Company model already has all onboarding fields from previous migration:
# - apps/companies/migrations/0002_add_onboarding_fields.py

# Just ensure migrations are up to date:
python manage.py migrate
```

### 4. Media File Storage

#### Development
```python
# Already configured in settings/base.py:
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# Already configured in urls.py:
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
```

#### Production
```bash
# Create media directory with proper permissions:
mkdir -p media/companies/logos
mkdir -p media/companies/covers
chmod 755 media/companies

# Recommended: Use cloud storage (S3, Digital Ocean Spaces, etc.)
# Install django-storages if using cloud storage:
# pip install django-storages boto3
```

### 5. Server Configuration

#### Nginx (if serving media files locally)
```nginx
location /media/ {
    alias /path/to/tredro/media/;
    expires 30d;
    add_header Cache-Control "public, immutable";
}
```

#### Whitenoise (alternative for static files)
```python
# If using Whitenoise for static files, consider adding for media too
# Or use CDN for production media files
```

### 6. Run Django Checks
```bash
# Check for issues:
python manage.py check

# Check for deployment issues:
python manage.py check --deploy
```

### 7. Test Endpoints
```bash
# Start development server:
python manage.py runserver

# Test endpoints (requires authentication token):
# GET  /api/companies/onboarding/status
# POST /api/companies/onboarding
# GET  /api/companies/locations
# GET  /api/companies/business-types
```

## Testing Checklist

### Manual Testing (Using Postman/Insomnia)

#### 1. Get Onboarding Status
```http
GET /api/companies/onboarding/status
Authorization: Bearer <access_token>
```
**Expected**: Returns company data with onboarding_completed flag

#### 2. Get Locations
```http
GET /api/companies/locations
Authorization: Bearer <access_token>
```
**Expected**: Returns 14 governorates with regions

#### 3. Get Business Types
```http
GET /api/companies/business-types
Authorization: Bearer <access_token>
```
**Expected**: Returns 6 business type options

#### 4. Complete Onboarding (Full Data)
```http
POST /api/companies/onboarding
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

logo: [file upload]
cover: [file upload]
governorate: دمشق
region: المزة
description: شركة توزيع مواد غذائية
business_type: food_products
```
**Expected**: 200 OK with updated company data

#### 5. Skip Onboarding
```http
POST /api/companies/onboarding
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

(empty body)
```
**Expected**: 200 OK, onboarding_completed=true

#### 6. Partial Onboarding
```http
POST /api/companies/onboarding
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

governorate: حلب
region: الشهباء
business_type: electronics
```
**Expected**: 200 OK with updated fields

### Error Cases to Test

#### 1. Unauthorized Access
```http
GET /api/companies/onboarding/status
(no Authorization header)
```
**Expected**: 401 Unauthorized

#### 2. Invalid File Size
```http
POST /api/companies/onboarding
logo: [file > 2MB]
```
**Expected**: 400 Bad Request with validation error

#### 3. Invalid Business Type
```http
POST /api/companies/onboarding
business_type: invalid_type
```
**Expected**: 400 Bad Request with validation error

#### 4. Description Too Long
```http
POST /api/companies/onboarding
description: [text > 500 chars]
```
**Expected**: 400 Bad Request with validation error

## Automated Testing

### Unit Tests
```bash
# Run existing tests:
pytest

# Tests should cover:
# - Serializer validation
# - View permissions
# - File upload validation
# - Optional field handling
```

### Integration Tests
```bash
# Test full onboarding flow:
# 1. Sign up
# 2. Check onboarding status
# 3. Complete onboarding
# 4. Verify company data updated
```

## Security Checklist

- [x] All endpoints require authentication
- [x] Company ID extracted from JWT token (tenant isolation)
- [x] File uploads validated (size, format)
- [x] File paths properly sanitized
- [x] No SQL injection vulnerabilities (using ORM)
- [x] CORS configured for frontend domain
- [x] HTTPS enforced in production
- [x] Media files served securely

## Performance Considerations

### Caching
```python
# Consider caching locations and business types:
from django.views.decorators.cache import cache_page

@cache_page(60 * 60 * 24)  # Cache for 24 hours
def get_locations():
    # ...
```

### Image Optimization
```python
# Consider adding image optimization:
# - Resize large uploads
# - Generate thumbnails
# - Convert to WebP format
# - Use django-imagekit or Pillow
```

### CDN
```bash
# Production recommendation:
# - Serve media files from CDN (CloudFront, Cloudinary, etc.)
# - Configure django-storages with S3
# - Set proper Cache-Control headers
```

## Monitoring

### Logs to Monitor
```python
# Key operations to log:
# - Onboarding completions
# - File upload failures
# - Validation errors
# - Authentication failures
```

### Metrics to Track
```python
# Important metrics:
# - Onboarding completion rate
# - Average fields filled per onboarding
# - Skip rate
# - File upload success rate
# - Response times
```

## Rollback Plan

### If Issues Occur

1. **Remove Companies URLs**
   ```python
   # In config/urls.py, comment out:
   # path("api/", include("apps.companies.urls")),
   ```

2. **Revert Changes**
   ```bash
   git revert <commit-hash>
   ```

3. **Database is Safe**
   - No migrations were added
   - Existing data not affected
   - Can roll back safely

## Documentation Links

- API Specification: `docs/api_auth_endpoints.md`
- Implementation Summary: `docs/onboarding_implementation_summary.md`
- This Checklist: `docs/onboarding_deployment_checklist.md`

## Support

### Common Issues

**Issue**: Media files not serving
**Solution**: Check MEDIA_ROOT permissions, ensure urls.py includes media patterns

**Issue**: File upload fails
**Solution**: Check Pillow is installed, verify file size limits in web server config

**Issue**: Authentication fails
**Solution**: Verify JWT token in Authorization header, check middleware configuration

**Issue**: Company not found
**Solution**: Ensure TenantScopingMiddleware is configured, check JWT token contains company_id

## Sign-off

- [ ] Code reviewed
- [ ] Tests passing
- [ ] Documentation updated
- [ ] Deployment tested in staging
- [ ] Security verified
- [ ] Performance acceptable
- [ ] Monitoring configured
- [ ] Rollback plan ready

**Deployed By**: _____________  
**Date**: _____________  
**Environment**: _____________  
**Version**: 1.0
