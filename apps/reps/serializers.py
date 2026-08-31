"""Serializers for reps and rep-customer assignments."""

from __future__ import annotations

from rest_framework import serializers

from apps.customers.serializers import CustomerSerializer
from apps.products.models import Product, ProductWarehouseStock
from apps.products.services.images import primary_image_payload
from apps.reps.models import Rep, RepCustomerAssignment
from apps.reps.services.customers import EMPTY_BALANCE
from core.responses import decimal_string


class RepAssignmentSerializer(serializers.ModelSerializer):
    """Serializer for rep details with work days in customer assignment context."""
    
    rep_id = serializers.IntegerField(source='id', read_only=True)
    rep_name = serializers.CharField(source='name', read_only=True)
    rep_phone = serializers.CharField(source='phone', read_only=True)
    company_id = serializers.IntegerField(read_only=True)
    assignment_work_days = serializers.SerializerMethodField()
    
    class Meta:
        model = Rep
        fields = [
            'rep_id',
            'rep_name',
            'rep_phone',
            'company_id',
            'work_days',
            'assignment_work_days',
        ]
    
    def get_assignment_work_days(self, obj):
        """Get work days for this specific customer-rep assignment."""
        customer_id = self.context.get('customer_id')
        if not customer_id:
            return obj.work_days
        
        try:
            assignment = RepCustomerAssignment.objects.get(
                rep_id=obj.id,
                customer_id=customer_id
            )
            return assignment.work_days if assignment.work_days else obj.work_days
        except RepCustomerAssignment.DoesNotExist:
            return obj.work_days


class RepCustomerAssignmentSerializer(serializers.Serializer):
    """Serializer for assigning reps to customers with work days."""
    
    rep_id = serializers.IntegerField(required=True)
    work_days = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Work days for this assignment (e.g., ['sunday', 'monday']). Empty means use rep's default."
    )
    
    def validate_work_days(self, value):
        """Validate work days are valid day names."""
        valid_days = {
            'sunday', 'monday', 'tuesday', 'wednesday', 
            'thursday', 'friday', 'saturday',
            'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء',
            'الخميس', 'الجمعة', 'السبت'
        }
        
        if value:
            invalid_days = [day for day in value if day.lower() not in valid_days]
            if invalid_days:
                raise serializers.ValidationError(
                    f"أيام غير صالحة: {', '.join(invalid_days)}"
                )
        
        return [day.lower() for day in value] if value else []


class CustomerLocationWorkDaysUpdateSerializer(serializers.Serializer):
    """Serializer for rep updating customer address, location and work days.

    The rep standing outside the shop is the one who knows where it actually is,
    so all three are theirs to correct. Every field is optional — the client
    sends only what changed.
    """

    address = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Street / neighbourhood / city, as a rep would read it"
    )
    latitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True
    )
    longitude = serializers.DecimalField(
        max_digits=9,
        decimal_places=6,
        required=False,
        allow_null=True
    )
    work_days = serializers.ListField(
        child=serializers.CharField(),
        required=False,
        allow_empty=True,
        help_text="Work days for this customer"
    )
    
    def validate_work_days(self, value):
        """Validate work days are valid day names."""
        valid_days = {
            'sunday', 'monday', 'tuesday', 'wednesday', 
            'thursday', 'friday', 'saturday',
            'الأحد', 'الإثنين', 'الثلاثاء', 'الأربعاء',
            'الخميس', 'الجمعة', 'السبت'
        }
        
        if value:
            invalid_days = [day for day in value if day.lower() not in valid_days]
            if invalid_days:
                raise serializers.ValidationError(
                    f"أيام غير صالحة: {', '.join(invalid_days)}"
                )
        
        return [day.lower() for day in value] if value else []
    
    def validate(self, data):
        """Validate GPS coordinates are provided together."""
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        
        # Both or neither (but allow null for both to clear location)
        if (latitude is not None) != (longitude is not None):
            raise serializers.ValidationError({
                "location": "يجب تقديم خطوط الطول والعرض معاً أو تركهما فارغين"
            })
        
        return data


