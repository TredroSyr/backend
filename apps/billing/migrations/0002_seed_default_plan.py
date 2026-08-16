# Generated migration to seed default Free plan

from __future__ import annotations

from django.db import migrations


def seed_default_plan(apps, schema_editor):
    """Seed the default Free plan with limits and features."""
    Plan = apps.get_model("billing", "Plan")
    PlanLimit = apps.get_model("billing", "PlanLimit")
    PlanFeature = apps.get_model("billing", "PlanFeature")
    
    # Create Free plan
    free_plan = Plan.objects.create(
        name="Free",
        price=0.00,
        billing_interval="monthly",
        is_active=True,
    )
    
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


def reverse_seed(apps, schema_editor):
    """Remove seeded data."""
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(name="Free").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_plan, reverse_seed),
    ]
