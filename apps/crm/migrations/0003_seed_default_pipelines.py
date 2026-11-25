from django.db import migrations


def seed_default_pipelines(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    Pipeline = apps.get_model('crm', 'Pipeline')
    DealStage = apps.get_model('crm', 'DealStage')

    initial_stages = [
        ("New", 1, 10, False, False),
        ("Qualified", 2, 25, False, False),
        ("Demo / Consultation", 3, 50, False, False),
        ("Proposal", 4, 70, False, False),
        ("Negotiation", 5, 85, False, False),
        ("Closed Won", 6, 100, True, False),
        ("Closed Lost", 7, 0, False, True),
    ]

    for tenant in Tenant.objects.all():
        if not Pipeline.objects.filter(tenant=tenant).exists():
            pipeline = Pipeline.objects.create(
                tenant=tenant,
                name="Default Sales Pipeline",
                is_default=True,
                is_active=True
            )
            for sname, sorder, sprob, swon, slost in initial_stages:
                DealStage.objects.create(
                    pipeline=pipeline,
                    name=sname,
                    order=sorder,
                    probability=sprob,
                    is_won=swon,
                    is_lost=slost
                )


def remove_default_pipelines(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0002_pipeline_dealstage_deal_activity_contactnote_contactmergeaudit'),
        ('tenants', '0002_migrate_existing_data_to_neoriz'),
    ]

    operations = [
        migrations.RunPython(seed_default_pipelines, reverse_code=remove_default_pipelines),
    ]
