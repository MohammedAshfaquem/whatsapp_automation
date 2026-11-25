from django.db import migrations

def preserve_access(apps,schema_editor):
    Plan=apps.get_model('tenants','PlanTier')
    for plan in Plan.objects.all():
        modules=plan.enabled_modules or []
        if 'scheduling_quotations' in modules and 'marketing' not in modules:
            plan.enabled_modules=modules+['marketing'];plan.save(update_fields=['enabled_modules'])

class Migration(migrations.Migration):
    dependencies=[('tenants','0010_platformserviceconfig_recoverythrottle_and_more')]
    operations=[migrations.RunPython(preserve_access,migrations.RunPython.noop)]
