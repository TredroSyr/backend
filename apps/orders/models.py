"""Non-financial documents: stock transfers and customer requests.

Both entities here replace what the original MVP doc modelled as an `Order`
(invoicing spec §1). Neither carries money or tax fields, and the distinction is
the point of the whole module:

* **Stock Transfer** (§3.2) moves goods company -> rep. No money changes hands
  internally, so it is a lightweight transfer record, not a tax-bearing invoice.
* **Customer Request** (§3.3) is a wishlist signal telling a rep what a customer
  wants on the next visit. It is *not* a sale and creates no commitment; the sale
  happens face-to-face and produces an `invoices.SalesInvoice`.

The financial documents live in `apps.invoices`; the stock ledger both of these
write to lives in `apps.products`.
"""

from __future__ import annotations

from django.db import models

from apps.common.models import TimeStampedModel
from apps.products.models import ProductLine


class StockTransferStatus(models.TextChoices):
    """§3.2 state machine. `received` is the only state that moves stock."""

    PENDING = "pending", "Pending admin review"
    MODIFIED_BY_ADMIN = "modified_by_admin", "Modified by admin"
    PENDING_REP_CONFIRMATION = "pending_rep_confirmation", "Pending rep confirmation"
    CONFIRMED = "confirmed", "Confirmed"
    RECEIVED = "received", "Received"
    CANCELLED = "cancelled", "Cancelled"


#: Allowed transitions, enforced by `services.transfers`. Mirrors §3.2 exactly:
#:
#:   pending -> admin approves as-is      -> confirmed
#:           -> admin modifies quantities -> modified_by_admin
#:                -> awaiting the rep     -> pending_rep_confirmation
#:                     -> rep approves    -> confirmed
#:                     -> rep rejects     -> cancelled
#:   confirmed -> rep taps "received"     -> received
STOCK_TRANSFER_TRANSITIONS: dict[str, set[str]] = {
    StockTransferStatus.PENDING: {
        StockTransferStatus.CONFIRMED,
        StockTransferStatus.MODIFIED_BY_ADMIN,
        StockTransferStatus.CANCELLED,
    },
    StockTransferStatus.MODIFIED_BY_ADMIN: {
        StockTransferStatus.PENDING_REP_CONFIRMATION,
        StockTransferStatus.CANCELLED,
    },
    StockTransferStatus.PENDING_REP_CONFIRMATION: {
        StockTransferStatus.CONFIRMED,
        StockTransferStatus.CANCELLED,
    },
    StockTransferStatus.CONFIRMED: {
        StockTransferStatus.RECEIVED,
        StockTransferStatus.CANCELLED,
    },
    StockTransferStatus.RECEIVED: set(),
    StockTransferStatus.CANCELLED: set(),
}


