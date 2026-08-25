from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.common.models import Currency, UnitOfMeasure


class Command(BaseCommand):
    help = "Seed common data: units of measure and currencies"

    def handle(self, *args, **options) -> None:
        self.stdout.write("Seeding units of measure...")
        self.seed_units()

        self.stdout.write("Seeding currencies...")
        self.seed_currencies()

        self.stdout.write(self.style.SUCCESS("✓ Common data seeded successfully"))

    def seed_units(self) -> None:
        """Seed predefined units of measure."""
        units = [
            ("liter", "Liter"),
            ("kg", "KG"),
            ("package", "Package"),
        ]

        for code, name in units:
            unit, created = UnitOfMeasure.objects.get_or_create(
                code=code,
                defaults={"name": name, "is_active": True},
            )
            if created:
                self.stdout.write(f"  Created unit: {name}")
            else:
                self.stdout.write(f"  Unit already exists: {name}")

    def seed_currencies(self) -> None:
        """Seed common currencies (ISO 4217)."""
        currencies = [
            ("USD", "US Dollar", "$"),
            ("EUR", "Euro", "€"),
            ("SYP", "Syrian Pound", "ل.س"),
            ("GBP", "British Pound", "£"),
            ("TRY", "Turkish Lira", "₺"),
        ]

        for code, name, symbol in currencies:
            currency, created = Currency.objects.get_or_create(
                code=code,
                defaults={"name": name, "symbol": symbol, "is_active": True},
            )
            if created:
                self.stdout.write(f"  Created currency: {name} ({code})")
            else:
                self.stdout.write(f"  Currency already exists: {name} ({code})")
