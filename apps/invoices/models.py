"""Financial documents for the invoicing module.

Entity map (invoicing spec §2). Only the financial rows live here; the two
non-financial documents — Stock Transfer and Customer Request — live in
`apps.orders` because they carry no money and no tax fields:

    Incoming Invoice   financial, tax  admin      + company warehouse
    Sales Invoice      financial, tax  rep        - rep warehouse
    Return Invoice     financial, tax  rep/admin  + rep or company warehouse
    Payment Collection financial       rep        no stock movement

Two rules shape every model below:

* §6.2 — `paid_amount`, `returned_amount`, `balance_due` and `status` are derived
  from `PaymentCollection` and `ReturnInvoice` rows and recomputed on every
  mutation by `services.balances.recompute_sales_invoice`. They are persisted for
  query speed, never accepted from a client.
* §6.3 — `number` is drawn from a per-company, per-type sequence. The database
  primary key stays a `BigAutoField`; `number` is the human-facing identifier the
  spec writes as `INV-SALE-00001`.
"""

from __future__ import annotations

from decimal import Decimal

from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import ProductLine

MONEY_ZERO = Decimal("0.00")
CENTS = Decimal("0.01")

DEFAULT_OVERDUE_THRESHOLD_DAYS = 7


class InvoiceSettings(TimeStampedModel):
    """One settings row per company, shared by every invoice type (§6.8).

    Company name and tax registration number are not duplicated per invoice type;
    each document snapshots them at issue time so a later settings edit cannot
    rewrite history on documents already handed to a customer.
    """

    company = models.OneToOneField(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="invoice_settings",
    )
    company_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Legal name printed on invoices. Falls back to Company.name when blank.",
    )
    tax_registration_no = models.CharField(max_length=64, blank=True, default="")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    overdue_threshold_days = models.PositiveIntegerField(
        default=DEFAULT_OVERDUE_THRESHOLD_DAYS,
        help_text="Days after which an unsettled sales invoice counts as overdue (§5).",
    )

    class Meta:
        db_table = "invoice_settings"
        verbose_name_plural = "invoice settings"

    def __str__(self) -> str:
        return f"Invoice settings for company {self.company_id}"

    @property
    def display_company_name(self) -> str:
        return self.company_name or self.company.name

    def as_snapshot(self) -> dict[str, str]:
        """Header fields copied onto a document at creation/issue time.

        `currency` is deliberately not here: these two strings are safe to
        refresh when a draft is issued, but the denomination is not — the lines
        were priced under it. Each document service pins `currency` once, at
        creation.
        """
        return {
            "company_name": self.display_company_name,
            "tax_registration_no": self.tax_registration_no,
        }


class DocumentLine(ProductLine):
    """Shared shape for every priced invoice line.

    Adds money to `products.ProductLine`: `subtotal` is always derived from
    quantity x unit_price — a client never posts it.
    """

    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=MONEY_ZERO)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        abstract = True

    def compute_subtotal(self) -> Decimal:
        return (self.quantity * self.unit_price).quantize(CENTS)

    def save(self, *args, **kwargs):
        self.subtotal = self.compute_subtotal()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "subtotal" not in update_fields:
            kwargs["update_fields"] = [*update_fields, "subtotal"]
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.product_id} x {self.quantity}"


# ---------------------------------------------------------------------------
# 1. Incoming Invoice (§3.1) — supplier / parent company -> company warehouse
# ---------------------------------------------------------------------------


class IncomingInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    CANCELLED = "cancelled", "Cancelled"


