"""Serializers for stock transfers and customer requests.

Neither document carries money, so unlike the invoice serializers there is no
price to resolve — lines are just a product and a quantity. Status is never
writable: transitions go through `apps.orders.services.transfers`, which is what
enforces the state machine and writes the audit trail.
"""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.common.serializers import line_count_of
from apps.companies.models import Company
from apps.orders.models import (
    MAX_PICKUP_WINDOW_HOURS,
    CustomerRequest,
    CustomerRequestLine,
    StockTransfer,
    StockTransferLine,
)
from apps.products.models import Warehouse
from apps.products.services.lookup import products_by_id
from apps.reps.models import Rep
from core.responses import decimal_string

QUANTITY_KWARGS = {"max_digits": 14, "decimal_places": 3, "min_value": Decimal("0.001")}


class ProductLineReadSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)


class QuantityLineWriteSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.DecimalField(**QUANTITY_KWARGS)


class ProductLinesWriteMixin:
    """Resolves posted `(product_id, quantity)` pairs against the company catalog."""

    sellable_only = False

    def build_product_lines(self, lines_data: list[dict]):
        company_id = self.context["company"].id
        products = products_by_id(
            company_id,
            [line["product_id"] for line in lines_data],
            sellable_only=self.sellable_only,
        )
        return [
            (products[line["product_id"]], line["quantity"]) for line in lines_data
        ]


# ---------------------------------------------------------------------------
# Stock transfers
# ---------------------------------------------------------------------------


class StockTransferLineSerializer(ProductLineReadSerializer):
    """A product being moved, with what it is worth at today's shelf price.

    A transfer carries no money — it is stock moving between two warehouses of
    the same company, and nobody is being charged. `unit_price` and `line_total`
    are resolved from the catalog on read purely so the rep can see the value of
    what they are asking for, and are null when the caller did not ask for
    pricing or the catalog has no price.

    The value is priced on `effective_qty`, not `requested_qty`: once an admin
    trims a line, what the rep is getting is the approved amount.
    """

    effective_qty = serializers.DecimalField(
        max_digits=14, decimal_places=3, read_only=True
    )
    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = StockTransferLine
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit",
            "unit_name",
            "requested_qty",
            "approved_qty",
            "effective_qty",
            "unit_price",
            "line_total",
        ]
        read_only_fields = fields

    def _price(self, obj):
        return (self.context.get("product_prices") or {}).get(obj.product_id)

    def get_unit_price(self, obj):
        price = self._price(obj)
        return decimal_string(price) if price is not None else None

    def get_line_total(self, obj):
        price = self._price(obj)
        return decimal_string(price * obj.effective_qty) if price is not None else None


