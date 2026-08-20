# Generated migration for adding referral_code_used field to Customer model

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('customers', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='customer',
            name='referral_code_used',
            field=models.CharField(
                blank=True,
                help_text='Original referral code used during signup (immutable for tracking)',
                max_length=32,
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name='customer',
            index=models.Index(fields=['referral_code_used'], name='customer_referral_code_idx'),
        ),
    ]
