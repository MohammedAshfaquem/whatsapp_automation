from django.contrib import admin
from .models import Booking, BookingStatus
from .notifications import change_booking_status

@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'customer',
        'recipient_name',
        'service',
        'ac_type',
        'preferred_date',
        'preferred_time_slot',
        'status',
        'created_at'
    )
    list_filter = ('status', 'preferred_date', 'created_at', 'service')
    search_fields = (
        'customer__phone_number',
        'customer__name',
        'recipient_name',
        'service_address',
        'problem_description',
        'owner_notes'
    )
    readonly_fields = ('status',)
    fieldsets = (
        ('Customer & Service Details', {
            'fields': ('customer', 'recipient_name', 'conversation', 'service', 'ac_type', 'ac_brand', 'problem_description')
        }),
        ('Schedule & Location', {
            'fields': ('service_address', 'preferred_date', 'preferred_time_slot')
        }),
        ('Status & Owner Notes', {
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
