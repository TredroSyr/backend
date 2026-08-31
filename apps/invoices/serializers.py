"""Serializers for the invoicing module.

Split by direction on purpose:

* **Read** serializers expose the derived money fields (`paid_amount`,
  `returned_amount`, `balance_due`, `status`) but never accept them — §6.2 says
  those are computed, and a writable field is how they eventually drift.
* **Write** serializers validate input and hand the service layer resolved model
  instances. They do not create anything themselves; documents are created by
  `apps.invoices.services`, which is where the atomicity and stock rules live.
"""

from __future__ import annotations

from decimal import Decimal

from django.utils import timezone
from rest_framework import serializers

from apps.common.serializers import line_count_of

from apps.common.models import Currency
from apps.customers.models import Customer
from apps.invoices.models import (
    MONEY_ZERO,
    IncomingInvoice,
    IncomingInvoiceLine,
    InvoiceSettings,
    PaymentCollection,
    PendingCustomerCredit,
    RefundMethod,
    ReturnInvoice,
    ReturnInvoiceLine,
    SalesInvoice,
    SalesInvoiceLine,
)
from apps.invoices.services.documents import LineInput
from apps.products.models import PriceType, Warehouse
from apps.products.services.images import primary_image_payload
from apps.products.services.lookup import products_by_id, resolve_unit_price
from apps.reps.models import Rep

QUANTITY_KWARGS = {"max_digits": 14, "decimal_places": 3, "min_value": Decimal("0.001")}
MONEY_KWARGS = {"max_digits": 14, "decimal_places": 2, "min_value": MONEY_ZERO}


class InvoiceSettingsSerializer(serializers.ModelSerializer):
    """The single settings object shared by all invoice types (§6.8)."""

    display_company_name = serializers.CharField(read_only=True)

    class Meta:
        model = InvoiceSettings
        fields = [
            "company_name",
            "display_company_name",
            "tax_registration_no",
            "address",
            "phone",
            "overdue_threshold_days",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]


# ---------------------------------------------------------------------------
# Shared line handling
# ---------------------------------------------------------------------------


class LineReadSerializer(serializers.ModelSerializer):
    """Read shape common to every priced line.

    The product fields are what a line needs to render on its own — a document
    is read far more often than the catalog behind it, and a client should not
    have to fetch each product to draw a row. `unit` stays the line's own
    snapshot, not the product's current unit, so an old document keeps reading
    the way it was issued.
    """

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_barcode = serializers.CharField(source="product.barcode", read_only=True)
    product_image = serializers.SerializerMethodField(read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)

    class Meta:
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "product_barcode",
            "product_image",
            "unit",
            "unit_name",
            "unit_code",
            "quantity",
            "unit_price",
            "subtotal",
            "tax_rate",
        ]
        read_only_fields = fields

    def get_product_image(self, obj):
        """Cover image of the line's product, or None."""
        return primary_image_payload(obj.product, self.context.get("request"))


class IncomingInvoiceLineSerializer(LineReadSerializer):
    class Meta(LineReadSerializer.Meta):
        model = IncomingInvoiceLine


class SalesInvoiceLineSerializer(LineReadSerializer):
    returned_quantity = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True, required=False
    )

    class Meta(LineReadSerializer.Meta):
        model = SalesInvoiceLine
        fields = [*LineReadSerializer.Meta.fields, "returned_quantity"]
        read_only_fields = fields


class ReturnInvoiceLineSerializer(LineReadSerializer):
    class Meta(LineReadSerializer.Meta):
        model = ReturnInvoiceLine
        fields = [*LineReadSerializer.Meta.fields, "sales_invoice_line"]
        read_only_fields = fields


class PricedLineWriteSerializer(serializers.Serializer):
    """One posted line.

    `unit_price` is optional: when omitted it is resolved from the product
    catalog (customer-category price first, then the general price) on the
    document's own price list — standard when selling, cost when purchasing.
    """

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(**QUANTITY_KWARGS)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=MONEY_ZERO, required=False
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), required=False
    )


