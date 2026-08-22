# Generated migration for CustomerCategory model and CustomerCategoryAssignment

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('companies', '0002_add_onboarding_fields'),
        ('customers', '0003_update_customer_model'),
    ]

    operations = [
        # Create CustomerCategory model
        migrations.CreateModel(
            name='CustomerCategory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100)),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(blank=True, help_text='NULL = global default category, otherwise company-specific', null=True, on_delete=django.db.models.deletion.CASCADE, related_name='customer_categories', to='companies.company')),
            ],
            options={
                'verbose_name_plural': 'Customer Categories',
                'db_table': 'customer_category',
            },
        ),
        migrations.AddConstraint(
            model_name='customercategory',
            constraint=models.UniqueConstraint(fields=('company', 'name'), name='customer_category_company_name_uniq'),
        ),
        migrations.AddIndex(
            model_name='customercategory',
            index=models.Index(fields=['company'], name='customer_category_company_idx'),
        ),
        migrations.AddIndex(
            model_name='customercategory',
            index=models.Index(fields=['is_active'], name='customer_category_active_idx'),
        ),
        # Create CustomerCategoryAssignment through table
        migrations.CreateModel(
            name='CustomerCategoryAssignment',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assigned_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('customer', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='category_assignments', to='customers.customer')),
                ('company', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='customer_category_assignments', to='companies.company')),
                ('category', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='assignments', to='customers.customercategory')),
            ],
            options={
                'db_table': 'customer_category_assignment',
            },
        ),
        migrations.AddConstraint(
            model_name='customercategoryassignment',
            constraint=models.UniqueConstraint(fields=('customer', 'company'), name='customer_category_assignment_uniq'),
        ),
        migrations.AddIndex(
            model_name='customercategoryassignment',
            index=models.Index(fields=['customer', 'company'], name='cust_cat_assign_cust_comp_idx'),
        ),
        migrations.AddIndex(
            model_name='customercategoryassignment',
            index=models.Index(fields=['company'], name='cust_cat_assign_company_idx'),
        ),
        migrations.AddIndex(
            model_name='customercategoryassignment',
            index=models.Index(fields=['category'], name='cust_cat_assign_category_idx'),
        ),
    ]
