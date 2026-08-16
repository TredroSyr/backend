"""Helper functions for creating consistent API responses."""

from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response


def success_response(
    data: dict | list | None = None,
    message: str = "",
    status_code: int = status.HTTP_200_OK,
) -> Response:
    """
    Helper function to create consistent success responses.
    
    Format:
    {
        "success": true,
        "message": "...",
        "data": {...}
    }
    """
    response_data = {
        "success": True,
        "message": message,
    }
    
    if data is not None:
        response_data["data"] = data
    
    return Response(response_data, status=status_code)


def error_response(
    message: str,
    errors: dict | None = None,
    status_code: int = status.HTTP_400_BAD_REQUEST,
) -> Response:
    """
    Helper function to create consistent error responses.
    
    Format:
    {
        "success": false,
        "message": "...",
        "errors": {...}
    }
    """
    response_data = {
        "success": False,
        "message": message,
    }
    
    if errors:
        response_data["errors"] = errors
    
    return Response(response_data, status=status_code)
