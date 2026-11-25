import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('tenants', '0002_migrate_existing_data_to_neoriz'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Company',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text='Company or organization legal/brand name', max_length=180)),
                ('domain', models.CharField(blank=True, default='', help_text='Company website or domain (e.g. acme.com)', max_length=150)),
                ('phone', models.CharField(blank=True, default='', help_text='Primary company phone number', max_length=30)),
                ('address', models.TextField(blank=True, default='', help_text='Company physical or registered address')),
                ('industry', models.CharField(blank=True, default='', help_text='Industry sector (e.g. Retail, Healthcare, IT)', max_length=100)),
                ('notes', models.TextField(blank=True, default='', help_text='Internal account notes')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('owner', models.ForeignKey(blank=True, help_text='Tenant staff member owning this company relationship', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_companies', to=settings.AUTH_USER_MODEL)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='companies', to='tenants.tenant')),
            ],
            options={
                'verbose_name': 'Company',
                'verbose_name_plural': 'Companies',
                'ordering': ['name'],
                'unique_together': {('tenant', 'name')},
            },
        ),
    ]