class IncomingInvoice(TimeStampedModel):
    """Formal purchase document. Stock lands only on the draft -> issued
    transition, atomically with the invoice update (§3.1 rule).
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="incoming_invoices",
    )
    number = models.CharField(max_length=32)
    date = models.DateTimeField()
    supplier_ref = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Free text naming the supplier or parent company.",
    )
    company_name = models.CharField(max_length=255, blank=True, default="")
    tax_registration_no = models.CharField(max_length=64, blank=True, default="")
    currency = models.CharField(
        max_length=3,
        blank=True,
        default="",
        help_text=(
            "ISO 4217 code every money column on this document is denominated in. "
            "Snapshotted at creation so a later change to Company.currency cannot "
            "re-denominate a document that was already priced."
        ),
    )
    warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="incoming_invoices",
        help_text="Company warehouse the goods are received into.",
    )
    status = models.CharField(
        max_length=16,
        choices=IncomingInvoiceStatus.choices,
        default=IncomingInvoiceStatus.DRAFT,
    )
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=MONEY_ZERO)
    notes = models.TextField(blank=True, default="")
    created_by = models.ForeignKey(
        "companies.SubUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="incoming_invoices",
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "incoming_invoice"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                name="incoming_invoice_company_number_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="inc_invoice_company_idx"),
            models.Index(fields=["company", "status"], name="inc_invoice_status_idx"),
            models.Index(fields=["date"], name="inc_invoice_date_idx"),
        ]

    def __str__(self) -> str:
        return self.number


class IncomingInvoiceLine(DocumentLine):
    invoice = models.ForeignKey(
        IncomingInvoice, on_delete=models.CASCADE, related_name="lines"
    )

    class Meta:
        db_table = "incoming_invoice_line"
        indexes = [
            models.Index(fields=["company"], name="inc_invoice_line_company_idx"),
            models.Index(fields=["invoice"], name="inc_invoice_line_invoice_idx"),
        ]


# ---------------------------------------------------------------------------
# 2. Sales Invoice (§3.4) — the real transaction, issued by the rep on delivery
# ---------------------------------------------------------------------------


class SalesInvoiceStatus(models.TextChoices):
    """Derived from the numbers, never set by a user (§3.4.1)."""

    FULLY_PAID = "fully_paid", "Fully paid"
    PARTIALLY_PAID = "partially_paid", "Partially paid"
    DEFERRED = "deferred", "Deferred"


class SalesInvoice(TimeStampedModel):
    """Created face-to-face when the rep delivers. Deducts the rep warehouse on
    creation, atomically (§3.4 rule).

    Customers may pay in full, in part, or not at all — there is no paid/unpaid
    flag and no credit limit (§1). `balance_due` floors at zero; anything beyond
    that is an overage carried by a Return Invoice (§3.5 rule 3).
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="sales_invoices",
    )
    number = models.CharField(max_length=32)
    date = models.DateTimeField()
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="sales_invoices",
        help_text=(
            "Null for a company-direct sale — a customer buying from the company "
            "itself, with no rep involved. Set for the normal field sale."
        ),
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="sales_invoices",
    )
    warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="sales_invoices",
        help_text=(
            "Warehouse the goods leave: the rep's van for a field sale, a company "
            "warehouse for a direct sale."
        ),
    )
    company_name = models.CharField(max_length=255, blank=True, default="")
    tax_registration_no = models.CharField(max_length=64, blank=True, default="")
    currency = models.CharField(
        max_length=3,
        blank=True,
        default="",
        help_text=(
            "ISO 4217 code every money column on this document is denominated in. "
            "Snapshotted at creation so a later change to Company.currency cannot "
            "re-denominate a document that was already priced."
        ),
    )

    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=MONEY_ZERO)
    paid_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=MONEY_ZERO,
        help_text="Derived: sum of linked payment_collections.",
    )
    returned_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=MONEY_ZERO,
        help_text="Derived: sum of linked issued return_invoices.",
    )
    balance_due = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=MONEY_ZERO,
        help_text="Derived: max(0, total - paid - returned). Never negative.",
    )
    status = models.CharField(
        max_length=16,
        choices=SalesInvoiceStatus.choices,
        default=SalesInvoiceStatus.DEFERRED,
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "sales_invoice"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                name="sales_invoice_company_number_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="sales_invoice_company_idx"),
            models.Index(fields=["company", "status"], name="sales_invoice_status_idx"),
            models.Index(fields=["rep"], name="sales_invoice_rep_idx"),
            models.Index(fields=["customer"], name="sales_invoice_customer_idx"),
            models.Index(fields=["created_at"], name="sales_invoice_created_idx"),
        ]

    def __str__(self) -> str:
        return self.number

    @property
    def overage_amount(self) -> Decimal:
        """Amount by which payments plus returns exceed the invoice total."""
        excess = self.paid_amount + self.returned_amount - self.total_amount
        return excess if excess > MONEY_ZERO else MONEY_ZERO


