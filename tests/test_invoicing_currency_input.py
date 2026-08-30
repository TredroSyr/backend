"""`currency` as a document input, defaulting to the company's.

The interesting part is not that the code is stored — it is that prices are held
per currency, so the code a document is priced in has to drive line resolution
too. A document labelled USD whose lines came from the SYP price rows is worse
than no currency field at all: the number looks deliberate and is wrong.

Returns are the deliberate exception and are pinned here as such: they inherit
from the sale they credit, never from the company and never from the client.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.authentication.utils import generate_tokens_for_subuser
from apps.common.models import Currency
from apps.invoices.models import (
    CustomerCreditStatus,
    IncomingInvoice,
    PendingCustomerCredit,
    RefundMethod,
    SalesInvoice,
)
from apps.invoices.services.documents import LineInput
from apps.invoices.services.payments import collect_payment
from apps.invoices.services.returns import create_return_invoice, issue_return_invoice
from apps.invoices.services.sales import create_sales_invoice
from apps.products.models import ProductPrice


@pytest.fixture
def admin_client(owner) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {generate_tokens_for_subuser(owner)['access']}"
    )
    return client


@pytest.fixture
def usd(db) -> Currency:
    currency, _ = Currency.objects.get_or_create(
        code="USD", defaults={"name": "US Dollar", "symbol": "$"}
    )
    return currency


@pytest.fixture
def product_priced_in_usd(product, usd) -> ProductPrice:
    """The same product, 10.00 SYP from conftest and 0.50 USD here.

    Two very different numbers on purpose: a test that picked the wrong price row
    could not pass by coincidence.
    """
    return ProductPrice.objects.create(
        product=product, currency=usd, price=Decimal("0.50"), is_default=False
    )


def post_sale(client, rep, customer, product, **overrides):
    payload = {
        "customer_id": customer.id,
        "rep": rep.id,
        "lines": [{"product_id": product.id, "quantity": "10"}],
        **overrides,
    }
    return client.post("/api/companies/sales-invoices/", payload, format="json")


# ---------------------------------------------------------------------------
# The default
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_omitting_currency_uses_the_company_currency(
    admin_client, company, rep, customer, product, stocked_rep_warehouse
):
    response = post_sale(admin_client, rep, customer, product)

    assert response.status_code == 201, response.data
    assert response.data["data"]["invoice"]["currency"] == company.currency == "SYP"


@pytest.mark.django_db
def test_the_service_defaults_too(company, rep, customer, product, stocked_rep_warehouse):
    """Callers below the API — other services, scripts — get the same default."""
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[LineInput(product=product, quantity=Decimal("1"), unit_price=Decimal("10.00"))],
    )

    assert invoice.currency == "SYP"


# ---------------------------------------------------------------------------
# Taking the client's currency
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_sale_is_stored_in_the_currency_it_was_given(
    admin_client, rep, customer, product, product_priced_in_usd, stocked_rep_warehouse
):
    response = post_sale(admin_client, rep, customer, product, currency="USD")

    assert response.status_code == 201, response.data
    invoice = SalesInvoice.objects.get(id=response.data["data"]["invoice"]["id"])
    assert invoice.currency == "USD"


@pytest.mark.django_db
def test_lines_are_priced_from_the_documents_currency(
    admin_client, rep, customer, product, product_priced_in_usd, stocked_rep_warehouse
):
    """10 units: 10.00 each in SYP, 0.50 each in USD. The total says which won."""
    response = post_sale(admin_client, rep, customer, product, currency="USD")

    invoice = response.data["data"]["invoice"]
    assert invoice["total_amount"] == "5.00"
    assert [line["unit_price"] for line in invoice["lines"]] == ["0.50"]


@pytest.mark.django_db
def test_the_company_currency_still_prices_from_its_own_rows(
    admin_client, rep, customer, product, product_priced_in_usd, stocked_rep_warehouse
):
    """The other half of the previous test: adding a USD price must not disturb
    the default path.
    """
    response = post_sale(admin_client, rep, customer, product)

    assert response.data["data"]["invoice"]["total_amount"] == "100.00"


@pytest.mark.django_db
def test_an_explicit_unit_price_is_taken_as_given(
    admin_client, rep, customer, product, product_priced_in_usd, stocked_rep_warehouse
):
    """Currency picks the price rows to *resolve* from; it never overrides a
    price the client actually sent.
    """
    response = post_sale(
        admin_client,
        rep,
        customer,
        product,
        currency="USD",
        lines=[{"product_id": product.id, "quantity": "10", "unit_price": "2.25"}],
    )

    assert response.data["data"]["invoice"]["total_amount"] == "22.50"


@pytest.mark.django_db
def test_the_code_is_normalised(
    admin_client, rep, customer, product, product_priced_in_usd, stocked_rep_warehouse
):
    response = post_sale(admin_client, rep, customer, product, currency="usd")

    assert response.data["data"]["invoice"]["currency"] == "USD"


@pytest.mark.django_db
def test_incoming_invoices_take_a_currency_too(
    admin_client, company_warehouse, product, usd
):
    response = admin_client.post(
        "/api/companies/incoming-invoices/",
        {
            "warehouse": company_warehouse.id,
            "currency": "USD",
            "lines": [{"product_id": product.id, "quantity": "5", "unit_price": "1.00"}],
        },
        format="json",
    )

    assert response.status_code == 201, response.data
    invoice = IncomingInvoice.objects.get(id=response.data["data"]["invoice"]["id"])
    assert invoice.currency == "USD"


# ---------------------------------------------------------------------------
# Rejections
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_an_unknown_currency_is_rejected(
    admin_client, rep, customer, product, stocked_rep_warehouse
):
    response = post_sale(admin_client, rep, customer, product, currency="XYZ")

    assert response.status_code == 400
    assert "currency" in response.data["errors"]
    assert not SalesInvoice.objects.exists()


@pytest.mark.django_db
def test_a_deactivated_currency_is_rejected(
    admin_client, rep, customer, product, product_priced_in_usd, usd, stocked_rep_warehouse
):
    """The catalog is how a company retires a currency; a retired one must not
    keep arriving on new documents.
    """
    usd.is_active = False
    usd.save(update_fields=["is_active"])

    response = post_sale(admin_client, rep, customer, product, currency="USD")

    assert response.status_code == 400
    assert "currency" in response.data["errors"]


@pytest.mark.django_db
def test_a_currency_with_no_prices_names_itself_in_the_error(
    admin_client, rep, customer, product, usd, stocked_rep_warehouse
):
    """`product` is priced in SYP only. Without the code in the message this
    reads as "no price for this product", which sends you looking in the wrong
    place.
    """
    response = post_sale(admin_client, rep, customer, product, currency="USD")

    assert response.status_code == 400
    assert "USD" in " ".join(response.data["errors"]["lines"])


# ---------------------------------------------------------------------------
# Returns are the exception
# ---------------------------------------------------------------------------


@pytest.mark.django_db
def test_a_return_inherits_the_sale_currency_not_the_company_one(
    company, rep, customer, product, product_priced_in_usd, stocked_rep_warehouse
):
    """The credit is subtracted from the sale's total, so the two must agree —
    which is why this one document type does not take a currency.
    """
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[LineInput(product=product, quantity=Decimal("4"), unit_price=Decimal("0.50"))],
        currency="USD",
    )

    return_invoice = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.first().id, Decimal("1"))],
        refund_method=RefundMethod.CASH_REFUNDED_BY_REP,
    )

    assert invoice.currency == "USD"
    assert return_invoice.currency == "USD"
    assert company.currency == "SYP"


@pytest.mark.django_db
def test_a_later_company_switch_does_not_re_denominate(
    company, rep, customer, product, stocked_rep_warehouse
):
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[LineInput(product=product, quantity=Decimal("1"), unit_price=Decimal("10.00"))],
    )

    company.currency = "USD"
    company.save(update_fields=["currency"])
    invoice.refresh_from_db()

    assert invoice.currency == "SYP"


# ---------------------------------------------------------------------------
# Credits carry the currency of the sale they came back from
# ---------------------------------------------------------------------------


def credit_in(company, rep, customer, product, currency: str, unit_price: Decimal):
    """Sell, pay in full, then return the lot — the overage becomes a credit.

    `deferred_customer_credit` is the only path that mints one, and it needs the
    invoice already settled, so the whole cycle has to run.
    """
    invoice = create_sales_invoice(
        company_id=company.id,
        rep=rep,
        customer=customer,
        lines=[LineInput(product=product, quantity=Decimal("10"), unit_price=unit_price)],
        currency=currency,
    )
    collect_payment(
        company_id=company.id, invoice_id=invoice.id, amount=invoice.total_amount
    )
    return_invoice = create_return_invoice(
        company_id=company.id,
        sales_invoice=invoice,
        requested_lines=[(invoice.lines.first().id, Decimal("10"))],
        refund_method=RefundMethod.DEFERRED_CUSTOMER_CREDIT,
    )
    issue_return_invoice(return_invoice)

    return PendingCustomerCredit.objects.get(source_return_invoice=return_invoice)


@pytest.mark.django_db
def test_a_credit_cannot_be_spent_in_another_currency(
    admin_client, company, rep, customer, product, product_priced_in_usd,
    stocked_rep_warehouse,
):
    """A 5.00 USD credit against a SYP invoice would silently subtract 5 SYP.

    Nothing caught this before because every document shared the company's
    currency; now that they need not, the credit path is where the two meet.
    """
    credit = credit_in(company, rep, customer, product, "USD", Decimal("0.50"))

    response = post_sale(
        admin_client, rep, customer, product, credit_ids=[credit.id]
    )

    assert response.status_code == 400, response.data
    assert str(credit.id) in " ".join(response.data["errors"]["credit_ids"])
    credit.refresh_from_db()
    assert credit.status == CustomerCreditStatus.PENDING


@pytest.mark.django_db
def test_the_rejected_sale_is_not_written(
    admin_client, company, rep, customer, product, product_priced_in_usd,
    stocked_rep_warehouse,
):
    """The guard fires mid-creation, so the whole sale has to roll back."""
    credit = credit_in(company, rep, customer, product, "USD", Decimal("0.50"))
    before = SalesInvoice.objects.count()

    post_sale(admin_client, rep, customer, product, credit_ids=[credit.id])

    assert SalesInvoice.objects.count() == before


@pytest.mark.django_db
def test_a_credit_spends_normally_in_its_own_currency(
    admin_client, company, rep, customer, product, product_priced_in_usd,
    stocked_rep_warehouse,
):
    credit = credit_in(company, rep, customer, product, "USD", Decimal("0.50"))

    response = post_sale(
        admin_client, rep, customer, product, currency="USD", credit_ids=[credit.id]
    )

    assert response.status_code == 201, response.data
    invoice = response.data["data"]["invoice"]
    assert invoice["currency"] == "USD"
    assert invoice["paid_amount"] == "5.00"
    credit.refresh_from_db()
    assert credit.status == CustomerCreditStatus.APPLIED
