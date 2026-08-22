# Seed default customer categories

from django.db import migrations


def seed_default_categories(apps, schema_editor):
    """Create global default customer categories."""
    CustomerCategory = apps.get_model('customers', 'CustomerCategory')
    
    default_categories = [
        'تاجر جملة',  # Wholesale merchant
        'تاجر مفرق',  # Retail merchant
    ]
    
    for category_name in default_categories:
        CustomerCategory.objects.get_or_create(
            company=None,  # Global default
            name=category_name,
            defaults={'is_active': True}
        )


def reverse_seed(apps, schema_editor):
    """Remove seeded categories on migration rollback."""
    CustomerCategory = apps.get_model('customers', 'CustomerCategory')
    CustomerCategory.objects.filter(
        company=None,
        name__in=['تاجر جملة', 'تاجر مفرق']
    ).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0004_add_customer_category_model'),
    ]

    operations = [
        migrations.RunPython(seed_default_categories, reverse_seed),
    ]