class CurrencyCodeField(serializers.CharField):
    """The currency a document is priced in, validated against the catalog.

    Companies pick from `Currency`, they do not invent codes (see that model), so
    an unknown or deactivated code is rejected here rather than being snapshotted
    onto a document nobody can price.
    """

    def __init__(self, **kwargs):
        kwargs.setdefault("max_length", 3)
        kwargs.setdefault("min_length", 3)
        kwargs.setdefault("required", False)
        kwargs.setdefault("allow_blank", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data) -> str:
        code = super().to_internal_value(data).strip().upper()
        if code and not Currency.objects.filter(code=code, is_active=True).exists():
            raise serializers.ValidationError("العملة غير معروفة أو غير مفعّلة")
        return code


class LinesWriteMixin:
    """Turns posted line dicts into `LineInput`s the service layer can consume."""

    #: Sales rejects non-sellable products; incoming stock does not care.
    sellable_only = False

    #: Which price list an omitted `unit_price` is resolved from. A purchase
    #: document overrides this to `cost`: falling back to the standard price
    #: there would book a supplier bill at what the goods are sold for.
    price_type = PriceType.STANDARD

    def document_currency(self, data: dict) -> str:
        """The code this document is priced in — the client's, or the company's.

        Resolved here rather than left to the service because the lines have to be
        priced in it before the service is ever called.
        """
        return data.get("currency") or self.context["company"].currency

    def build_line_inputs(
        self,
        lines_data: list[dict],
        *,
        customer: Customer | None = None,
        currency_code: str = "",
    ) -> list[LineInput]:
        company = self.context["company"]
        products = products_by_id(
            company.id,
            [line["product_id"] for line in lines_data],
            sellable_only=self.sellable_only,
        )

        inputs: list[LineInput] = []
        missing_price: list[int] = []

        for line in lines_data:
            product = products[line["product_id"]]
            unit_price = line.get("unit_price")

            if unit_price is None:
                unit_price = resolve_unit_price(
                    product,
                    company=company,
                    customer=customer,
                    currency_code=currency_code,
                    price_type=self.price_type,
                )

            if unit_price is None:
                missing_price.append(product.id)
                continue

            inputs.append(
                LineInput(
                    product=product,
                    quantity=line["quantity"],
                    unit_price=unit_price,
                    tax_rate=line.get("tax_rate")
                    if line.get("tax_rate") is not None
                    else (product.tax_rate or MONEY_ZERO),
                )
            )

        if missing_price:
            raise serializers.ValidationError(
                {
                    "lines": [
                        "لا يوجد سعر محدد لبعض المنتجات، يرجى إدخال السعر يدوياً",
                        f"Products without a resolvable {self.price_type} price in "
                        f"{currency_code or company.currency}: {missing_price}",
                    ]
                }
            )

        return inputs


class CompanyScopedPrimaryKeyRelatedField(serializers.PrimaryKeyRelatedField):
    """A related field restricted to the authenticated company's rows.

    Without this, an id from another tenant would resolve happily and only fail
    (or not) at a later check.
    """

    def get_queryset(self):
        return super().get_queryset().filter(company_id=self.context["company"].id)


# ---------------------------------------------------------------------------
# Incoming invoices
# ---------------------------------------------------------------------------


