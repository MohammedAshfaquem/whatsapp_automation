from django.db import models
from apps.chatbot.models import Customer, Conversation
from apps.services.models import Service

class BookingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Confirmation'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    REJECTED = 'REJECTED', 'Rejected'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'


class RequestType(models.TextChoices):
    CONSULTATION = 'CONSULTATION', 'IT Service Consultation'
    PRODUCT_DEMO = 'PRODUCT_DEMO', 'Product Demo'
    CUSTOMER_SUPPORT = 'CUSTOMER_SUPPORT', 'Existing Customer Support'
    SERVICE_REQUEST = 'SERVICE_REQUEST', 'Service Request'


class Booking(models.Model):
    """
    Customer consultation, product demo, or support request submitted via chat
    and reviewed/managed by staff.
    Initially in PENDING state; bot never claims confirmation until confirmed by staff.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='bookings', null=True, blank=True)
    request_type = models.CharField(
        max_length=30,
        choices=RequestType.choices,
        default=RequestType.CONSULTATION,
        db_index=True,
        help_text="Type of customer request"
    )
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='bookings')
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    product = models.ForeignKey(
        'business.Product',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='bookings',
        help_text="Product of interest for demo or existing-customer support"
    )
    recipient_name = models.CharField(max_length=150, blank=True, help_text='Person receiving the service when booked for someone else')

    # Explicit IT agency & product consultation fields
    organization = models.CharField(max_length=200, blank=True, default='', help_text="Company or organization name")
    contact_email = models.CharField(max_length=255, blank=True, default='', help_text="Contact email for consultation/demo")
    requirements_summary = models.TextField(blank=True, default='', help_text="Structured summary of requirements")
    staff_summary = models.TextField(blank=True, default='', help_text="Concise summary prepared for staff review")
    language = models.CharField(max_length=12, default='en', blank=True, help_text="Language preferred by customer")
    account_reference = models.CharField(max_length=100, blank=True, default='', help_text="Existing account/installation reference for support")

    # Retained legacy AC fields for backward compatibility with existing tests and schema
    ac_type = models.CharField(max_length=100, blank=True, help_text="e.g. Split AC, Window AC, or project category")
    ac_brand = models.CharField(max_length=100, blank=True, help_text="e.g. Daikin, Voltas, LG")
    problem_description = models.TextField(blank=True, help_text="Description of issue or project requirements")
    service_address = models.TextField(blank=True, default='', help_text="Customer address, organization, or contact email")
    
    preferred_date = models.DateField(null=True, blank=True, help_text="Customer requested appointment date")
    preferred_time_slot = models.CharField(max_length=100, blank=True, help_text="e.g. Morning (10 AM - 1 PM) or Evening (3 PM - 6 PM)")
    
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True
    )
    owner_notes = models.TextField(blank=True, help_text="Internal notes added by staff")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Service & Demo Request"
        verbose_name_plural = "Service & Demo Requests"

    def __str__(self):
        target = self.product.name if self.product else (self.service.name if self.service else "Consultation")
        return f"{self.get_request_type_display()} #{self.id}: {self.customer.phone_number} - {target} [{self.get_status_display()}]"

    def save(self, *args, **kwargs):
        if not self.tenant_id and self.conversation and self.conversation.tenant_id:
            self.tenant = self.conversation.tenant
        elif not self.tenant_id and self.customer and self.customer.tenant_id:
            self.tenant = self.customer.tenant
        # Backward compatibility sync
        if not self.service_address:
            addr_parts = [p for p in (self.organization, self.contact_email) if p]
            if addr_parts:
                self.service_address = " | ".join(addr_parts)
            else:
                self.service_address = "Remote / Online Consultation"
        if not self.ac_type:
            if self.request_type == RequestType.PRODUCT_DEMO and self.product:
                self.ac_type = f"{self.product.name} Demo"
            elif self.request_type == RequestType.CUSTOMER_SUPPORT and self.product:
                self.ac_type = f"{self.product.name} Support"
            elif self.service:
                self.ac_type = self.service.name
            else:
                self.ac_type = "Project consultation"
        if not self.requirements_summary and self.problem_description:
            self.requirements_summary = self.problem_description
        elif not self.problem_description and self.requirements_summary:
            self.problem_description = self.requirements_summary
        super().save(*args, **kwargs)


class BookingStep(models.TextChoices):
    NAME = 'NAME', 'Collecting Name'
    SERVICE = 'SERVICE', 'Selecting Service'
    AC_DETAILS = 'AC_DETAILS', 'Collecting AC Type & Problem'
    ADDRESS = 'ADDRESS', 'Collecting Address'
    SCHEDULE = 'SCHEDULE', 'Collecting Preferred Date & Time'
    REVIEW = 'REVIEW', 'Reviewing Request'
    EDIT = 'EDIT', 'Choosing Detail to Edit'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'

class BookingSession(models.Model):
    """
    Tracks state of active multi-turn conversational booking slot-filling.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='booking_sessions', null=True, blank=True)
    conversation = models.OneToOneField(Conversation, on_delete=models.CASCADE, related_name='booking_session')
    step = models.CharField(max_length=20, choices=BookingStep.choices, default=BookingStep.NAME)
    data = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Booking Session"
        verbose_name_plural = "Booking Sessions"

    def __str__(self):
        return f"Session for Conv #{self.conversation_id} [Step: {self.step}]"
