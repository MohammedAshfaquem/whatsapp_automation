from django.apps import AppConfig


class CrmConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.crm'
    verbose_name = 'Customer Relationship Management'

    def ready(self):
        try:
            import apps.crm.signals  # noqa
        except ImportError:
            pass