class IncomingInvoiceSerializer(serializers.ModelSerializer):
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)
    line_count = serializers.IntegerField(read_only=True, required=False)

    class Meta:
        model = IncomingInvoice
        fields = [
            "id",
            "number",
            "date",
            "supplier_ref",
            "company_name",
            "tax_registration_no",
            "currency",
            "warehouse",
            "warehouse_name",
            "status",
            "total_amount",
            "notes",
            "issued_at",
            "cancelled_at",
            "line_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class IncomingInvoiceDetailSerializer(IncomingInvoiceSerializer):
    lines = IncomingInvoiceLineSerializer(many=True, read_only=True)

    class Meta(IncomingInvoiceSerializer.Meta):
        fields = [*IncomingInvoiceSerializer.Meta.fields, "lines"]
        read_only_fields = fields


class IncomingInvoiceCreateSerializer(LinesWriteMixin, serializers.Serializer):
    """A supplier delivery. Lines are priced at what the supplier charged, so an
    omitted `unit_price` reads the product's cost list, never the sale price.
    """

    price_type = PriceType.COST

    warehouse = CompanyScopedPrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    lines = PricedLineWriteSerializer(many=True, allow_empty=False)
    date = serializers.DateTimeField(required=False)
    supplier_ref = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    #: Omit to invoice in the company's currency — the usual case. Send one to buy
    #: from a supplier who prices in something else.
    currency = CurrencyCodeField()

    def validate(self, data):
        data["currency"] = self.document_currency(data)
        data["line_inputs"] = self.build_line_inputs(
            data["lines"], currency_code=data["currency"]
        )
        return data


# ---------------------------------------------------------------------------
# Sales invoices
# ---------------------------------------------------------------------------


class SalesInvoiceSerializer(serializers.ModelSerializer):
    # allow_null keeps the key present as null on a company-direct sale; without
    # it DRF drops the field entirely when `rep` is None.
    rep_name = serializers.CharField(source="rep.name", read_only=True, allow_null=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    overage_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "number",
            "date",
            "line_count",
            "rep",
            "rep_name",
            "customer",
            "customer_name",
            "customer_phone",
            "warehouse",
            "company_name",
            "tax_registration_no",
            "currency",
            "total_amount",
            "paid_amount",
            "returned_amount",
            "balance_due",
            "overage_amount",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_line_count(self, obj) -> int:
        """How many product lines the invoice has — the "N صنف" on a list row.

        Three ways to get it, cheapest first, because the three callers arrive
        differently: the list endpoints annotate it, the detail endpoints have
        already prefetched the lines, and a one-off (the object returned after
        recording a payment) has neither and can afford the single query.
        """
        return line_count_of(obj)


class SalesInvoiceDetailSerializer(SalesInvoiceSerializer):
    lines = SalesInvoiceLineSerializer(many=True, read_only=True)
    payments = serializers.SerializerMethodField()
    returns = serializers.SerializerMethodField()
    fulfilled_request_ids = serializers.SerializerMethodField()

    class Meta(SalesInvoiceSerializer.Meta):
        fields = [
            *SalesInvoiceSerializer.Meta.fields,
            "lines",
            "payments",
            "returns",
            "fulfilled_request_ids",
        ]
        read_only_fields = fields

    def get_payments(self, obj):
        return PaymentCollectionSerializer(obj.payments.all(), many=True).data

    def get_returns(self, obj):
        return ReturnInvoiceSerializer(obj.returns.all(), many=True).data

    def get_fulfilled_request_ids(self, obj):
        return list(obj.fulfilled_requests.values_list("id", flat=True))


class SalesInvoiceCreateSerializer(LinesWriteMixin, serializers.Serializer):
    """Everything a rep can settle in one call: the sale, credits applied, and any
    cash handed over on the spot. All of it commits together.
    """

    sellable_only = True

    customer_id = serializers.IntegerField()
    lines = PricedLineWriteSerializer(many=True, allow_empty=False)
    warehouse = CompanyScopedPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True
    )
    date = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    credit_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    payment_amount = serializers.DecimalField(
        **MONEY_KWARGS, required=False, allow_null=True
    )
    payment_collected_at = serializers.DateTimeField(required=False, allow_null=True)
    fulfils_request_ids = serializers.ListField(
        child=serializers.IntegerField(), required=False, default=list
    )
    #: Omit to sell in the company's currency — the usual case. Send one to price
    #: this sale in another, and the lines resolve from that currency's prices.
    currency = CurrencyCodeField()

    def validate_customer_id(self, value):
        customer = Customer.objects.filter(id=value, is_active=True).first()
        if customer is None:
            raise serializers.ValidationError("العميل غير موجود أو غير نشط")
        return value

    def validate(self, data):
        customer = Customer.objects.get(id=data["customer_id"])
        data["customer"] = customer
        data["currency"] = self.document_currency(data)
        data["line_inputs"] = self.build_line_inputs(
            data["lines"], customer=customer, currency_code=data["currency"]
        )
        return data


# ---------------------------------------------------------------------------
# Return invoices
# ---------------------------------------------------------------------------


class ReturnInvoiceSerializer(serializers.ModelSerializer):
    sales_invoice_number = serializers.CharField(
        source="sales_invoice.number", read_only=True
    )
    rep_name = serializers.CharField(source="rep.name", read_only=True, allow_null=True)
    warehouse_name = serializers.CharField(source="warehouse.name", read_only=True)

    class Meta:
        model = ReturnInvoice
        fields = [
            "id",
            "number",
            "date",
            "sales_invoice",
            "sales_invoice_number",
            "rep",
            "rep_name",
            "warehouse",
            "warehouse_name",
            "company_name",
            "tax_registration_no",
            "currency",
            "status",
            "amount",
            "overage_amount",
            "refund_method",
            "notes",
            "issued_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class ReturnInvoiceDetailSerializer(ReturnInvoiceSerializer):
    lines = ReturnInvoiceLineSerializer(many=True, read_only=True)
    projected_overage_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True, required=False
    )

    class Meta(ReturnInvoiceSerializer.Meta):
        fields = [
            *ReturnInvoiceSerializer.Meta.fields,
            "lines",
            "projected_overage_amount",
        ]
        read_only_fields = fields


class ReturnLineWriteSerializer(serializers.Serializer):
    """Returns reference the sold line, not a bare product: that is what carries
    the original price and caps how much is still returnable.
    """

    sales_invoice_line_id = serializers.IntegerField()
    quantity = serializers.DecimalField(**QUANTITY_KWARGS)


class ReturnInvoiceCreateSerializer(serializers.Serializer):
    sales_invoice = CompanyScopedPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all()
    )
    lines = ReturnLineWriteSerializer(many=True, allow_empty=False)
    warehouse = CompanyScopedPrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True
    )
    date = serializers.DateTimeField(required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    refund_method = serializers.ChoiceField(
        choices=RefundMethod.choices, required=False, allow_blank=True, default=""
    )

    def validate(self, data):
        data["requested_lines"] = [
            (line["sales_invoice_line_id"], line["quantity"]) for line in data["lines"]
        ]
        return data


class ReturnInvoiceIssueSerializer(serializers.Serializer):
    """`refund_method` may also be supplied at issue time — the rep only learns
    whether cash is going back once the overage is known (§3.5 rule 3).
    """

    refund_method = serializers.ChoiceField(
        choices=RefundMethod.choices, required=False, allow_blank=True
    )


# ---------------------------------------------------------------------------
# Payments and credits
# ---------------------------------------------------------------------------


class PaymentCollectionSerializer(serializers.ModelSerializer):
    collected_by_name = serializers.CharField(
        source="collected_by.name", read_only=True, allow_null=True
    )
    sales_invoice_number = serializers.CharField(
        source="sales_invoice.number", read_only=True
    )

    class Meta:
        model = PaymentCollection
        fields = [
            "id",
            "sales_invoice",
            "sales_invoice_number",
            "amount",
            "collected_by",
            "collected_by_name",
            "collected_at",
            "source",
            "applied_credit",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class PaymentCollectionCreateSerializer(serializers.Serializer):
    sales_invoice = CompanyScopedPrimaryKeyRelatedField(
        queryset=SalesInvoice.objects.all()
    )
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=Decimal("0.01")
    )
    collected_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, default="")
    collected_by = CompanyScopedPrimaryKeyRelatedField(
        queryset=Rep.objects.all(), required=False, allow_null=True
    )

    def validate_collected_at(self, value):
        if value and value > timezone.now():
            raise serializers.ValidationError("لا يمكن تسجيل دفعة بتاريخ مستقبلي")
        return value


class PendingCustomerCreditSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    source_return_invoice_number = serializers.CharField(
        source="source_return_invoice.number", read_only=True
    )

    class Meta:
        model = PendingCustomerCredit
        fields = [
            "id",
            "customer",
            "customer_name",
            "source_return_invoice",
            "source_return_invoice_number",
            "amount",
            "status",
            "applied_to_invoice",
            "applied_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class AdminSalesInvoiceCreateSerializer(SalesInvoiceCreateSerializer):
    """Company-side sale creation.

    `rep` is optional and decides which kind of sale this is:

    * omitted -> a company-direct sale (a walk-in, or a customer buying from the
      company itself). Stock leaves a company warehouse and no rep is attributed.
    * supplied -> the sale is recorded on that rep's behalf and leaves their van,
      exactly as if they had posted it from the field app.

    `warehouse` still defaults correctly in both cases, so it only needs sending
    when the company has more than one warehouse and the goods left a specific one.
    """

    rep = CompanyScopedPrimaryKeyRelatedField(
        queryset=Rep.objects.all(), required=False, allow_null=True
    )
