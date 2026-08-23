# Migration to add work_days and RepCustomerAssignment model

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('reps', '0001_initial'),
        ('customers', '0005_seed_default_categories'),
    ]

    operations = [
        # 1. Add work_days field to Rep
        migrations.AddField(
            model_name='rep',
            name='work_days',
            field=models.JSONField(
                default=list,
                help_text="Default work days for this rep (e.g., ['sunday', 'monday', 'tuesday'])"
            ),
        ),
        
        # 2. Create RepCustomerAssignment through table
        migrations.CreateModel(
            name='RepCustomerAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('work_days', models.JSONField(
                    default=list,
                    help_text="Work days for this customer-rep assignment (e.g., ['sunday', 'monday'])"
                )),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='rep_assignments',
                    to='customers.customer'
                )),
                ('rep', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='customer_assignments',
                    to='reps.rep'
                )),
            ],
            options={
                'db_table': 'rep_customer_assignment',
                'indexes': [
                    models.Index(fields=['rep'], name='rep_cust_assign_rep_idx'),
                    models.Index(fields=['customer'], name='rep_cust_assign_customer_idx'),
                    models.Index(fields=['rep', 'customer'], name='rep_cust_assign_both_idx'),
                ],
                'constraints': [
                    models.UniqueConstraint(
                        fields=('rep', 'customer'),
                        name='rep_customer_assignment_uniq'
                    ),
                ],
            },
        ),
    ]
