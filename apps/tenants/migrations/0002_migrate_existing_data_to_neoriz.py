from django.db import migrations


def assign_existing_records_to_neoriz(apps, schema_editor):
    Tenant = apps.get_model('tenants', 'Tenant')
    TenantMembership = apps.get_model('tenants', 'TenantMembership')
    User = apps.get_model('auth', 'User')

    # 1. Get or create Neoriz Solutions tenant
    neoriz, _ = Tenant.objects.get_or_create(
        slug='neoriz-solutions',
        defaults={
            'name': 'Neoriz Solutions',
            'plan': 'ENTERPRISE',
            'is_active': True,
            'max_services': 50,
            'max_staff': 20,
        }
    )

    # 2. Assign existing administrator user wappadmin as OWNER
    wappadmin = User.objects.filter(username='wappadmin').first()
    if wappadmin:
        TenantMembership.objects.get_or_create(
            tenant=neoriz,
            user=wappadmin,
            defaults={'role': 'OWNER', 'is_active': True}
        )

    # 3. Assign all existing business data to Neoriz Solutions
    BusinessProfile = apps.get_model('business', 'BusinessProfile')
    Product = apps.get_model('business', 'Product')
    Service = apps.get_model('services', 'Service')
    Customer = apps.get_model('chatbot', 'Customer')
    Conversation = apps.get_model('chatbot', 'Conversation')
    Booking = apps.get_model('bookings', 'Booking')
    BookingSession = apps.get_model('bookings', 'BookingSession')
    FAQ = apps.get_model('knowledge_base', 'FAQ')
    KnowledgeDocument = apps.get_model('knowledge_base', 'KnowledgeDocument')
    KnowledgeSyncStatus = apps.get_model('knowledge_base', 'KnowledgeSyncStatus')
    WhatsAppConfig = apps.get_model('whatsapp', 'WhatsAppConfig')
    WhatsAppWebhookLog = apps.get_model('whatsapp', 'WhatsAppWebhookLog')
    WhatsAppDelivery = apps.get_model('whatsapp', 'WhatsAppDelivery')

    # Update only unassigned records
    BusinessProfile.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    Product.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    Service.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    Customer.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    Conversation.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    Booking.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    BookingSession.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    FAQ.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    KnowledgeDocument.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    KnowledgeSyncStatus.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    WhatsAppConfig.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    WhatsAppWebhookLog.objects.filter(tenant__isnull=True).update(tenant=neoriz)
    WhatsAppDelivery.objects.filter(tenant__isnull=True).update(tenant=neoriz)


def reverse_assignment(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0001_initial'),
        ('business', '0003_businessprofile_tenant_product_tenant_and_more'),
        ('services', '0004_alter_service_options_service_tenant_and_more'),
        ('chatbot', '0009_conversation_tenant_customer_tenant_and_more'),
        ('bookings', '0006_booking_tenant_bookingsession_tenant'),
        ('knowledge_base', '0003_remove_knowledgesyncstatus_knowledge_b_source__31fad5_idx_and_more'),
        ('whatsapp', '0003_whatsappconfig_tenant_whatsappdelivery_tenant_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_existing_records_to_neoriz, reverse_assignment),
    ]
