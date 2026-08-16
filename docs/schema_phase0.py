"""
Phase 0 / §1 schema sketch (historical). Live models live under apps/:
companies, billing, reps, customers, products, orders, invoices, notifications.

§7 Open Questions are NOT resolved here. Recommended defaults from the plan
are used only where the plan itself names them (Warehouse.owner_type).
Ambiguities are marked FLAG in comments and listed in the module docstring.

PKs: project default BigAutoField (config.settings.base.DEFAULT_AUTO_FIELD).
Every tenant-scoped table carries company_id for the §0 auto-filter.
Customer is global and has no company_id.
Plan / PlanLimit / PlanFeature / UnitOfMeasure are global catalog rows (no company_id).
"""

from __future__ import annotations

from django.db import models
from django.db.models import Q


# ---------------------------------------------------------------------------
# Enums (known values only — incomplete where §7 blocks the rest)
# ---------------------------------------------------------------------------


class WarehouseOwnerType(models.TextChoices):
    COMPANY = "company", "Company"
    REP = "rep", "Rep"


class SubscriptionStatus(models.TextChoices):
    TRIALING = "trialing", "Trialing"
    ACTIVE = "active", "Active"
    PAST_DUE = "past_due", "Past due"
    CANCELLED = "cancelled", "Cancelled"


class BillingInterval(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    YEARLY = "yearly", "Yearly"


class InvoiceType(models.TextChoices):
    INCOMING = "incoming", "Incoming"
    RETURN = "return", "Return"


class OrderType(models.TextChoices):
    REP_TO_COMPANY = "rep_to_company", "Rep → Company"
    CUSTOMER_TO_COMPANY = "customer_to_company", "Customer → Company"


class ActorType(models.TextChoices):
    """JWT actor_type / polymorphic recipient. Not a table."""

    SUBUSER = "subuser", "SubUser"
    REP = "rep", "Rep"
    CUSTOMER = "customer", "Customer"


# FLAG: full Order.status enum is not in the plan.
# Known values from §3 only. Do not treat this as the complete state machine.
# Customer→Company states after assignment are blocked on §7 (delivery vs pickup).
class OrderStatus(models.TextChoices):
    PENDING_REP_ASSIGNMENT = "pending_rep_assignment", "Pending rep assignment"
    READY_FOR_PICKUP = "ready_for_pickup", "Ready for pickup"
    RECEIVED_CONFIRMED = "received_confirmed", "Received confirmed"


class StockMovementType(models.TextChoices):
    """Reason codes for the ledger. FLAG: list is a sketch, not product-approved."""

    INITIAL = "initial", "Initial stock"
    INCOMING = "incoming", "Incoming invoice receipt"
    ORDER_OUT = "order_out", "Stock leaving a warehouse (order)"
    ORDER_IN = "order_in", "Stock entering a warehouse (order)"
    RETURN_IN = "return_in", "Return received into a warehouse"
    RETURN_OUT = "return_out", "Return leaving a warehouse"
    ADJUSTMENT = "adjustment", "Manual adjustment"


# ===========================================================================
# Global catalogs (not tenant-scoped)
# ===========================================================================


class UnitOfMeasure(models.Model):
    """Predefined material units. Companies pick from this list; they do not create units.

    Seed (confirmed): liter, kg, package.
    FLAG: full catalog beyond those three is not specified ("and so on").
    FLAG: no unit conversions (e.g. 1 package = 12 pieces) — one unit per product.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "unit_of_measure"

    def __str__(self) -> str:
        return self.name


# ===========================================================================
# SaaS catalog (§4) — global, not tenant-scoped
# ===========================================================================


class Plan(models.Model):
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_interval = models.CharField(max_length=16, choices=BillingInterval.choices)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "plan"

    def __str__(self) -> str:
        return self.name


class PlanLimit(models.Model):
    """Generic numeric cap. Adding a newly-limited resource = a row, not a migration.

    resource_key examples from the plan: reps, products, subusers, warehouses, customers.
    max_value NULL = unlimited (FLAG: sentinel not specified in the plan; see Decisions Log).
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="limits")
    resource_key = models.CharField(max_length=64)
    max_value = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "plan_limit"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "resource_key"],
                name="plan_limit_plan_resource_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["resource_key"], name="plan_limit_resource_key_idx"),
        ]


