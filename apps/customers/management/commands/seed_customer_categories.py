from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.customers.models import CustomerCategory


class Command(BaseCommand):
    help = "Seed default customer categories (global, company-agnostic)"

    def handle(self, *args, **options) -> None:
        self.stdout.write("Seeding default customer categories...")

        default_categories = [
            'تاجر جملة',  # Wholesale merchant
            'تاجر مفرق',  # Retail merchant
        ]

        for category_name in default_categories:
            category, created = CustomerCategory.objects.get_or_create(
                company=None,  # Global default
                name=category_name,
                defaults={'is_active': True}
            )
            if created:
                self.stdout.write(f"  Created category: {category_name}")
            else:
                self.stdout.write(f"  Category already exists: {category_name}")

        self.stdout.write(self.style.SUCCESS("✓ Customer categories seeded successfully"))
