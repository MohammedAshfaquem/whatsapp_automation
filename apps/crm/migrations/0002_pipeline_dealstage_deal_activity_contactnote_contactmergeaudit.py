import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('business', '0003_businessprofile_tenant_product_tenant_and_more'),
        ('chatbot', '0010_customer_company_customer_email_and_more'),
        ('crm', '0001_initial'),
        ('services', '0004_alter_service_options_service_tenant_and_more'),
        ('tenants', '0002_migrate_existing_data_to_neoriz'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Pipeline',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="e.g. 'Standard Sales', 'Enterprise', 'Inbound WhatsApp'", max_length=100)),
                ('is_default', models.BooleanField(default=False, help_text='Designates this pipeline as the primary default for new deals')),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='crm_pipelines', to='tenants.tenant')),
            ],
            options={
                'verbose_name': 'Pipeline',
                'verbose_name_plural': 'Pipelines',
                'ordering': ['-is_default', 'name'],
            },
        ),
        migrations.CreateModel(
            name='DealStage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=80)),
                ('order', models.PositiveSmallIntegerField(default=1, help_text='Stage sequence order in pipeline')),
                ('probability', models.PositiveSmallIntegerField(default=10, help_text='Default win probability percentage (0-100)')),
                ('is_won', models.BooleanField(default=False, help_text='Terminal stage indicating successful deal close')),
                ('is_lost', models.BooleanField(default=False, help_text='Terminal stage indicating lost opportunity')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('pipeline', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stages', to='crm.pipeline')),
            ],
            options={
                'verbose_name': 'Deal Stage',
                'verbose_name_plural': 'Deal Stages',
                'ordering': ['order', 'id'],
                'unique_together': {('pipeline', 'name')},
            },
        ),
        migrations.CreateModel(
            name='Deal',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(help_text="Descriptive deal title (e.g. 'Cafe Website + TABLO POS')", max_length=200)),
                ('amount', models.DecimalField(blank=True, decimal_places=2, help_text='Estimated deal value. Never infer from unapproved catalog prices.', max_digits=12, null=True)),
                ('currency', models.CharField(default='INR', help_text='ISO currency code (e.g. INR, USD, AED)', max_length=10)),
                ('expected_close_date', models.DateField(blank=True, help_text='Target deal closing date', null=True)),
                ('probability', models.PositiveSmallIntegerField(blank=True, help_text='Win probability percentage (defaults to stage probability if unset)', null=True)),
                ('requirements_summary', models.TextField(blank=True, default='', help_text='Captured customer requirements or scope notes')),
                ('won_at', models.DateTimeField(blank=True, null=True)),
                ('lost_at', models.DateTimeField(blank=True, null=True)),
                ('lost_reason', models.TextField(blank=True, default='', help_text='Reason recorded when deal is marked lost')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(blank=True, help_text='Associated company/organization', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deals', to='crm.company')),
                ('contact', models.ForeignKey(help_text='Primary person/contact record', on_delete=django.db.models.deletion.CASCADE, related_name='deals', to='chatbot.customer')),
                ('owner', models.ForeignKey(blank=True, help_text='Assigned deal owner from tenant members', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='owned_deals', to=settings.AUTH_USER_MODEL)),
                ('pipeline', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deals', to='crm.pipeline')),
                ('product', models.ForeignKey(blank=True, help_text='Linked verified product if applicable', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deals', to='business.product')),
                ('service', models.ForeignKey(blank=True, help_text='Linked agency service if applicable', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='deals', to='services.service')),
                ('stage', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='deals', to='crm.dealstage')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='deals', to='tenants.tenant')),
            ],
            options={
                'verbose_name': 'Deal',
                'verbose_name_plural': 'Deals',
                'ordering': ['-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='Activity',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('activity_type', models.CharField(choices=[('CALL', 'Phone Call'), ('MEETING', 'Meeting'), ('DEMO', 'Product Demo'), ('FOLLOW_UP', 'Follow Up'), ('TASK', 'General Task')], default='TASK', max_length=20)),
                ('title', models.CharField(help_text='Activity description / subject', max_length=200)),
                ('notes', models.TextField(blank=True, default='', help_text='Detailed notes or agenda')),
                ('due_date', models.DateTimeField(blank=True, help_text='Due date and time (timezone aware)', null=True)),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('COMPLETED', 'Completed'), ('CANCELLED', 'Cancelled')], db_index=True, default='PENDING', max_length=20)),
                ('priority', models.CharField(choices=[('LOW', 'Low'), ('MEDIUM', 'Medium'), ('HIGH', 'High')], default='MEDIUM', max_length=15)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('assigned_to', models.ForeignKey(blank=True, help_text='Assigned tenant member', null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='crm_activities', to=settings.AUTH_USER_MODEL)),
                ('company', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='activities', to='crm.company')),
                ('completed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('contact', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='chatbot.customer')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
                ('deal', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='crm.deal')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='activities', to='tenants.tenant')),
            ],
            options={
                'verbose_name': 'Activity',
                'verbose_name_plural': 'Activities',
                'ordering': ['due_date', '-priority'],
            },
        ),
        migrations.CreateModel(
            name='ContactNote',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('content', models.TextField(help_text='Internal confidential notes regarding this contact')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('author', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('contact', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='internal_notes', to='chatbot.customer')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='contact_notes', to='tenants.tenant')),
            ],
            options={
                'verbose_name': 'Contact Note',
                'verbose_name_plural': 'Contact Notes',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='ContactMergeAudit',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('merged_phone', models.CharField(max_length=30)),
                ('merged_name', models.CharField(blank=True, max_length=150)),
                ('details', models.JSONField(default=dict, help_text='Summary of transferred deals, messages, and activities')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('performed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('primary_contact', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merge_records', to='chatbot.customer')),
                ('tenant', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='merge_audits', to='tenants.tenant')),
            ],
            options={
                'verbose_name': 'Contact Merge Audit',
                'verbose_name_plural': 'Contact Merge Audits',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='DealStageHistory',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notes', models.CharField(blank=True, default='', max_length=255)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('changed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('deal', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='stage_history', to='crm.deal')),
                ('from_stage', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='crm.dealstage')),
                ('to_stage', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='+', to='crm.dealstage')),
            ],
            options={
                'verbose_name': 'Deal Stage History',
                'verbose_name_plural': 'Deal Stage History',
                'ordering': ['-created_at'],
            },
        ),
    ]
