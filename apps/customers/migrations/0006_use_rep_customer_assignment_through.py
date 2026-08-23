# Migration to update Customer.assigned_reps to use RepCustomerAssignment through table

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0005_seed_default_categories'),
        ('reps', '0003_migrate_existing_assignments'),
    ]

    operations = [
        # Remove the old ManyToMany field
        migrations.RemoveField(
            model_name='customer',
            name='assigned_reps',
        ),
        
        # Add the new ManyToMany field with through table
        migrations.AddField(
            model_name='customer',
            name='assigned_reps',
            field=models.ManyToManyField(
                blank=True,
                help_text='Reps from any company can be assigned to this customer',
                related_name='assigned_customers',
                through='reps.RepCustomerAssignment',
                to='reps.rep'
            ),
        ),
    ]