class PlanFeature(models.Model):
    """Generic boolean feature gate. Same shape as PlanLimit.

    feature_key examples from the plan: excel_import, advanced_reports, multi_warehouse.
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name="features")
    feature_key = models.CharField(max_length=64)
    enabled = models.BooleanField(default=False)

    class Meta:
        db_table = "plan_feature"
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "feature_key"],
                name="plan_feature_plan_feature_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["feature_key"], name="plan_feature_feature_key_idx"),
        ]


# ===========================================================================
# Tenant
# ===========================================================================


class Company(models.Model):
    """Tenant. Current plan is resolved via Subscription, never inlined here (§4)."""

    name = models.CharField(max_length=255)
    # FLAG: slug is not in the plan. Needed so a global Customer can hit a Store URL.
    slug = models.SlugField(max_length=64, unique=True)
    # FLAG: currency is not in the plan; invoices/orders need a unit. ISO 4217.
    currency = models.CharField(max_length=3)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "company"
        indexes = [
            models.Index(fields=["slug"], name="company_slug_idx"),
        ]


class Subscription(models.Model):
    """Company's subscription instance, decoupled from Plan catalog (§4).

    Historical rows are kept. At most one non-cancelled subscription per company
    (partial unique index). FLAG: billing-provider IDs omitted — §7 billing provider.
    FLAG: downgrade/over-limit policy is §7 — no schema for grace/deactivation.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="subscriptions"
    )
    plan = models.ForeignKey(
        Plan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status = models.CharField(max_length=16, choices=SubscriptionStatus.choices)
    current_period_start = models.DateTimeField()
    current_period_end = models.DateTimeField()
    cancelled_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subscription"
        constraints = [
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(
                    status__in=[
                        SubscriptionStatus.TRIALING,
                        SubscriptionStatus.ACTIVE,
                        SubscriptionStatus.PAST_DUE,
                    ]
                ),
                name="subscription_one_current_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status"], name="subscription_company_status_idx"),
            models.Index(fields=["current_period_end"], name="subscription_period_end_idx"),
        ]


# ===========================================================================
# Identity & access
# ===========================================================================


class Role(models.Model):
    """Per-company role. FLAG: predefined vs custom roles is §7 — no seed rows here.

    Modeling as company-scoped does not pick the role catalog; it only lets
    permissions live in data (ModulePermission) rather than in code.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "role"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="role_company_name_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="role_company_idx"),
        ]


class ModulePermission(models.Model):
    """(module, can_view, can_action) per Role. module is a string key, not an enum.

    FLAG: the module list is not in the plan (tied to §7 predefined roles).
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="module_permissions"
    )
    role = models.ForeignKey(
        Role, on_delete=models.CASCADE, related_name="permissions"
    )
    module = models.CharField(max_length=64)
    can_view = models.BooleanField(default=False)
    can_action = models.BooleanField(default=False)

    class Meta:
        db_table = "module_permission"
        constraints = [
            models.UniqueConstraint(
                fields=["role", "module"],
                name="module_permission_role_module_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="module_permission_company_idx"),
        ]


class SubUser(models.Model):
    """Company staff. Admin is a SubUser with is_owner=True (see Decisions Log).

    Company is not a login actor. FLAG: login identifier (phone vs email) not in plan.
    Phone unique per company, matching Phase 6 index note.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="subusers"
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name="subusers",
        null=True,
        blank=True,
        help_text="Null allowed only for is_owner=True (implicit full access). FLAG: confirm.",
    )
    is_owner = models.BooleanField(default=False)
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(max_length=128)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "subuser"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "phone"],
                name="subuser_company_phone_uniq",
            ),
            models.UniqueConstraint(
                fields=["company"],
                condition=Q(is_owner=True),
                name="subuser_one_owner_per_company",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="subuser_company_idx"),
            models.Index(fields=["phone"], name="subuser_phone_idx"),
        ]


class Rep(models.Model):
    """Company-scoped sales rep. No self-service profile edit (enforced in services later).

    Warehouse is NOT a FK on Rep. A rep warehouse is a Warehouse row with
    owner_type=rep and rep_id set (§2 recommended default; §7 still open).
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="reps")
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32)
    password = models.CharField(max_length=128)
    # Globally unique so a Customer can enter it without already knowing the company.
    # FLAG: plan indexes referral_code but does not say which entity owns it.
    referral_code = models.CharField(max_length=32, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "rep"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "phone"],
                name="rep_company_phone_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="rep_company_idx"),
            models.Index(fields=["phone"], name="rep_phone_idx"),
            models.Index(fields=["referral_code"], name="rep_referral_code_idx"),
        ]


