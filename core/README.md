# Core Module

This module contains shared utilities and functionality used across the entire Tredro project.

## Purpose

The `core/` directory houses project-wide utilities that don't belong to any specific Django app. This keeps the codebase organized and prevents circular dependencies.

## What Belongs Here

✅ **Should be in `core/`:**
- Global exception handlers
- Response formatting utilities
- Custom middleware (if project-wide)
- Base model classes
- Common validators
- Shared constants
- Utility functions used by multiple apps

❌ **Should NOT be in `core/`:**
- App-specific business logic
- Domain models (those belong in their respective apps)
- App-specific serializers or views

## Current Modules

### `exceptions.py`
Custom DRF exception handler that formats all API errors consistently:
```python
from core.exceptions import custom_exception_handler

# Configured in settings.py:
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}
```

**Format:**
```json
{
    "success": false,
    "message": "Human-readable error message",
    "errors": {
        "field_name": ["Error description"]
    }
}
```

### `responses.py`
Helper functions for creating consistent API responses:

```python
from core.responses import success_response, error_response

# Success response
return success_response(
    data={"user": user_data},
    message="تم تسجيل الدخول بنجاح",
    status_code=status.HTTP_200_OK
)

# Error response
return error_response(
    message="فشل التحقق من البيانات",
    errors={"phone": ["رقم الهاتف مطلوب"]},
    status_code=status.HTTP_400_BAD_REQUEST
)
```

**Success Format:**
```json
{
    "success": true,
    "message": "...",
    "data": {...}
}
```

**Error Format:**
```json
{
    "success": false,
    "message": "...",
    "errors": {...}
}
```

## Usage Guidelines

### Importing from Core

```python
# Good ✅
from core.exceptions import custom_exception_handler
from core.responses import success_response, error_response

# Bad ❌
from apps.companies.exceptions import custom_exception_handler
```

### Adding New Utilities

When adding a new utility to `core/`:

1. **Check if it's truly project-wide**
   - Will it be used by multiple apps?
   - Is it independent of any specific domain logic?

2. **Create a focused module**
   - Don't create a "utils.py" catch-all
   - Create specific modules: `validators.py`, `formatters.py`, etc.

3. **Document it**
   - Add docstrings
   - Update this README
   - Add usage examples

4. **Write tests**
   - Create `tests/test_core_<module>.py`
   - Test all edge cases

## Architecture Decision

**Why not `utils/` or `common/`?**
- `core/` clearly indicates fundamental, project-wide functionality
- Matches Django's convention (e.g., `django.core`)
- Avoids the "utils dump" anti-pattern

**Why not in individual apps?**
- Prevents circular dependencies
- Single source of truth for shared functionality
- Easier to maintain and test
- Clear separation of concerns

## Future Additions

Potential candidates for `core/`:

- `middleware.py` - Custom middleware classes
- `validators.py` - Custom field validators
- `pagination.py` - Custom pagination classes  
- `throttling.py` - Custom throttling classes
- `constants.py` - Project-wide constants
- `utils.py` - Only if truly generic (discouraged)

## Related

- App-specific utilities should remain in their respective apps
- Tenant-scoping mixins remain in `apps/companies/mixins.py` (they're tied to the companies domain)
- Authentication utilities remain in `apps/companies/auth_utils.py` (auth is a company concern)
