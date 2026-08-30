"""Snapshot the company's currency onto every financial document.

Money columns carried no denomination: they were read as `Company.currency` at
display time, so changing that field re-denominated documents already issued.
Copying the code onto the document at creation freezes it alongside the rest of
the header snapshot (`company_name`, `tax_registration_no`).
"""

from django.db import migrations, models
from django.db.models import OuterRef, Subquery

HELP_TEXT = (
    "ISO 4217 code every money column on this document is denominated in. "
    "Snapshotted at creation so a later change to Company.currency cannot "
    "re-denominate a document that was already priced."
)


def backfill_currency(apps, schema_editor):
    """Existing rows take the currency their company trades in today.

    That is exactly what the code inferred for them before this column existed,
    so the backfill changes no displayed value — it only pins it.
    """
    company_currency = Subquery(
        apps.get_model("companies", "Company")
        .objects.filter(pk=OuterRef("company_id"))
        .values("currency")[:1]
    )
    for model_name in ("IncomingInvoice", "SalesInvoice", "ReturnInvoice"):
        apps.get_model("invoices", model_name).objects.filter(currency="").update(
            currency=company_currency
        )


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        ("invoices", "0005_alter_returninvoice_rep_alter_salesinvoice_rep_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="incominginvoice",
            name="currency",
            field=models.CharField(
                blank=True, default="", help_text=HELP_TEXT, max_length=3
            ),
        ),
        migrations.AddField(
            model_name="salesinvoice",
            name="currency",
            field=models.CharField(
                blank=True, default="", help_text=HELP_TEXT, max_length=3
            ),
        ),
        migrations.AddField(
            model_name="returninvoice",
            name="currency",
            field=models.CharField(
                blank=True, default="", help_text=HELP_TEXT, max_length=3
            ),
        ),
        migrations.RunPython(backfill_currency, migrations.RunPython.noop),
    ]
