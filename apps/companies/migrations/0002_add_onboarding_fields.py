# Generated migration for onboarding fields

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("companies", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="company",
            name="logo",
            field=models.FileField(blank=True, null=True, upload_to="companies/logos/"),
        ),
        migrations.AddField(
            model_name="company",
            name="cover",
            field=models.FileField(blank=True, null=True, upload_to="companies/covers/"),
        ),
        migrations.AddField(
            model_name="company",
            name="governorate",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="region",
            field=models.CharField(blank=True, max_length=100, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="description",
            field=models.TextField(blank=True, max_length=500, null=True),
        ),
        migrations.AddField(
            model_name="company",
            name="business_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("food_products", "مواد غذائية"),
                    ("electronics", "إلكترونيات"),
                    ("cosmetics", "مستحضرات تجميل"),
                    ("medical_supplies", "أدوية ومستلزمات طبية"),
                    ("home_tools", "أدوات منزلية"),
                    ("clothing", "ألبسة"),
                ],
                max_length=50,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="company",
            name="onboarding_completed",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="company",
            name="onboarding_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="company",
            name="currency",
            field=models.CharField(default="SYP", max_length=3),
        ),
    ]
