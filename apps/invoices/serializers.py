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
from apps.products.models import Warehouse
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
    """Read shape common to every priced line."""

    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)

    class Meta:
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit",
            "unit_name",
            "quantity",
            "unit_price",
            "subtotal",
            "tax_rate",
        ]
        read_only_fields = fields


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
    """One posted line. `unit_price` is optional: when omitted it is resolved from
    the product catalog (customer-category price first, then the general price).
    """

    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(**QUANTITY_KWARGS)
    unit_price = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=MONEY_ZERO, required=False
    )
    tax_rate = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=Decimal("0"), required=False
    )


class LinesWriteMixin:
    """Turns posted line dicts into `LineInput`s the service layer can consume."""

    #: Sales rejects non-sellable products; incoming stock does not care.
    sellable_only = False

    def build_line_inputs(
        self, lines_data: list[dict], *, customer: Customer | None = None
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
                    product, company=company, customer=customer
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
                        f"Products without a resolvable price: {missing_price}",
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
    warehouse = CompanyScopedPrimaryKeyRelatedField(queryset=Warehouse.objects.all())
    lines = PricedLineWriteSerializer(many=True, allow_empty=False)
    date = serializers.DateTimeField(required=False)
    supplier_ref = serializers.CharField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        data["line_inputs"] = self.build_line_inputs(data["lines"])
        return data


# ---------------------------------------------------------------------------
# Sales invoices
# ---------------------------------------------------------------------------


class SalesInvoiceSerializer(serializers.ModelSerializer):
    rep_name = serializers.CharField(source="rep.name", read_only=True)
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    overage_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = SalesInvoice
        fields = [
            "id",
            "number",
            "date",
            "rep",
            "rep_name",
            "customer",
            "customer_name",
            "customer_phone",
            "warehouse",
            "company_name",
            "tax_registration_no",
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

    def validate_customer_id(self, value):
        customer = Customer.objects.filter(id=value, is_active=True).first()
        if customer is None:
            raise serializers.ValidationError("العميل غير موجود أو غير نشط")
        return value

    def validate(self, data):
        customer = Customer.objects.get(id=data["customer_id"])
        data["customer"] = customer
        data["line_inputs"] = self.build_line_inputs(data["lines"], customer=customer)
        return data


# ---------------------------------------------------------------------------
# Return invoices
# ---------------------------------------------------------------------------


class ReturnInvoiceSerializer(serializers.ModelSerializer):
    sales_invoice_number = serializers.CharField(
        source="sales_invoice.number", read_only=True
    )
    rep_name = serializers.CharField(source="rep.name", read_only=True)
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
