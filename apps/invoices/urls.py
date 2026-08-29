"""URL patterns for the invoicing module.

Routes are grouped by audience, matching the three clients in the spec:

    /api/companies/...  admin dashboard (SubUsers, module-permissioned)
    /api/reps/...       rep field app
"""

from __future__ import annotations

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.invoices.views import (
    CustomerCreditViewSet,
    IncomingInvoiceViewSet,
    InvoiceSettingsView,
    OverdueDebtReportView,
    PaymentCollectionViewSet,
    RepCustomerCreditViewSet,
    RepPaymentCollectionViewSet,
    RepReturnInvoiceViewSet,
    RepSalesInvoiceViewSet,
    RepCashReconciliationView,
    ReturnInvoiceViewSet,
    SalesInvoiceViewSet,
)

router = DefaultRouter()

# Admin dashboard
router.register(
    r"companies/incoming-invoices", IncomingInvoiceViewSet, basename="incoming-invoice"
)
router.register(r"companies/sales-invoices", SalesInvoiceViewSet, basename="sales-invoice")
router.register(
    r"companies/return-invoices", ReturnInvoiceViewSet, basename="return-invoice"
)
router.register(
    r"companies/payment-collections",
    PaymentCollectionViewSet,
    basename="payment-collection",
)
router.register(
    r"companies/customer-credits", CustomerCreditViewSet, basename="customer-credit"
)

# Rep field app
router.register(r"reps/sales-invoices", RepSalesInvoiceViewSet, basename="rep-sales-invoice")
router.register(
    r"reps/return-invoices", RepReturnInvoiceViewSet, basename="rep-return-invoice"
)
router.register(r"reps/payments", RepPaymentCollectionViewSet, basename="rep-payment")
router.register(
    r"reps/customer-credits", RepCustomerCreditViewSet, basename="rep-customer-credit"
)

urlpatterns = [
    path(
        "companies/invoice-settings/",
        InvoiceSettingsView.as_view(),
        name="invoice-settings",
    ),
    path(
        "companies/reports/overdue-debts/",
        OverdueDebtReportView.as_view(),
        name="overdue-debt-report",
    ),
    path(
        "companies/reports/rep-cash/",
        RepCashReconciliationView.as_view(),
        name="rep-cash-report",
    ),
    path("", include(router.urls)),
]