class Customer(models.Model):
    """Global entity — no company_id. Registers once; orders from any company.

    assigned_rep is the §3 action-item field (referral/admin assignment).
    FLAG / §7: a Rep belongs to one Company, but a Customer is global. A single
    assigned_rep_id cannot express per-company assignment. Also §7: is this the
    same relationship as referral credit vs fulfillment? Do not add a second
    'fulfillment rep' on Customer — Order.fulfilling_rep is the per-order field.
    FLAG: trade-license image is §7 — no column.
    """

    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=32, unique=True)
    email = models.EmailField(null=True, blank=True)
    password = models.CharField(max_length=128)
    assigned_rep = models.ForeignKey(
        Rep,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="assigned_customers",
    )
    # Phase 2 first-visit GPS pin — stored on the customer, so included now.
    latitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    longitude = models.DecimalField(
        max_digits=9, decimal_places=6, null=True, blank=True
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "customer"
        indexes = [
            models.Index(fields=["phone"], name="customer_phone_idx"),
            models.Index(fields=["assigned_rep"], name="customer_assigned_rep_idx"),
        ]


# ===========================================================================
# Catalog + warehouse (§2)
# ===========================================================================


class Warehouse(models.Model):
    """Belongs to a Company. Rep warehouses reuse this table (plan §2 default).

    §7 still open — this is the recommended default, not a product decision.
    FLAG: do rep warehouses count toward PlanLimit resource_key='warehouses'?
    FLAG: one warehouse per rep, or many? No unique(rep) enforced.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="warehouses"
    )
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, default="")
    # Optional type/tag from §2 ("main" vs "cold storage"). Free string, not enum.
    kind = models.CharField(max_length=64, blank=True, default="")
    owner_type = models.CharField(
        max_length=16, choices=WarehouseOwnerType.choices
    )
    rep = models.ForeignKey(
        Rep,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="warehouses",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "warehouse"
        constraints = [
            models.CheckConstraint(
                check=(
                    Q(owner_type=WarehouseOwnerType.COMPANY, rep__isnull=True)
                    | Q(owner_type=WarehouseOwnerType.REP, rep__isnull=False)
                ),
                name="warehouse_owner_matches_rep",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="warehouse_company_idx"),
            models.Index(fields=["rep"], name="warehouse_rep_idx"),
            models.Index(
                fields=["company", "owner_type"],
                name="warehouse_company_owner_type_idx",
            ),
        ]


class Product(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="products"
    )
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=64, blank=True, default="")
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="products",
        help_text="Required. Pick from the predefined catalog, not free text.",
    )
    # FLAG: unit price on Product vs only on order/invoice lines not specified.
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    image = models.FileField(upload_to="products/", null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "sku"],
                condition=~Q(sku=""),
                name="product_company_sku_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="product_company_idx"),
        ]


class ProductWarehouseStock(models.Model):
    """M2M: which warehouses a product is stored in.

    quantity is a *projection* of StockMovement for (product, warehouse), not
    an independently writable source of truth (§0 ledger rule). Service layer
    must only change it as a result of appending a StockMovement.

    FLAG: §0 says never a mutable quantity column; §2 puts quantity on this
    join. See Decisions Log — projection, not a second source of truth.
    Quantity is in the product's UnitOfMeasure (decimal: liters/kg need fractions).
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="product_warehouse_stocks"
    )
    product = models.ForeignKey(
        Product, on_delete=models.CASCADE, related_name="warehouse_stocks"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.CASCADE, related_name="product_stocks"
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "product_warehouse_stock"
        constraints = [
            models.UniqueConstraint(
                fields=["product", "warehouse"],
                name="product_warehouse_stock_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="pws_company_idx"),
            models.Index(fields=["warehouse"], name="pws_warehouse_idx"),
        ]


# ===========================================================================
# Orders
# ===========================================================================


class Order(models.Model):
    """Both Rep→Company and Customer→Company flows.

    fulfilling_rep is distinct from placing_rep (§3).
    status values beyond the three known ones are blocked on §7 (customer
    fulfillment = deliver vs pickup). Do not add more states in this sketch.

    FLAG: Cart is named in §0 but is not a §1 entity — omitted here.
    FLAG: source warehouse on the order is not specified; stock movements
    carry warehouse_id at confirmation time.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="orders"
    )
    order_type = models.CharField(max_length=32, choices=OrderType.choices)
    status = models.CharField(max_length=64)
    customer = models.ForeignKey(
        Customer,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="orders",
        help_text="Set for customer→company orders.",
    )
    placing_rep = models.ForeignKey(
        Rep,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="placed_orders",
        help_text="Set for rep→company orders (the 'created by' rep).",
    )
    fulfilling_rep = models.ForeignKey(
        Rep,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="fulfilling_orders",
        help_text="Nullable. Required to leave pending_rep_assignment.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "order"
        indexes = [
            models.Index(fields=["company"], name="order_company_idx"),
            models.Index(fields=["company", "status"], name="order_company_status_idx"),
            models.Index(fields=["status"], name="order_status_idx"),
            models.Index(fields=["customer"], name="order_customer_idx"),
            models.Index(fields=["placing_rep"], name="order_placing_rep_idx"),
            models.Index(fields=["fulfilling_rep"], name="order_fulfilling_rep_idx"),
        ]


class OrderItem(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="order_items"
    )
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="order_items")
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="order_items",
        help_text="Snapshot of Product.unit at line creation (invoice/order immutability).",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        db_table = "order_item"
        indexes = [
            models.Index(fields=["company"], name="order_item_company_idx"),
            models.Index(fields=["order"], name="order_item_order_idx"),
        ]


# ===========================================================================
# Stock ledger (§0 / §2)
# ===========================================================================


class StockMovement(models.Model):
    """Append-only ledger. One row, one warehouse, signed quantity.

    A Company-warehouse → Rep-warehouse transfer is TWO rows (ORDER_OUT + ORDER_IN).
    Never UPDATE/DELETE. No updated_at.
    FLAG: actor who created the row (subuser vs system) not specified.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="stock_movements"
    )
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="stock_movements"
    )
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="stock_movements"
    )
    quantity = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        help_text="Signed, in the product's UnitOfMeasure. Positive = inbound, negative = outbound.",
    )
    movement_type = models.CharField(max_length=32, choices=StockMovementType.choices)
    order = models.ForeignKey(
        Order,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    invoice = models.ForeignKey(
        "Invoice",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="stock_movements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "stock_movement"
        indexes = [
            models.Index(fields=["company"], name="stock_movement_company_idx"),
            models.Index(fields=["warehouse"], name="stock_movement_warehouse_idx"),
            models.Index(
                fields=["warehouse", "product"],
                name="stock_movement_wh_product_idx",
            ),
            models.Index(fields=["order"], name="stock_movement_order_idx"),
            models.Index(fields=["created_at"], name="stock_movement_created_at_idx"),
        ]


# ===========================================================================
# Invoicing
# ===========================================================================


class Invoice(models.Model):
    """Incoming (stock receipt) or Return. Immutable after insert — no updated_at.

    Corrections are new rows, not edits (§4 Phase 4). FLAG: no parent/correction
    FK yet — correction shape not specified.
    FLAG: incoming-stock payment timing is §7 — no paid_at / payment_status.
    FLAG: tax settings location (company vs invoice) not specified; tax_rate
    is snapshotted on the line so historical invoices stay stable.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="invoices"
    )
    invoice_type = models.CharField(max_length=16, choices=InvoiceType.choices)
    warehouse = models.ForeignKey(
        Warehouse, on_delete=models.PROTECT, related_name="invoices"
    )
    rep = models.ForeignKey(
        Rep,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="invoices",
        help_text="Set for return invoices initiated by a rep.",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "invoice"
        indexes = [
            models.Index(fields=["company"], name="invoice_company_idx"),
            models.Index(fields=["invoice_type"], name="invoice_type_idx"),
            models.Index(fields=["warehouse"], name="invoice_warehouse_idx"),
        ]


class InvoiceItem(models.Model):
    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="invoice_items"
    )
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey(
        Product, on_delete=models.PROTECT, related_name="invoice_items"
    )
    unit = models.ForeignKey(
        UnitOfMeasure,
        on_delete=models.PROTECT,
        related_name="invoice_items",
        help_text="Snapshot of Product.unit at line creation.",
    )
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "invoice_item"
        indexes = [
            models.Index(fields=["company"], name="invoice_item_company_idx"),
            models.Index(fields=["invoice"], name="invoice_item_invoice_idx"),
        ]


# ===========================================================================
# Notifications
# ===========================================================================


class Notification(models.Model):
    """In-app record. company_id always set (§0) even when recipient is a Customer.

    Polymorphic recipient via actor_type + actor_id (SubUser / Rep / Customer).
    FLAG: event catalog (OrderApproved, etc.) is Phase 5 — type is a free string.
    """

    company = models.ForeignKey(
        Company, on_delete=models.CASCADE, related_name="notifications"
    )
    recipient_actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    recipient_actor_id = models.BigIntegerField()
    event_key = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "notification"
        indexes = [
            models.Index(fields=["company"], name="notification_company_idx"),
            models.Index(
                fields=["recipient_actor_type", "recipient_actor_id"],
                name="notification_recipient_idx",
            ),
            models.Index(fields=["created_at"], name="notification_created_at_idx"),
        ]
