from django.contrib import admin
from .models import BusinessProfile

@admin.register(BusinessProfile)
class BusinessProfileAdmin(admin.ModelAdmin):
    list_display = ('shop_name', 'contact_phone', 'is_active', 'updated_at')
    list_filter = ('is_active', 'created_at')
    search_fields = ('shop_name', 'contact_phone', 'address', 'service_areas')
    fieldsets = (
        ('Basic Information', {
            'fields': ('shop_name', 'contact_phone', 'address', 'google_maps_url', 'is_active')
        }),
        ('Operations & Working Hours', {
            'fields': ('working_hours', 'holiday_information', 'service_areas')
        }),
        ('Technical Capability', {
            'fields': ('supported_ac_types', 'supported_ac_brands')
        }),
        ('Policies & Commercials', {
            'fields': ('warranty_policies', 'accepted_payment_methods', 'general_service_policies')
        }),
    )
