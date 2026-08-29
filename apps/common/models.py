from __future__ import annotations

from django.db import models


class UnitOfMeasure(models.Model):
    """Predefined material units. Companies pick from this list; they do not create units.

    Seeded: liter, kg, package. Full catalog beyond those three is still open.
    """

    code = models.CharField(max_length=32, unique=True)
    name = models.CharField(max_length=64)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "unit_of_measure"

    def __str__(self) -> str:
        return self.name


class Currency(models.Model):
    """Predefined currency catalog (ISO 4217). Same pattern as UnitOfMeasure: companies pick,
    they do not create currencies.
    """

    code = models.CharField(max_length=3, unique=True, help_text="ISO 4217 code, e.g. USD, EUR")
    name = models.CharField(max_length=64)
    symbol = models.CharField(max_length=8, blank=True, default="")
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "currency"
        verbose_name_plural = "currencies"

    def __str__(self) -> str:
        return self.code


class TimeStampedModel(models.Model):
    """Abstract `created_at`/`updated_at` pair shared by every document below."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class ActorType(models.TextChoices):
    """Who performed an action. Mirrors the JWT `actor_type` claim, plus `system`
    for transitions the platform makes on its own (e.g. auto-fulfilling a request).
    """

    SUBUSER = "subuser", "SubUser"
    REP = "rep", "Rep"
    CUSTOMER = "customer", "Customer"
    SYSTEM = "system", "System"


class DocumentType(models.TextChoices):
    """Numbered documents. Invoicing spec §6.3: one sequence per type, never a
    shared global counter — admins reconcile against their paper books per type.
    """

    INCOMING_INVOICE = "incoming_invoice", "Incoming invoice"
    STOCK_TRANSFER = "stock_transfer", "Stock transfer"
    SALES_INVOICE = "sales_invoice", "Sales invoice"
    RETURN_INVOICE = "return_invoice", "Return invoice"


DOCUMENT_NUMBER_PREFIXES: dict[str, str] = {
    DocumentType.INCOMING_INVOICE: "INV-IN",
    DocumentType.STOCK_TRANSFER: "TRF",
    DocumentType.SALES_INVOICE: "INV-SALE",
    DocumentType.RETURN_INVOICE: "INV-RET",
}


class DocumentSequence(models.Model):
    """Per-company, per-type counter behind `services.numbering.next_document_number`.

    Rows are locked with `SELECT ... FOR UPDATE` when a number is drawn, so two
    concurrent issues can never collide on the same number.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="document_sequences",
    )
    document_type = models.CharField(max_length=32, choices=DocumentType.choices)
    last_number = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "document_sequence"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "document_type"],
                name="document_sequence_company_type_uniq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.document_type}: {self.last_number}"


class AuditLog(models.Model):
    """Immutable history entry. Invoicing spec §6.4: every status transition on a
    document that touches money or stock writes one of these (who, when, what).

    Never UPDATE or DELETE a row here — corrections are new rows.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Null for system-initiated transitions.",
    )
    entity_type = models.CharField(
        max_length=64,
        help_text="Model label, e.g. 'sales_invoice'.",
    )
    entity_id = models.BigIntegerField()
    entity_number = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="Human-readable document number at the time of the action.",
    )
    action = models.CharField(max_length=64, help_text="e.g. 'issued', 'payment_recorded'.")
    from_status = models.CharField(max_length=64, blank=True, default="")
    to_status = models.CharField(max_length=64, blank=True, default="")
    changes = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "audit_log"
        indexes = [
            models.Index(fields=["company"], name="audit_log_company_idx"),
            models.Index(
                fields=["entity_type", "entity_id"],
                name="audit_log_entity_idx",
            ),
            models.Index(fields=["created_at"], name="audit_log_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.entity_type}#{self.entity_id} {self.action}"


class IdempotencyKey(models.Model):
    """Replay cache for retryable writes. Invoicing spec §6.6: the rep app runs in
    low-connectivity conditions, so "create sales invoice" / "record payment" /
    "confirm receipt" must be safe to retry without double-inserting.

    The stored response is replayed verbatim when the same key arrives again. A
    matching key with a *different* request body is rejected rather than replayed,
    which catches client bugs that reuse a key for a new operation.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="idempotency_keys",
    )
    actor_type = models.CharField(max_length=16, choices=ActorType.choices)
    actor_id = models.BigIntegerField(null=True, blank=True)
    scope = models.CharField(max_length=128, help_text="Operation name, e.g. 'sales_invoice.create'.")
    key = models.CharField(max_length=128, help_text="Client-supplied Idempotency-Key header.")
    request_fingerprint = models.CharField(
        max_length=64,
        help_text="SHA-256 of the request body, to detect key reuse with different data.",
    )
    response_status = models.PositiveSmallIntegerField()
    response_body = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "idempotency_key"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "scope", "key"],
                name="idempotency_key_company_scope_key_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["created_at"], name="idempotency_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.scope}:{self.key}"
