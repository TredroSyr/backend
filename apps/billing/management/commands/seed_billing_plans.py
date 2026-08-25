from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.billing.models import Plan, PlanFeature, PlanLimit


class Command(BaseCommand):
    help = "Seed default billing plans with limits and features"

    def handle(self, *args, **options) -> None:
        self.stdout.write("Seeding default billing plans...")

        # Check if Free plan already exists
        free_plan, created = Plan.objects.get_or_create(
            name="Free",
            defaults={
                "price": 0.00,
                "billing_interval": "monthly",
                "is_active": True,
            }
        )

        if created:
            self.stdout.write("  Created plan: Free")
            
            # Add resource limits for Free plan
            limits = [
                {"resource_key": "reps", "max_value": 5},
                {"resource_key": "products", "max_value": 50},
                {"resource_key": "subusers", "max_value": 3},
                {"resource_key": "warehouses", "max_value": 2},
                {"resource_key": "customers", "max_value": None},  # Unlimited
            ]

            for limit_data in limits:
                PlanLimit.objects.create(
                    plan=free_plan,
                    resource_key=limit_data["resource_key"],
                    max_value=limit_data["max_value"],
                )
                limit_display = limit_data["max_value"] if limit_data["max_value"] is not None else "Unlimited"
                self.stdout.write(f"    Added limit: {limit_data['resource_key']} = {limit_display}")

            # Add feature flags for Free plan
            features = [
                {"feature_key": "excel_import", "enabled": False},
                {"feature_key": "advanced_reports", "enabled": False},
                {"feature_key": "multi_warehouse", "enabled": False},
                {"feature_key": "api_access", "enabled": False},
                {"feature_key": "custom_branding", "enabled": False},
            ]

            for feature_data in features:
                PlanFeature.objects.create(
                    plan=free_plan,
                    feature_key=feature_data["feature_key"],
                    enabled=feature_data["enabled"],
                )
                status = "enabled" if feature_data["enabled"] else "disabled"
                self.stdout.write(f"    Added feature: {feature_data['feature_key']} ({status})")

        else:
            self.stdout.write("  Plan already exists: Free")
            self.stdout.write(f"    Limits: {free_plan.limits.count()}")
            self.stdout.write(f"    Features: {free_plan.features.count()}")

        self.stdout.write(self.style.SUCCESS("✓ Billing plans seeded successfully"))
