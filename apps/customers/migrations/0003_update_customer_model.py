# Generated migration for customer model updates:
# - Make password nullable (only set by customer on signup, not by company)
# - Change assigned_rep from ForeignKey to ManyToManyField (assigned_reps)
# - Add category field (free text)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0002_add_referral_code_tracking'),
        ('reps', '0001_initial'),
    ]

    operations = [
        # 1. Make password nullable
        migrations.AlterField(
            model_name='customer',
            name='password',
            field=models.CharField(
                blank=True,
                help_text='Only set by customer during signup, not by company',
                max_length=128,
                null=True,
            ),
        ),
        
        # 2. Remove old assigned_rep ForeignKey and its index
        migrations.RemoveIndex(
            model_name='customer',
            name='customer_assigned_rep_idx',
        ),
        migrations.RemoveField(
            model_name='customer',
            name='assigned_rep',
        ),
        
        # 3. Add new assigned_reps ManyToManyField
        migrations.AddField(
            model_name='customer',
            name='assigned_reps',
            field=models.ManyToManyField(
                blank=True,
                help_text='Reps from any company can be assigned to this customer',
                related_name='assigned_customers',
                to='reps.rep',
            ),
        ),
        
        # 4. Add category field
        migrations.AddField(
            model_name='customer',
            name='category',
            field=models.CharField(
                blank=True,
                help_text='Customer category (free text, choices defined in serializer)',
                max_length=100,
                null=True,
            ),
        ),
        
        # 5. Add index for category
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['category'], name='customer_category_idx'),
        ),
    ]
