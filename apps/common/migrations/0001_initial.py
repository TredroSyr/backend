# Initial migration for common app - creates UnitOfMeasure and Currency tables

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='UnitOfMeasure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=32, unique=True)),
                ('name', models.CharField(max_length=64)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'unit_of_measure',
            },
        ),
        migrations.CreateModel(
            name='Currency',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=3, unique=True, help_text='ISO 4217 code, e.g. USD, EUR')),
                ('name', models.CharField(max_length=64)),
                ('symbol', models.CharField(blank=True, default='', max_length=8)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'db_table': 'currency',
                'verbose_name_plural': 'currencies',
            },
        ),
    ]
