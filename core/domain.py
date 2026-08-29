"""Domain errors raised by service functions.

Services stay framework-agnostic: they raise these instead of building DRF
responses, and `core.exceptions.custom_exception_handler` renders them in the
same `{success, message, errors}` envelope as everything else. That keeps one
error shape across the API without dragging DRF into the business logic.

`message` is user-facing (Arabic, like the rest of the API); `errors` carries the
field-level detail a client needs to highlight the offending input.
"""

from __future__ import annotations

from rest_framework import status


class DomainError(Exception):
    """A rule of the domain was violated. Renders as 400 by default."""

    status_code = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str, errors: dict | None = None):
        self.message = message
        self.errors = errors or {}
        super().__init__(message)


class InvalidTransition(DomainError):
    """A document was asked to move to a state its state machine forbids."""

    status_code = status.HTTP_409_CONFLICT