class StockTransferSerializer(serializers.ModelSerializer):
    rep_name = serializers.CharField(source="rep.name", read_only=True)
    pickup_deadline = serializers.DateTimeField(read_only=True, allow_null=True)
    line_count = serializers.SerializerMethodField()
    source_warehouse_name = serializers.CharField(
        source="source_warehouse.name", read_only=True
    )
    destination_warehouse_name = serializers.CharField(
        source="destination_warehouse.name", read_only=True
    )

    class Meta:
        model = StockTransfer
        fields = [
            "id",
            "number",
            "rep",
            "rep_name",
            "source_warehouse",
            "source_warehouse_name",
            "destination_warehouse",
            "destination_warehouse_name",
            "status",
            "requested_at",
            "pickup_within_hours",
            "pickup_deadline",
            "approved_at",
            "received_at",
            "cancelled_at",
            "line_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_line_count(self, obj) -> int:
        return line_count_of(obj)


class StockTransferDetailSerializer(StockTransferSerializer):
    """Adds the lines, and the total the request card prints."""

    lines = StockTransferLineSerializer(many=True, read_only=True)
    estimated_total = serializers.SerializerMethodField()

    class Meta(StockTransferSerializer.Meta):
        fields = [
            *StockTransferSerializer.Meta.fields,
            "lines",
            "estimated_total",
        ]
        read_only_fields = fields

    def get_estimated_total(self, obj):
        """Shelf value of everything on the transfer, or null if nothing priced.

        A line the catalog cannot price is skipped rather than counted as free,
        so this can be a partial figure — compare `lines[].unit_price` against
        null if the screen needs to say so.
        """
        prices = self.context.get("product_prices") or {}
        priced = [
            prices[line.product_id] * line.effective_qty
            for line in obj.lines.all()
            if line.product_id in prices
        ]
        return decimal_string(sum(priced)) if priced else None


class StockTransferCreateSerializer(ProductLinesWriteMixin, serializers.Serializer):
    """A rep asking the company for goods. Warehouses default to the company's
    main warehouse and the rep's own, so the field client can omit both.
    """

    lines = QuantityLineWriteSerializer(many=True, allow_empty=False)
    source_warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True
    )
    destination_warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True
    )
    pickup_within_hours = serializers.IntegerField(
        required=False,
        allow_null=True,
        min_value=1,
        max_value=MAX_PICKUP_WINDOW_HOURS,
        help_text=(
            "Hours from now the rep expects to collect in. The app offers "
            "1/2/3/4/6; anything up to 24 is accepted."
        ),
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate(self, data):
        data["product_lines"] = self.build_product_lines(data["lines"])
        return data


class StockTransferDispatchSerializer(ProductLinesWriteMixin, serializers.Serializer):
    """The office sending goods to a rep who never asked (§3.2, dispatch origin).

    Same body as a rep's request plus the `rep` being sent to — which is the whole
    difference, since a rep's own id comes from their token and can never be
    chosen.
    """

    rep = serializers.IntegerField()
    lines = QuantityLineWriteSerializer(many=True, allow_empty=False)
    source_warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True
    )
    destination_warehouse = serializers.PrimaryKeyRelatedField(
        queryset=Warehouse.objects.all(), required=False, allow_null=True
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_rep(self, value):
        """Scope the rep to the caller's company, so an id cannot cross tenants."""
        rep = Rep.objects.filter(
            id=value, company_id=self.context["company"].id, is_active=True
        ).first()
        if rep is None:
            raise serializers.ValidationError("المندوب غير موجود أو غير نشط")
        self.context["rep"] = rep
        return value

    def validate(self, data):
        data["rep_instance"] = self.context["rep"]
        data["product_lines"] = self.build_product_lines(data["lines"])
        return data


class StockTransferModifySerializer(serializers.Serializer):
    """Admin cutting approved quantities. Lines not listed keep what was requested."""

    lines = serializers.ListField(
        child=serializers.DictField(), allow_empty=False
    )

    def validate_lines(self, value):
        approved: dict[int, Decimal] = {}
        for entry in value:
            try:
                line_id = int(entry["line_id"])
                quantity = Decimal(str(entry["approved_qty"]))
            except (KeyError, TypeError, ValueError, ArithmeticError):
                raise serializers.ValidationError(
                    "كل بند يجب أن يحتوي على line_id و approved_qty"
                )
            approved[line_id] = quantity
        return approved


# ---------------------------------------------------------------------------
# Customer requests
# ---------------------------------------------------------------------------


class CustomerRequestLineSerializer(ProductLineReadSerializer):
    """A wanted product, with what it would cost today.

    `unit_price` and `line_total` are **indicative, not agreed**: nothing is
    stored on the line, and both are resolved from the catalog on read by
    `orders.services.request_pricing`. They are null when the caller did not ask
    for pricing, or when the catalog has no price for that product — null means
    "not priced", which is not the same claim as zero.
    """

    unit_price = serializers.SerializerMethodField()
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CustomerRequestLine
        fields = [
            "id",
            "product",
            "product_name",
            "product_sku",
            "unit",
            "unit_name",
            "desired_quantity",
            "unit_price",
            "line_total",
        ]
        read_only_fields = fields

    def _price(self, obj):
        return (self.context.get("line_prices") or {}).get(obj.id)

    def get_unit_price(self, obj):
        price = self._price(obj)
        return decimal_string(price) if price is not None else None

    def get_line_total(self, obj):
        price = self._price(obj)
        return decimal_string(price * obj.desired_quantity) if price is not None else None


class CustomerRequestSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.name", read_only=True)
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    rep_name = serializers.CharField(
        source="rep.name", read_only=True, allow_null=True
    )
    fulfilled_by_invoice_number = serializers.CharField(
        source="fulfilled_by_invoice.number", read_only=True, allow_null=True
    )
    line_count = serializers.SerializerMethodField()

    class Meta:
        model = CustomerRequest
        fields = [
            "id",
            "company",
            "customer",
            "customer_name",
            "customer_phone",
            "rep",
            "rep_name",
            "status",
            "fulfilled_by_invoice",
            "fulfilled_by_invoice_number",
            "fulfilled_at",
            "cancelled_at",
            "accepted_at",
            "rejected_at",
            "rejection_reason",
            "line_count",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_line_count(self, obj) -> int:
        return line_count_of(obj)


class CustomerRequestDetailSerializer(CustomerRequestSerializer):
    """Adds the lines, and the card total they add up to."""

    lines = CustomerRequestLineSerializer(many=True, read_only=True)
    estimated_total = serializers.SerializerMethodField()

    class Meta(CustomerRequestSerializer.Meta):
        fields = [
            *CustomerRequestSerializer.Meta.fields,
            "lines",
            "estimated_total",
        ]
        read_only_fields = fields

    def get_estimated_total(self, obj):
        """What the request is worth at today's catalog prices.

        Null when nothing on it could be priced, so the card can say "no price"
        rather than print a confident zero. A line the catalog cannot price is
        skipped rather than counted as free, so compare `lines[].unit_price`
        against null if the distinction matters to the screen.
        """
        prices = self.context.get("line_prices") or {}
        priced = [
            prices[line.id] * line.desired_quantity
            for line in obj.lines.all()
            if line.id in prices
        ]
        return decimal_string(sum(priced)) if priced else None


class CustomerRequestCreateSerializer(ProductLinesWriteMixin, serializers.Serializer):
    """Posted from the customer app. `company_id` names the company being browsed —
    customers are global entities and are not bound to one tenant.
    """

    sellable_only = True

    company_id = serializers.IntegerField()
    lines = QuantityLineWriteSerializer(many=True, allow_empty=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_company_id(self, value):
        company = Company.objects.filter(id=value, is_active=True).first()
        if company is None:
            raise serializers.ValidationError("الشركة غير موجودة أو غير نشطة")
        # The browsing customer has no tenant of their own, so the company that
        # scopes the product lookup comes from the payload, not from a JWT claim.
        self.context["company"] = company
        return value

    def validate(self, data):
        data["product_lines"] = self.build_product_lines(data["lines"])
        return data
