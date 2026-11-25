from django.db import models
from django.utils import timezone
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError


class ContactLifecycleStatus(models.TextChoices):
    SUBSCRIBER = 'SUBSCRIBER', 'Subscriber'
    LEAD = 'LEAD', 'Lead'
    MQL = 'MQL', 'Marketing Qualified Lead'
    SQL = 'SQL', 'Sales Qualified Lead'
    OPPORTUNITY = 'OPPORTUNITY', 'Opportunity'
    CUSTOMER = 'CUSTOMER', 'Customer'
    EVANGELIST = 'EVANGELIST', 'Evangelist'
    OTHER = 'OTHER', 'Other'


class ContactSource(models.TextChoices):
    WHATSAPP_INBOUND = 'WHATSAPP_INBOUND', 'WhatsApp Inbound'
    WEBSITE = 'WEBSITE', 'Website Form / Portal'
    MANUAL = 'MANUAL', 'Manual Entry'
    REFERRAL = 'REFERRAL', 'Referral'
    IMPORT = 'IMPORT', 'CSV Import'
    OTHER = 'OTHER', 'Other'


class Customer(models.Model):
    """
    Customer identified by their unique normalized phone number per tenant,
    optionally linked to a User account for customer portal login and enriched with CRM fields.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='customers', null=True, blank=True)
    user = models.OneToOneField(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_profile')
    name = models.CharField(max_length=150, blank=True, help_text="Customer name if provided")
    email = models.EmailField(max_length=254, blank=True, default='', help_text="Contact email address")
    company = models.ForeignKey('crm.Company', on_delete=models.SET_NULL, null=True, blank=True, related_name='contacts')
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='owned_contacts')
    lifecycle_status = models.CharField(max_length=30, choices=ContactLifecycleStatus.choices, default=ContactLifecycleStatus.LEAD)
    source = models.CharField(max_length=30, choices=ContactSource.choices, default=ContactSource.WHATSAPP_INBOUND)
    tags = models.JSONField(default=list, blank=True, help_text="List of string tags scoped to tenant")
    notes = models.TextField(blank=True, default='', help_text="General internal contact notes")
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    preferred_language = models.CharField(max_length=12, default='en')
    custom_fields = models.JSONField(default=dict, blank=True)
    last_whatsapp_event_at = models.DateTimeField(null=True, blank=True, editable=False)
    processing_token = models.CharField(max_length=32, blank=True, editable=False)
    processing_until = models.DateTimeField(null=True, blank=True, editable=False)
    phone_number = models.CharField(max_length=30, db_index=True, help_text="Normalized phone number (e.g. +919876543210)")
    assigned_services = models.ManyToManyField('services.Service', blank=True, related_name='tagged_customers')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Customer"
        verbose_name_plural = "Customers"
        unique_together = ('tenant', 'phone_number')

    def __str__(self):
        return f"{self.name or 'Unknown'} ({self.phone_number})"

    def clean(self):
        super().clean()
        if self.company and self.tenant and self.company.tenant_id != self.tenant_id:
            raise ValidationError("Company must belong to the same tenant as the contact.")
        if self.owner and self.tenant and not self.owner.is_superuser:
            if not self.tenant.memberships.filter(user=self.owner, is_active=True).exists():
                raise ValidationError("Contact owner must be an active member of this tenant.")


class ChannelChoice(models.TextChoices):
    SIMULATED = 'SIMULATED', 'Simulated Chat (API/Postman)'
    WHATSAPP = 'WHATSAPP', 'WhatsApp Cloud API'

class ConversationStatus(models.TextChoices):
    BOT_ACTIVE = 'BOT_ACTIVE', 'Bot Active'
    HUMAN_HANDOVER = 'HUMAN_HANDOVER', 'Human Handover'
    CLOSED = 'CLOSED', 'Closed'

class Conversation(models.Model):
    """
    Tracks state, channel, and human-handover mode of customer interaction.
    Can be scoped to a specific service.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='conversations', null=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='conversations')
    service = models.ForeignKey('services.Service', on_delete=models.SET_NULL, null=True, blank=True, related_name='conversations')
    channel = models.CharField(max_length=20, choices=ChannelChoice.choices, default=ChannelChoice.SIMULATED)
    status = models.CharField(max_length=25, choices=ConversationStatus.choices, default=ConversationStatus.BOT_ACTIVE)
    last_message_at = models.DateTimeField(default=timezone.now)
    handoff_summary = models.TextField(blank=True)
    assigned_staff = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,
                                      related_name='support_conversations', limit_choices_to={'is_staff': True})
    picked_up_at = models.DateTimeField(null=True, blank=True)
    unresolved_count = models.PositiveSmallIntegerField(default=0)
    memory_summary = models.TextField(blank=True)
    memory_through_message_id = models.PositiveBigIntegerField(default=0, editable=False)
    unread_count = models.PositiveIntegerField(default=0)
    first_human_response_at = models.DateTimeField(null=True, blank=True)
    last_inbound_at = models.DateTimeField(null=True, blank=True)
    followup_alert_sent_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_message_at']
        verbose_name = "Conversation"
        verbose_name_plural = "Conversations"

    def __str__(self):
        return f"Conv #{self.id} - {self.customer.phone_number} [{self.get_status_display()}]"

class MessageDirection(models.TextChoices):
    INBOUND = 'INBOUND', 'Inbound'
    OUTBOUND = 'OUTBOUND', 'Outbound'


class AIConnectionStatus(models.Model):
    """Last provider check for a configuration; never store keys or raw errors."""
    provider = models.CharField(max_length=30, primary_key=True, default='gemini')
    configuration_hash = models.CharField(max_length=64)
    status = models.CharField(max_length=30)
    checked_at = models.DateTimeField(default=timezone.now)
    latency_ms = models.PositiveIntegerField(default=0)

class SenderType(models.TextChoices):
    CUSTOMER = 'CUSTOMER', 'Customer'
    BOT = 'BOT', 'Bot'
    HUMAN = 'HUMAN', 'Human Shop Owner/Agent'

class ProcessingStatus(models.TextChoices):
    RECEIVED = 'RECEIVED', 'Received'
    PROCESSING = 'PROCESSING', 'Processing'
    PROCESSED = 'PROCESSED', 'Processed'
    FAILED = 'FAILED', 'Failed'

class Message(models.Model):
    """
    Records every inbound and outbound message with deduplication support.
    """
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name='messages')
    direction = models.CharField(max_length=15, choices=MessageDirection.choices)
    sender_type = models.CharField(max_length=15, choices=SenderType.choices)
    message_text = models.TextField()
    response_data = models.JSONField(default=dict, blank=True)
    external_message_id = models.CharField(
        max_length=150,
        null=True,
        blank=True,
        unique=True,
        db_index=True,
        help_text="Meta WhatsApp message ID for idempotent deduplication"
    )
    processing_status = models.CharField(
        max_length=20,
        choices=ProcessingStatus.choices,
        default=ProcessingStatus.RECEIVED
    )
    media_type = models.CharField(max_length=20, blank=True, default='')
    media_key = models.CharField(max_length=300, blank=True, default='')
    media_name = models.CharField(max_length=200, blank=True, default='')
    media_mime = models.CharField(max_length=100, blank=True, default='')
    media_size = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'pk']
        verbose_name = "Message"
        verbose_name_plural = "Messages"

    def __str__(self):
        return f"[{self.direction}] {self.sender_type}: {self.message_text[:40]}"
