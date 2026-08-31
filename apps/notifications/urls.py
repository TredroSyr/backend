"""URL patterns for the in-app inbox.

No audience prefix, unlike the document apps: the recipient is whoever holds the
token, so `/api/notifications/` means the same thing to an admin, a rep and a
customer.
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.notifications.views import NotificationViewSet

router = DefaultRouter()
router.register(r"notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("", include(router.urls)),
]
