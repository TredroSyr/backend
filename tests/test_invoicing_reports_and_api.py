"""Overdue reporting, rep cash reconciliation, and the retry-safety of the field API.

Covers spec §5 (pull-only overdue report), §3.5 rule 3 (the cash side of a
refund), §3.3 (a customer request is a signal, not a sale) and §6.6 (idempotent
writes for the rep app).
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_rep
from apps.invoices.models import RefundMethod, SalesInvoice
from apps.invoices.services.documents import LineInput, get_invoice_settings
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.reports import overdue_debt_report, rep_cash_reconciliation
from apps.invoices.services.returns import create_return_invoice, issue_return_invoice
from apps.invoices.services.sales import create_sales_invoice
from apps.notifications.models import Notification
from apps.orders.models import CustomerRequest
from apps.orders.services.requests import create_customer_request
from apps.products.services.stock import available_quantity


def make_sale(company, rep, customer, product, quantity="10", price="10.00"):
    return create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(
                product=product,
                quantity=Decimal(quantity),
                unit_price=Decimal(price),
            )
        ],
    )


def age(invoice: SalesInvoice, days: int) -> SalesInvoice:
    """Backdate an invoice. `created_at` is auto_now_add, so it needs an UPDATE."""
    SalesInvoice.objects.filter(id=invoice.id).update(
        created_at=timezone.now() - timedelta(days=days)
    )
    invoice.refresh_from_db()
    return invoice


# ---------------------------------------------------------------------------
# Overdue debt report (§5)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_fresh_unpaid_invoice_is_not_yet_overdue(
    company, rep, customer, stocked_rep_warehouse, product
):
    make_sale(company, rep, customer, product)
    report = overdue_debt_report(company.id)

    assert report["overdue_threshold_days"] == 7
    assert report["totals"]["invoice_count"] == 0


@pytest.mark.django_db
def test_an_invoice_past_the_threshold_shows_under_both_groupings(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = age(make_sale(company, rep, customer, product), days=10)
    report = overdue_debt_report(company.id)

    assert report["totals"]["invoice_count"] == 1
    assert report["totals"]["total_balance_due"] == "100.00"

    by_rep = report["by_rep"][0]
    assert by_rep["rep_id"] == rep.id
    assert by_rep["total_balance_due"] == "100.00"

    by_customer = report["by_customer"][0]
    assert by_customer["customer_id"] == customer.id
    assert by_customer["invoices"][0]["number"] == invoice.number
    assert by_customer["invoices"][0]["days_overdue"] >= 10


@pytest.mark.django_db
def test_a_settled_invoice_drops_off_the_report(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = age(make_sale(company, rep, customer, product), days=10)
    collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=Decimal("100.00")
    )

    assert overdue_debt_report(company.id)["totals"]["invoice_count"] == 0


@pytest.mark.django_db
def test_the_threshold_comes_from_invoice_settings(
    company, rep, customer, stocked_rep_warehouse, product
):
    age(make_sale(company, rep, customer, product), days=10)

    settings = get_invoice_settings(company.id)
    settings.overdue_threshold_days = 30
    settings.save(update_fields=["overdue_threshold_days", "updated_at"])

    report = overdue_debt_report(company.id)
    assert report["overdue_threshold_days"] == 30
    assert report["totals"]["invoice_count"] == 0


# ---------------------------------------------------------------------------
# Rep cash reconciliation (§3.5 rule 3, cash path)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_cash_refunds_are_deducted_from_the_reps_expected_cash_in(
    company, rep, customer, stocked_rep_warehouse, product
):
    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
        collected_by_id=rep.id,
    )

    credit_note = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.get().id, Decimal("3"))],
        refund_method=RefundMethod.CASH_REFUNDED_BY_REP,
    )
    issue_return_invoice(credit_note)

    report = rep_cash_reconciliation(company.id, rep_id=rep.id)
    row = report["by_rep"][0]

    assert row["cash_collected"] == "100.00"
    assert row["adjustments"] == "-30.00"
    assert row["expected_cash_in"] == "70.00"


@pytest.mark.django_db
def test_credit_applications_do_not_count_as_cash(
    company, rep, customer, stocked_rep_warehouse, product
):
    """No money changed hands for a credit, so it must not inflate the cash figure."""
    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("100.00"),
        collected_by_id=rep.id,
    )
    credit_note = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.get().id, Decimal("3"))],
        refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT,
    )
    issue_return_invoice(credit_note)

    next_sale = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[
            LineInput(product=product, quantity=Decimal("5"), unit_price=Decimal("10.00"))
        ],
        credit_ids=[credit_note.credits.get().id],
    )
    assert next_sale.paid_amount == Decimal("30.00")

    row = rep_cash_reconciliation(company.id, rep_id=rep.id)["by_rep"][0]
    assert row["cash_collected"] == "100.00"
    assert row["expected_cash_in"] == "100.00"


# ---------------------------------------------------------------------------
# Customer requests (§3.3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_customer_request_moves_no_stock_and_creates_no_financial_record(
    company, customer, rep, stocked_rep_warehouse, product
):
    create_customer_request(
        company_id=company.id,
        customer_id=customer.id,
        lines=[(product, Decimal("4"))],
    )

    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("100.000")
    assert SalesInvoice.objects.count() == 0


@pytest.mark.django_db
def test_a_customer_request_notifies_the_assigned_rep(company, customer, rep, product):
    create_customer_request(
        company_id=company.id,
        customer_id=customer.id,
        lines=[(product, Decimal("4"))],
    )

    notification = Notification.objects.get(event_key="customer_request.created")
    assert notification.recipient_actor_type == "rep"
    assert notification.recipient_actor_id == rep.id
    assert CustomerRequest.objects.get().rep_id == rep.id


# ---------------------------------------------------------------------------
# Retry safety for the field app (§6.6)
# ---------------------------------------------------------------------------


@pytest.fixture
def rep_client(rep) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_rep(rep)['access']}"
    )
    return client


@pytest.mark.django_db
def test_a_retried_sale_replays_instead_of_invoicing_twice(
    rep_client, customer, stocked_rep_warehouse, product
):
    payload = {
        "customer_id": customer.id,
        "lines": [{"product_id": product.id, "quantity": "3", "unit_price": "10.00"}],
    }
    headers = {"HTTP_IDEMPOTENCY_KEY": "visit-2026-08-29-001"}

    first = rep_client.post(
        "/api/reps/sales-invoices/", payload, format="json", **headers
    )
    second = rep_client.post(
        "/api/reps/sales-invoices/", payload, format="json", **headers
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.data["data"]["invoice"]["number"] == first.data["data"]["invoice"]["number"]

    assert SalesInvoice.objects.count() == 1
    assert available_quantity(stocked_rep_warehouse.id, product.id) == Decimal("97.000")


@pytest.mark.django_db
def test_the_same_key_with_different_data_is_rejected_not_replayed(
    rep_client, customer, stocked_rep_warehouse, product
):
    headers = {"HTTP_IDEMPOTENCY_KEY": "visit-2026-08-29-002"}
    rep_client.post(
        "/api/reps/sales-invoices/",
        {
            "customer_id": customer.id,
            "lines": [{"product_id": product.id, "quantity": "3", "unit_price": "10.00"}],
        },
        format="json",
        **headers,
    )

    conflict = rep_client.post(
        "/api/reps/sales-invoices/",
        {
            "customer_id": customer.id,
            "lines": [{"product_id": product.id, "quantity": "9", "unit_price": "10.00"}],
        },
        format="json",
        **headers,
    )

    assert conflict.status_code == 409
    assert SalesInvoice.objects.count() == 1


@pytest.mark.django_db
def test_without_a_key_two_posts_are_two_sales(
    rep_client, customer, stocked_rep_warehouse, product
):
    payload = {
        "customer_id": customer.id,
        "lines": [{"product_id": product.id, "quantity": "3", "unit_price": "10.00"}],
    }
    rep_client.post("/api/reps/sales-invoices/", payload, format="json")
    rep_client.post("/api/reps/sales-invoices/", payload, format="json")

    assert SalesInvoice.objects.count() == 2


@pytest.mark.django_db
def test_a_rep_only_sees_their_own_invoices(
    rep_client, company, other_rep, customer, stocked_rep_warehouse, product
):
    from apps.products.models import StockMovementType, Warehouse, WarehouseOwnerType
    from apps.products.services.stock import StockChange, apply_stock_changes

    other_warehouse = Warehouse.objects.create(
        company=company,
        name="Nour's van",
        owner_type=WarehouseOwnerType.REP,
        rep=other_rep,
    )
    apply_stock_changes(
        company_id=company.id,
        warehouse=other_warehouse,
        changes=[StockChange(product_id=product.id, quantity=Decimal("10"))],
        movement_type=StockMovementType.INITIAL,
        source_type="manual",
    )
    make_sale(company, other_rep, customer, product, quantity="1")

    response = rep_client.get("/api/reps/sales-invoices/")

    assert response.status_code == 200
    assert SalesInvoice.objects.count() == 1
    assert response.data["data"]["invoices"] == []


@pytest.mark.django_db
def test_every_monetary_value_is_a_decimal_string_not_a_float(
    rep_client, company, owner, rep, customer, stocked_rep_warehouse, product
):
    """Floats lose precision and force clients to parse money two ways."""
    import json

    from apps.authentication.utils import generate_tokens_for_subuser

    invoice = make_sale(company, rep, customer, product)
    collect_payment(
        company_id=company.id,
        invoice_id=invoice.id,
        amount=Decimal("40.00"),
        collected_by_id=rep.id,
    )
    age(invoice, days=30)

    admin = APIClient()
    admin.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )

    for url in (
        "/api/companies/reports/overdue-debts/",
        "/api/companies/reports/rep-cash/",
        "/api/companies/payment-collections/",
        "/api/reps/sales-invoices/",
    ):
        response = admin.get(url) if "companies" in url else rep_client.get(url)
        assert response.status_code == 200, url
        body = json.loads(response.content)

        def assert_no_float(node, path=url):
            if isinstance(node, float):
                raise AssertionError(f"float in JSON at {path}: {node}")
            if isinstance(node, dict):
                for key, value in node.items():
                    assert_no_float(value, f"{path}.{key}")
            elif isinstance(node, list):
                for index, value in enumerate(node):
                    assert_no_float(value, f"{path}[{index}]")

        assert_no_float(body)
