from django.contrib import admin
from .models import Customer, Conversation, Message

class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    readonly_fields = ('direction', 'sender_type', 'message_text', 'external_message_id', 'processing_status', 'created_at')
    can_delete = False

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('phone_number', 'name', 'created_at', 'updated_at')
    search_fields = ('phone_number', 'name')
    ordering = ('-updated_at',)

@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('id', 'customer', 'channel', 'status', 'assigned_staff', 'picked_up_at', 'last_message_at')
    list_filter = ('status', 'channel', 'created_at')
    search_fields = ('customer__phone_number', 'customer__name')
    list_editable = ('status',)
    inlines = [MessageInline]
    actions = ['activate_bot', 'handover_to_human', 'close_conversation']

    @admin.action(description="Resume AI bot (BOT_ACTIVE)")
    def activate_bot(self, request, queryset):
        queryset.update(status='BOT_ACTIVE', assigned_staff=None, picked_up_at=None)

    @admin.action(description="Handover to Human (HUMAN_HANDOVER)")
    def handover_to_human(self, request, queryset):
        queryset.update(status='HUMAN_HANDOVER')

    @admin.action(description="Close selected conversations")
    def close_conversation(self, request, queryset):
        queryset.update(status='CLOSED', assigned_staff=None, picked_up_at=None)

@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'conversation', 'direction', 'sender_type', 'short_text', 'processing_status', 'created_at')
    list_filter = ('direction', 'sender_type', 'processing_status', 'created_at')
    search_fields = ('message_text', 'external_message_id', 'conversation__customer__phone_number')

    def short_text(self, obj):
        return obj.message_text[:60]
    short_text.short_description = "Message"
