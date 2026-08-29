"""URL patterns for stock transfers and customer requests.

Three audiences, three prefixes: the admin dashboard, the rep field app, and the
customer app (whose requests are scoped by customer, not by tenant — customers
are global entities).
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.orders.views import (
    CustomerRequestViewSet,
    MyCustomerRequestViewSet,
    RepCustomerRequestViewSet,
    RepStockTransferViewSet,
    StockTransferViewSet,
)

router = DefaultRouter()

# Admin dashboard
router.register(
    r"companies/stock-transfers", StockTransferViewSet, basename="stock-transfer"
)
router.register(
    r"companies/customer-requests", CustomerRequestViewSet, basename="customer-request"
)

# Rep field app
router.register(
    r"reps/stock-transfers", RepStockTransferViewSet, basename="rep-stock-transfer"
)
router.register(
    r"reps/customer-requests",
    RepCustomerRequestViewSet,
    basename="rep-customer-request",
)

# Customer app
router.register(
    r"customers/requests", MyCustomerRequestViewSet, basename="my-customer-request"
)

urlpatterns = [
    path("", include(router.urls)),
]
