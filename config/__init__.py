from __future__ import annotations

# Celery app is imported so that shared_task uses this app when Django starts.
from .celery import app as celery_app

__all__ = ("celery_app",)