class StockTransfer(TimeStampedModel):
    """Company warehouse -> rep warehouse. Not an invoice: no tax fields, no total.

    Confirmation and physical receipt are deliberately two steps. Confirming only
    means the rep agreed to the quantity; stock moves on `received` and nowhere
    else, matching the two-step flow the original doc describes.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="stock_transfers",
    )
    number = models.CharField(max_length=32)
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.PROTECT,
        related_name="stock_transfers",
    )
    source_warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="outgoing_transfers",
        help_text="Company warehouse the goods leave.",
    )
    destination_warehouse = models.ForeignKey(
        "products.Warehouse",
        on_delete=models.PROTECT,
        related_name="incoming_transfers",
        help_text="Rep warehouse the goods arrive in.",
    )
    status = models.CharField(
        max_length=32,
        choices=StockTransferStatus.choices,
        default=StockTransferStatus.PENDING,
    )
    requested_at = models.DateTimeField()
    approved_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        "companies.SubUser",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="approved_stock_transfers",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "stock_transfer"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "number"],
                name="stock_transfer_company_number_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="transfer_company_idx"),
            models.Index(fields=["company", "status"], name="transfer_status_idx"),
            models.Index(fields=["rep"], name="transfer_rep_idx"),
            models.Index(fields=["requested_at"], name="transfer_requested_idx"),
        ]

    def __str__(self) -> str:
        return self.number

    def can_transition_to(self, status: str) -> bool:
        return status in STOCK_TRANSFER_TRANSITIONS.get(self.status, set())


class StockTransferLine(ProductLine):
    """`approved_qty` may differ from `requested_qty` — the admin can cut a line
    down. It stays null until an admin acts, and the *approved* quantity is what
    moves on receipt.
    """

    transfer = models.ForeignKey(
        StockTransfer, on_delete=models.CASCADE, related_name="lines"
    )
    requested_qty = models.DecimalField(max_digits=14, decimal_places=3)
    approved_qty = models.DecimalField(
        max_digits=14,
        decimal_places=3,
        null=True,
        blank=True,
        help_text="Null until an admin approves or modifies the transfer.",
    )

    class Meta:
        db_table = "stock_transfer_line"
        constraints = [
            models.UniqueConstraint(
                fields=["transfer", "product"],
                name="stock_transfer_line_product_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="transfer_line_company_idx"),
            models.Index(fields=["transfer"], name="transfer_line_transfer_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} x {self.requested_qty}"

    @property
    def effective_qty(self):
        """Quantity that will actually move: the approved one, else as requested."""
        return self.requested_qty if self.approved_qty is None else self.approved_qty


class CustomerRequestStatus(models.TextChoices):
    """Where a request stands with the rep who owns it.

    `accepted` and `rejected` are the rep's answer to the customer: yes, I will
    bring this, or no. Neither moves stock or money — accepting is a promise to
    visit, and the delivery is still the Sales Invoice, which is what actually
    fulfils the request (§3.3).

    `rejected` and `cancelled` are both closed-without-delivery but are not the
    same event: the rep turned it down, versus the customer withdrew it. Keeping
    them apart is what lets either side see who ended it.
    """

    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted by rep"
    FULFILLED = "fulfilled", "Fulfilled"
    REJECTED = "rejected", "Rejected by rep"
    CANCELLED = "cancelled", "Cancelled by customer"


class CustomerRequest(TimeStampedModel):
    """A wishlist signal from the customer app — informational only (§3.3).

    Creating one never touches a warehouse and never creates a financial record.
    It notifies the assigned rep as a heads-up, not an order confirmation.

    `fulfilled_by_invoice` is deliberately optional: a rep may deliver a Sales
    Invoice containing products that were never requested, and invoice creation
    is never blocked on a request existing.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="customer_requests",
        help_text="The company being browsed in the customer app.",
    )
    customer = models.ForeignKey(
        "customers.Customer",
        on_delete=models.PROTECT,
        related_name="requests",
    )
    rep = models.ForeignKey(
        "reps.Rep",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="customer_requests",
        help_text="Assigned rep notified at creation time, if the customer has one.",
    )
    status = models.CharField(
        max_length=16,
        choices=CustomerRequestStatus.choices,
        default=CustomerRequestStatus.PENDING,
    )
    fulfilled_by_invoice = models.ForeignKey(
        "invoices.SalesInvoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="fulfilled_requests",
        help_text="Set when a rep links a delivery to this request. Optional by design.",
    )
    fulfilled_at = models.DateTimeField(null=True, blank=True)
    cancelled_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Optional note the rep leaves when turning a request down.",
    )
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "customer_request"
        indexes = [
            models.Index(fields=["company"], name="cust_request_company_idx"),
            models.Index(fields=["company", "status"], name="cust_request_status_idx"),
            models.Index(fields=["customer"], name="cust_request_customer_idx"),
            models.Index(fields=["rep"], name="cust_request_rep_idx"),
            models.Index(fields=["created_at"], name="cust_request_created_idx"),
        ]

    def __str__(self) -> str:
        return f"Request {self.pk} from customer {self.customer_id}"


class CustomerRequestLine(ProductLine):
    """No price: nothing has been agreed yet. The rep prices the goods when the
    Sales Invoice is written.
    """

    request = models.ForeignKey(
        CustomerRequest, on_delete=models.CASCADE, related_name="lines"
    )
    desired_quantity = models.DecimalField(max_digits=14, decimal_places=3)

    class Meta:
        db_table = "customer_request_line"
        constraints = [
            models.UniqueConstraint(
                fields=["request", "product"],
                name="customer_request_line_product_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["company"], name="cust_req_line_company_idx"),
            models.Index(fields=["request"], name="cust_req_line_request_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.product_id} x {self.desired_quantity}"
