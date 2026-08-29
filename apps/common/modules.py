"""Single source of truth for permission module keys.

`Role`/`ModulePermission` (companies app) store a free-text `module` key. That key
is used in three places — the owner short-circuit in
`authentication.utils.get_permissions_for_subuser`, the `GET /api/modules` picker
used by the dashboard, and the `required_module` attribute on every view. Keeping
the catalog here means those three can never drift apart.

Invoicing spec §6.7: every document type is its own module. Sales Invoice and
Return Invoice permissions are deliberately *not* bundled — a delivery-only role
may create sales invoices without being able to issue credit notes.
"""

from __future__ import annotations

from typing import Final

# Identity/catalogue modules that predate the invoicing spec.
PRODUCTS: Final = "products"
CUSTOMERS: Final = "customers"
REPS: Final = "reps"
NOTIFICATIONS: Final = "notifications"
BILLING: Final = "billing"
SETTINGS: Final = "settings"
REPORTS: Final = "reports"

# Invoicing spec §2 document types, one module each.
INCOMING_INVOICES: Final = "incoming_invoices"
STOCK_TRANSFERS: Final = "stock_transfers"
CUSTOMER_REQUESTS: Final = "customer_requests"
SALES_INVOICES: Final = "sales_invoices"
RETURN_INVOICES: Final = "return_invoices"
PAYMENT_COLLECTIONS: Final = "payment_collections"
CUSTOMER_CREDITS: Final = "customer_credits"

# Ordered catalog: (key, Arabic label, English label).
MODULES: Final[tuple[tuple[str, str, str], ...]] = (
    (PRODUCTS, "المنتجات", "Products"),
    (CUSTOMERS, "العملاء", "Customers"),
    (REPS, "المندوبين", "Representatives"),
    (INCOMING_INVOICES, "فواتير الوارد", "Incoming invoices"),
    (STOCK_TRANSFERS, "طلبات البضاعة", "Stock transfers"),
    (CUSTOMER_REQUESTS, "طلبات العملاء", "Customer requests"),
    (SALES_INVOICES, "فواتير المبيعات", "Sales invoices"),
    (RETURN_INVOICES, "فواتير الإرجاع", "Return invoices"),
    (PAYMENT_COLLECTIONS, "التحصيلات", "Payment collections"),
    (CUSTOMER_CREDITS, "أرصدة العملاء", "Customer credits"),
    (NOTIFICATIONS, "الإشعارات", "Notifications"),
    (REPORTS, "التقارير", "Reports"),
    (BILLING, "الاشتراك", "Billing"),
    (SETTINGS, "الإعدادات", "Settings"),
)

MODULE_KEYS: Final[tuple[str, ...]] = tuple(key for key, _, _ in MODULES)

# Role rows created before the invoicing spec split "invoices"/"orders" into the
# granular modules above. Both halves of this mapping matter:
#
# * a legacy key still *grants* the granular ones, so an existing role keeps
#   working without a data migration;
# * the legacy key is also kept in the resolved permission set, because
#   dashboards built against the old API read `permissions["orders"]` directly.
#
# New roles should be assigned granular keys — those are the only ones the
# module picker offers.
LEGACY_INVOICES: Final = "invoices"
LEGACY_ORDERS: Final = "orders"

LEGACY_MODULE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    LEGACY_INVOICES: (
        LEGACY_INVOICES,
        INCOMING_INVOICES,
        SALES_INVOICES,
        RETURN_INVOICES,
        PAYMENT_COLLECTIONS,
        CUSTOMER_CREDITS,
    ),
    LEGACY_ORDERS: (LEGACY_ORDERS, STOCK_TRANSFERS, CUSTOMER_REQUESTS),
}

#: Everything an owner is granted: the live catalog plus the legacy aliases.
PERMISSION_MODULE_KEYS: Final[tuple[str, ...]] = (
    *MODULE_KEYS,
    LEGACY_INVOICES,
    LEGACY_ORDERS,
)


def module_choices() -> list[dict[str, str]]:
    """Serialize the catalog for the module picker endpoint.

    Legacy keys are deliberately absent: they are honoured when already stored on
    a role, but they are not offered for new assignments.
    """
    return [
        {"value": key, "label": label, "label_en": label_en}
        for key, label, label_en in MODULES
    ]
