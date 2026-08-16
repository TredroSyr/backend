"""Custom exception handlers for consistent API error responses."""

from __future__ import annotations

from rest_framework import status
from rest_framework.exceptions import ErrorDetail
from rest_framework.response import Response
from rest_framework.views import exception_handler


def custom_exception_handler(exc, context):
    """
    Custom exception handler that returns consistent error format:
    {
        "success": false,
        "message": "Human-readable error message",
        "errors": {
            "field_name": ["Error description 1", "Error description 2"]
        }
    }
    """
    # Call REST framework's default exception handler first
    response = exception_handler(exc, context)
    
    if response is not None:
        custom_response_data = {
            "success": False,
            "message": get_error_message(exc),
            "errors": format_errors(response.data),
        }
        response.data = custom_response_data
    
    return response


def get_error_message(exc) -> str:
    """Extract a human-readable error message from the exception."""
    if hasattr(exc, "detail"):
        detail = exc.detail
        if isinstance(detail, dict):
            # For validation errors, use a generic message
            return "فشل التحقق من البيانات"
        elif isinstance(detail, list):
            # Return first error message
            return str(detail[0]) if detail else "حدث خطأ"
        else:
            return str(detail)
    
    return "حدث خطأ في الخادم"


def format_errors(data) -> dict:
    """
    Format error data into consistent structure.
    Converts DRF's error format to our custom format.
    """
    if isinstance(data, dict):
        errors = {}
        for key, value in data.items():
            if isinstance(value, list):
                # Convert ErrorDetail objects to strings
                errors[key] = [str(v) for v in value]
            elif isinstance(value, ErrorDetail):
                errors[key] = [str(value)]
            elif isinstance(value, dict):
                # Nested errors
                errors[key] = format_errors(value)
            else:
                errors[key] = [str(value)]
        return errors
    elif isinstance(data, list):
        return {"detail": [str(item) for item in data]}
    else:
        return {"detail": [str(data)]}