class SalesInvoiceLine(DocumentLine):
    invoice = models.ForeignKey(
        SalesInvoice, on_delete=models.CASCADE, related_name="lines"
    )

    class Meta:
        db_table = "sales_invoice_line"
        indexes = [
            models.Index(fields=["company"], name="sales_line_company_idx"),
            models.Index(fields=["invoice"], name="sales_line_invoice_idx"),
        ]


# ---------------------------------------------------------------------------
# 3. Return Invoice / Credit Note (§3.5)
# ---------------------------------------------------------------------------


class ReturnInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"


class RefundMethod(models.TextChoices):
    """How an overage is settled. Required only when `overage_amount > 0`."""

    CASH_REFUNDED_BY_REP = "cash_refunded_by_rep", "Cash refunded by rep"
    DEFERRED_CUSTOMER_CREDIT = "deferred_customer_credit", "Deferred customer credit"


class ReturnInvoice(TimeStampedModel):
    """A credit note against one Sales Invoice — never an orphan document.

    Matches the SAP/QuickBooks/Zoho/Odoo pattern: `sales_invoice` is required, a
    single sale can accumulate several returns over successive visits, and the
    parent's derived totals are recomputed from the full set every time (§3.5
    rule 4).
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="return_invoices",
    )
    number = models.CharField(max_length=32)
    date = models.DateTimeField()
    sales_invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        related_name="returns",
        help_text="Required — a return is always a credit note against a sale.",
    )
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="return_invoices",
        help_text=(
            "Inherited from the sale being credited, so it is null when crediting "
            "a company-direct sale."
        ),
    )
    warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="return_invoices",
        help_text=(
            "Where the goods physically land. The rep's warehouse by default; an "
            "admin can route defective goods to a company warehouse instead."
        ),
    )
    company_name = models.CharField(max_length=255, blank=True, default="")
    tax_registration_no = models.CharField(max_length=64, blank=True, default="")
    currency = models.CharField(
        max_length=3,
        blank=True,
        default="",
        help_text=(
            "ISO 4217 code every money column on this document is denominated in. "
            "Snapshotted at creation so a later change to Company.currency cannot "
            "re-denominate a document that was already priced."
        ),
    )
    status = models.CharField(
        max_length=16,
        choices=ReturnInvoiceStatus.choices,
        default=ReturnInvoiceStatus.DRAFT,
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2, default=MONEY_ZERO)
    overage_amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        default=MONEY_ZERO,
        help_text="Derived: (returned + paid) - total on the parent invoice, floored at 0.",
    )
    refund_method = models.CharField(
        max_length=32,
        choices=RefundMethod.choices,
        blank=True,
        default="",
        help_text="Required before issuing when this return creates an overage.",
    )
    notes = models.TextField(blank=True, default="")
    issued_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "return_invoice"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                name="return_invoice_company_number_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="return_invoice_company_idx"),
            models.Index(fields=["sales_invoice"], name="return_invoice_sales_idx"),
            models.Index(fields=["rep"], name="return_invoice_rep_idx"),
            models.Index(fields=["company", "status"], name="return_invoice_status_idx"),
        ]

    def __str__(self) -> str:
        return self.number


class ReturnInvoiceLine(DocumentLine):
    """`unit_price` is copied from the original sales line, never re-entered
    (§3.5 schema), which is also what bounds how much may be returned.
    """

    return_invoice = models.ForeignKey(
        ReturnInvoice, on_delete=models.CASCADE, related_name="lines"
    )
    sales_invoice_line = models.ForeignKey(
        SalesInvoiceLine,
        on_delete=models.PROTECT,
        related_name="return_lines",
        help_text="The sold line being credited. Source of unit_price and of the returnable cap.",
    )

    class Meta:
        db_table = "return_invoice_line"
        indexes = [
            models.Index(fields=["company"], name="return_line_company_idx"),
            models.Index(fields=["return_invoice"], name="return_line_invoice_idx"),
            models.Index(fields=["sales_invoice_line"], name="return_line_sales_line_idx"),
        ]


# ---------------------------------------------------------------------------
# 4. Payment Collection (§3.6)
# ---------------------------------------------------------------------------


class PaymentSource(models.TextChoices):
    CASH = "cash", "Cash collected by rep"
    CUSTOMER_CREDIT = "customer_credit", "Applied from a pending customer credit"


class PaymentCollection(models.Model):
    """Append-only. A rep never types a "new balance" — they append a payment and
    the invoice's derived fields are recomputed from the full set (§3.6 rule).

    Immutable by design, so there is no `updated_at`.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="payment_collections",
    )
    sales_invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        related_name="payments",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    collected_by = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payment_collections",
        help_text="Null when an admin records the payment rather than a rep.",
    )
    collected_at = models.DateTimeField()
    source = models.CharField(
        max_length=16,
        choices=PaymentSource.choices,
        default=PaymentSource.CASH,
        help_text="Cash counts toward the rep's expected cash-in; credit does not.",
    )
    applied_credit = models.ForeignKey(
        "PendingCustomerCredit",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="payments",
        help_text="Set when this row records a customer credit being applied (§3.7 rule 2).",
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "payment_collection"
        indexes = [
            models.Index(fields=["company"], name="payment_company_idx"),
            models.Index(fields=["sales_invoice"], name="payment_invoice_idx"),
            models.Index(fields=["collected_by"], name="payment_rep_idx"),
            models.Index(fields=["collected_at"], name="payment_collected_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.amount} on {self.sales_invoice_id}"


# ---------------------------------------------------------------------------
# 5. Pending Customer Credit (§3.7)
# ---------------------------------------------------------------------------


class CustomerCreditStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPLIED = "applied", "Applied"
    CANCELLED = "cancelled", "Cancelled"


class PendingCustomerCredit(TimeStampedModel):
    """A tracked list, deliberately not an auto-applying ledger (§3.7, §7).

    Created only by the `deferred_customer_credit` refund path. A rep or admin
    explicitly chooses to apply one while building a new Sales Invoice; nothing
    is ever deducted silently.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customer_credits",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="pending_credits",
    )
    source_return_invoice = models.ForeignKey(
        ReturnInvoice,
        on_delete=models.PROTECT,
        related_name="credits",
    )
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(
        max_length=16,
        choices=CustomerCreditStatus.choices,
        default=CustomerCreditStatus.PENDING,
    )
    applied_to_invoice = models.ForeignKey(
        SalesInvoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applied_credits",
    )
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "pending_customer_credit"
        indexes = [
            models.Index(fields=["company"], name="credit_company_idx"),
            models.Index(
                fields=["customer", "status"],
                name="credit_customer_status_idx",
            ),
            models.Index(fields=["source_return_invoice"], name="credit_return_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.amount} credit for customer {self.customer_id}"


# ---------------------------------------------------------------------------
# 6. Rep cash adjustments (§3.5 rule 3, `cash_refunded_by_rep` path)
# ---------------------------------------------------------------------------


class RepCashAdjustment(models.Model):
    """Signed correction to a rep's expected cash-in.

    The `cash_refunded_by_rep` path needs the refunded overage deducted from what
    the rep owes at their next reconciliation, without inventing a settlement
    module (out of scope for v1). This append-only row, plus the payments a rep
    collected, is enough to state that figure — see `services.reconciliation`.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="rep_cash_adjustments",
    )
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        related_name="cash_adjustments",
    )
    amount = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        help_text="Signed. Negative reduces the rep's expected cash-in (e.g. a refund paid out).",
    )
    reason = models.CharField(max_length=64)
    return_invoice = models.ForeignKey(
        ReturnInvoice,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="cash_adjustments",
    )
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "rep_cash_adjustment"
        indexes = [
            models.Index(fields=["company"], name="cash_adj_company_idx"),
            models.Index(fields=["rep"], name="cash_adj_rep_idx"),
            models.Index(fields=["created_at"], name="cash_adj_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.amount} for rep {self.rep_id}"
