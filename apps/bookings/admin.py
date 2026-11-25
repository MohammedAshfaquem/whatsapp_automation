from django.contrib import admin
from apps.tenants.admin import TenantScopedAdminMixin
from .models import Booking, BookingStatus
from .notifications import change_booking_status

@admin.register(Booking)
class BookingAdmin(TenantScopedAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'request_type',
        'customer',
        'product',
        'service',
        'organization',
        'preferred_date',
        'preferred_time_slot',
        'status',
        'created_at'
    )
    list_filter = ('request_type', 'status', 'preferred_date', 'created_at', 'product', 'service')
    search_fields = (
        'customer__phone_number',
        'customer__name',
        'recipient_name',
        'organization',
        'contact_email',
        'service_address',
        'problem_description',
        'requirements_summary',
        'owner_notes'
    )
    readonly_fields = ('status',)
    fieldsets = (
        ('Request Classification', {
            'fields': ('request_type', 'customer', 'recipient_name', 'conversation', 'product', 'service')
        }),
        ('Customer & Organization', {
            'fields': ('organization', 'contact_email', 'language', 'account_reference')
        }),
        ('Requirements & Details', {
            'fields': ('requirements_summary', 'staff_summary', 'problem_description', 'ac_type', 'ac_brand')
        }),
        ('Schedule & Contact Location', {
            'fields': ('service_address', 'preferred_date', 'preferred_time_slot')
        }),
        ('Status & Staff Notes', {
            'fields': ('status', 'owner_notes')
        }),
    )
    actions = ['mark_confirmed', 'mark_rejected', 'mark_completed']

    @admin.action(description="Confirm selected bookings")
    def mark_confirmed(self, request, queryset):
        self.change_status(request, queryset, BookingStatus.CONFIRMED)

    @admin.action(description="Reject selected bookings")
    def mark_rejected(self, request, queryset):
        self.change_status(request, queryset, BookingStatus.REJECTED)

    @admin.action(description="Mark selected bookings as completed")
    def mark_completed(self, request, queryset):
        self.change_status(request, queryset, BookingStatus.COMPLETED)

    def change_status(self, request, queryset, target):
        for booking in queryset:
            try:
                change_booking_status(booking, target)
            except ValueError as error:
                self.message_user(request, f'Booking #{booking.pk}: {error}', level='warning')

from .models import BookingSession

@admin.register(BookingSession)
class BookingSessionAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'step', 'updated_at')
    list_filter = ('step', 'created_at')
    search_fields = ('conversation__customer__phone_number', 'conversation__customer__name')