class RepInventoryItemSerializer(serializers.ModelSerializer):
    """One product sitting in the rep's van.

    Reads a `ProductWarehouseStock` row — the projection maintained by
    `apps.products.services.stock`, never a second count — and adds the two
    things a stock line on a phone shows next to the quantity: the unit it is
    counted in, and what it sells for.

    `unit_price` comes from `context["prices"]`, resolved for the whole page in
    one query by `products.services.pricing.general_prices_by_product`. It is the
    general catalog price and null when the catalog has none, matching what
    `resolve_unit_price` hands the sales-invoice service; the price actually
    charged is still resolved per customer when the invoice is written, because
    a customer category can override it.
    """

    product_id = serializers.IntegerField(read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_sku = serializers.CharField(source="product.sku", read_only=True)
    product_barcode = serializers.CharField(source="product.barcode", read_only=True)
    unit = serializers.IntegerField(source="product.unit_id", read_only=True)
    unit_name = serializers.CharField(source="product.unit.name", read_only=True)
    unit_code = serializers.CharField(source="product.unit.code", read_only=True)
    unit_price = serializers.SerializerMethodField()
    is_low_stock = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = ProductWarehouseStock
        fields = [
            "id",
            "product_id",
            "product_name",
            "product_sku",
            "product_barcode",
            "unit",
            "unit_name",
            "unit_code",
            "quantity",
            "unit_price",
            "is_low_stock",
            "image",
            "updated_at",
        ]
        read_only_fields = fields

    def get_unit_price(self, obj):
        price = (self.context.get("prices") or {}).get(obj.product_id)
        return decimal_string(price) if price is not None else None

    def get_is_low_stock(self, obj):
        """Whether the van is at or below the product's reorder point.

        Null when the product has no reorder point, so the app can tell "healthy"
        apart from "not tracked" — the same rule
        `ProductWarehouseStockSerializer` applies on the admin side.
        """
        reorder_point = obj.product.reorder_point
        if reorder_point is None:
            return None
        return obj.quantity <= reorder_point

    def get_image(self, obj):
        return primary_image_payload(obj.product, self.context.get("request"))


#: Attribute the rep customer views prefetch this rep's own assignment into.
MY_ASSIGNMENTS_ATTR = "my_assignments"


class RepCustomerSerializer(CustomerSerializer):
    """A store as the rep's own screens show it.

    Extends the shared `CustomerSerializer` rather than replacing it, so a store
    reads the same everywhere and the admin dashboard keeps every field it
    already had. What is added is the two things only a rep asks about: the days
    *they* visit this store, and what this store owes *them*.

    The money comes from `context["balances"]`, aggregated for the whole page in
    one query by `reps.services.customers.customer_balances`. A store with no
    invoices yet reports zeroes, not nulls — that is the "0 ل.س" the list prints.
    """

    work_days = serializers.SerializerMethodField()
    invoice_count = serializers.SerializerMethodField()
    total_invoiced = serializers.SerializerMethodField()
    paid_amount = serializers.SerializerMethodField()
    returned_amount = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta(CustomerSerializer.Meta):
        fields = [
            *CustomerSerializer.Meta.fields,
            "work_days",
            "invoice_count",
            "total_invoiced",
            "paid_amount",
            "returned_amount",
            "balance_due",
        ]

    def _balance(self, obj) -> dict:
        return (self.context.get("balances") or {}).get(obj.id, EMPTY_BALANCE)

    def get_work_days(self, obj):
        """The days this rep visits this store.

        Falls back to the rep's own default when the assignment names none —
        `RepCustomerAssignment.get_effective_work_days` owns that rule, so the
        list badge and the assignment editor cannot disagree about it.
        """
        assignments = getattr(obj, MY_ASSIGNMENTS_ATTR, None)
        if assignments is None:
            rep_id = self.context.get("rep_id")
            assignments = (
                list(obj.rep_assignments.filter(rep_id=rep_id).select_related("rep"))
                if rep_id
                else []
            )
        return assignments[0].get_effective_work_days() if assignments else []

    def get_invoice_count(self, obj) -> int:
        return self._balance(obj)["invoice_count"]

    def get_total_invoiced(self, obj) -> str:
        return self._balance(obj)["total_invoiced"]

    def get_paid_amount(self, obj) -> str:
        return self._balance(obj)["paid_amount"]

    def get_returned_amount(self, obj) -> str:
        return self._balance(obj)["returned_amount"]

    def get_balance_due(self, obj) -> str:
        return self._balance(obj)["balance_due"]


class RepProductSerializer(serializers.ModelSerializer):
    """A product as the rep's picker shows it: what it is, what it sells for,
    and how many the rep already has on board.

    `van_quantity` is the "بالسيارة N" under each row — the whole reason this
    exists rather than the rep reading `/api/companies/products/`. A rep about to
    order stock needs to see what they are already carrying, or they order a
    second carton of something sitting in the van.

    Both `price` and `van_quantity` come from context, batched for the page by
    the viewset: one query for every price, one for every quantity, instead of
    two per row. `price` is the general shelf price and is null when the catalog
    has none — null means "not priced", not "free".
    """

    unit = serializers.IntegerField(source="unit_id", read_only=True)
    unit_name = serializers.CharField(source="unit.name", read_only=True)
    unit_code = serializers.CharField(source="unit.code", read_only=True)
    price = serializers.SerializerMethodField()
    van_quantity = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "barcode",
            "category",
            "unit",
            "unit_name",
            "unit_code",
            "price",
            "van_quantity",
            "image",
        ]
        read_only_fields = fields

    def get_price(self, obj):
        price = (self.context.get("prices") or {}).get(obj.id)
        return decimal_string(price) if price is not None else None

    def get_van_quantity(self, obj) -> str:
        """Zero, not null, for a product the rep is not carrying.

        The picker prints it for every row; "none on board" is a known quantity,
        not a missing one.
        """
        return decimal_string(
            (self.context.get("van_quantities") or {}).get(obj.id, 0), places=3
        )

    def get_image(self, obj):
        return primary_image_payload(obj, self.context.get("request"))
