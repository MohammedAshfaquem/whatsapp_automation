from django.contrib import admin
from apps.tenants.admin import TenantScopedAdminMixin
from .models import WhatsAppConfig, WhatsAppWebhookLog, WhatsAppDelivery


@admin.register(WhatsAppDelivery)
class WhatsAppDeliveryAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'recipient_phone', 'status', 'attempts', 'updated_at')
    list_filter = ('status',)
    search_fields = ('recipient_phone', 'provider_message_id', 'dedup_key')
    readonly_fields = ('dedup_key', 'recipient_phone', 'payload', 'status', 'provider_message_id', 'attempts', 'last_error', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False

@admin.register(WhatsAppConfig)
class WhatsAppConfigAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'is_enabled', 'phone_number_id', 'business_account_id', 'updated_at')
    list_editable = ('is_enabled',)
    fieldsets = (
        ('Master Switch', {
            'fields': ('is_enabled',),
            'description': 'Toggle this switch to activate live WhatsApp messaging. When disabled, the bot operates in simulation mode.'
        }),
        ('Meta Credentials & IDs', {
            'fields': ('phone_number_id', 'business_account_id', 'verify_token', 'access_token', 'app_secret'),
            'description': 'Credentials obtained from your Meta App Dashboard (developers.facebook.com).'
        }),
    )

    def has_add_permission(self, request):
        tenant = getattr(request, 'tenant', None)
        if tenant and self.model.objects.filter(tenant=tenant).exists():
            return False
        return super().has_add_permission(request)

@admin.register(WhatsAppWebhookLog)
class WhatsAppWebhookLogAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'event_type', 'sender_phone', 'whatsapp_message_id', 'is_processed', 'created_at')
    list_filter = ('is_processed', 'event_type', 'created_at')
    search_fields = ('sender_phone', 'whatsapp_message_id', 'error_message')
    readonly_fields = ('event_type', 'whatsapp_message_id', 'sender_phone', 'raw_payload', 'is_processed', 'error_message', 'created_at')

    def has_add_permission(self, request):
        return False
