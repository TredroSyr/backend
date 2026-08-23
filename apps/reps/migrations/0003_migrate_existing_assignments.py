# Data migration to migrate existing customer-rep assignments to new through table

from django.db import migrations


def migrate_assignments(apps, schema_editor):
    """Migrate existing ManyToMany relationships to RepCustomerAssignment."""
    Customer = apps.get_model('customers', 'Customer')
    RepCustomerAssignment = apps.get_model('reps', 'RepCustomerAssignment')
    
    # Get the through table for the old ManyToMany
    through_model = Customer.assigned_reps.through
    
    # Migrate all existing assignments
    for assignment in through_model.objects.all():
        RepCustomerAssignment.objects.get_or_create(
            rep_id=assignment.rep_id,
            customer_id=assignment.customer_id,
            defaults={'work_days': []}  # Empty list, will inherit from rep's default
        )


def reverse_migration(apps, schema_editor):
    """Clean up RepCustomerAssignment if rolling back."""
    RepCustomerAssignment = apps.get_model('reps', 'RepCustomerAssignment')
    RepCustomerAssignment.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('reps', '0002_add_work_days_and_assignment_model'),
        ('customers', '0005_seed_default_categories'),
    ]

    operations = [
        migrations.RunPython(migrate_assignments, reverse_migration),
    ]
