"""Single source of truth for permission module keys.

`Role`/`ModulePermission` (companies app) store a free-text `module` key. That key
is used in three places — the owner short-circuit in
`authentication.utils.get_permissions_for_subuser`, the `GET /api/modules` picker
used by the dashboard, and the `required_module` attribute on every view. Keeping
the catalog here means those three can never drift apart.

Every invoicing document type shares the single `invoices` module: a role that
can work on invoices can work on all of them — sales, returns, incoming,
collections and credits. The order flows keep their own modules because they are
granted to different people.
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

# One module for every invoicing spec §2 document type: sales invoices, return
# invoices, incoming invoices, payment collections and customer credits.
INVOICES: Final = "invoices"

# Order flows are separate — reps raise these, invoicing staff do not.
STOCK_TRANSFERS: Final = "stock_transfers"
CUSTOMER_REQUESTS: Final = "customer_requests"

# Ordered catalog: (key, Arabic label, English label).
MODULES: Final[tuple[tuple[str, str, str], ...]] = (
    (PRODUCTS, "المنتجات", "Products"),
    (CUSTOMERS, "العملاء", "Customers"),
    (REPS, "المندوبين", "Representatives"),
    (INVOICES, "الفواتير", "Invoices"),
    (STOCK_TRANSFERS, "طلبات البضاعة", "Stock transfers"),
    (CUSTOMER_REQUESTS, "طلبات العملاء", "Customer requests"),
    (NOTIFICATIONS, "الإشعارات", "Notifications"),
    (REPORTS, "التقارير", "Reports"),
    (BILLING, "الاشتراك", "Billing"),
    (SETTINGS, "الإعدادات", "Settings"),
)

MODULE_KEYS: Final[tuple[str, ...]] = tuple(key for key, _, _ in MODULES)

# Role rows created before the invoicing spec split "orders" into stock transfers
# and customer requests. Both halves of this mapping matter:
#
# * the legacy key still *grants* the granular ones, so an existing role keeps
#   working without a data migration;
# * the legacy key is also kept in the resolved permission set, because
#   dashboards built against the old API read `permissions["orders"]` directly.
#
# New roles should be assigned catalog keys — those are the only ones the module
# picker offers. `invoices` needs no alias: it is a live catalog key again.
LEGACY_ORDERS: Final = "orders"

LEGACY_MODULE_ALIASES: Final[dict[str, tuple[str, ...]]] = {
    LEGACY_ORDERS: (LEGACY_ORDERS, STOCK_TRANSFERS, CUSTOMER_REQUESTS),
}

#: Everything an owner is granted: the live catalog plus the legacy alias.
PERMISSION_MODULE_KEYS: Final[tuple[str, ...]] = (*MODULE_KEYS, LEGACY_ORDERS)


def module_choices() -> list[dict[str, str]]:
    """Serialize the catalog for the module picker endpoint.

    Legacy keys are deliberately absent: they are honoured when already stored on
    a role, but they are not offered for new assignments.
    """
    return [
        {"value": key, "label": label, "label_en": label_en}
        for key, label, label_en in MODULES
    ]
