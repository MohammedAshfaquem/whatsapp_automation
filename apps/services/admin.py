from django.contrib import admin
from .models import Service

@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ('name', 'category', 'price_type', 'formatted_price', 'estimated_duration', 'is_active', 'updated_at')
    list_filter = ('category', 'price_type', 'is_active', 'created_at')
    search_fields = ('name', 'description', 'category')
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ('is_active',)
    fieldsets = (
        ('Service Details', {
            'fields': ('name', 'slug', 'category', 'description', 'estimated_duration', 'is_active')
        }),
        ('Pricing Configuration', {
            'fields': ('price_type', 'price_amount', 'max_price', 'currency'),
            'description': 'Configure base price, price ranges, or mark as inspection required.'
        }),
    )
