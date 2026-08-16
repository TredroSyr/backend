from __future__ import annotations

from django.db import migrations

SEED_UNITS = (
    ("liter", "Liter"),
    ("kg", "KG"),
    ("package", "Package"),
)


def seed_units(apps, schema_editor) -> None:
    UnitOfMeasure = apps.get_model("products", "UnitOfMeasure")
    for code, name in SEED_UNITS:
        UnitOfMeasure.objects.get_or_create(
            code=code, defaults={"name": name, "is_active": True}
        )


def unseed_units(apps, schema_editor) -> None:
    UnitOfMeasure = apps.get_model("products", "UnitOfMeasure")
    UnitOfMeasure.objects.filter(code__in=[code for code, _ in SEED_UNITS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_units, unseed_units),
    ]
