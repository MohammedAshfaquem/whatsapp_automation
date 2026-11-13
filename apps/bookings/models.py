from django.db import models
from apps.chatbot.models import Customer, Conversation
from apps.services.models import Service

class BookingStatus(models.TextChoices):
    PENDING = 'PENDING', 'Pending Confirmation'
    CONFIRMED = 'CONFIRMED', 'Confirmed'
    REJECTED = 'REJECTED', 'Rejected'
    COMPLETED = 'COMPLETED', 'Completed'
    CANCELLED = 'CANCELLED', 'Cancelled'

class Booking(models.Model):
    """
    AC Service Booking submitted by customer via chat and reviewed/managed by shop owner.
    Initially in PENDING state; bot never claims confirmation until confirmed by owner.
    """
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='bookings')
    conversation = models.ForeignKey(Conversation, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True, related_name='bookings')
    recipient_name = models.CharField(max_length=150, blank=True, help_text='Person receiving the service when booked for someone else')

    ac_type = models.CharField(max_length=100, blank=True, help_text="e.g. Split AC, Window AC")
    ac_brand = models.CharField(max_length=100, blank=True, help_text="e.g. Daikin, Voltas, LG")
    problem_description = models.TextField(blank=True, help_text="Description of issue (e.g. not cooling, water leakage)")
    service_address = models.TextField(help_text="Customer address where service is required")
    
    preferred_date = models.DateField(null=True, blank=True, help_text="Customer requested appointment date")
    preferred_time_slot = models.CharField(max_length=100, blank=True, help_text="e.g. Morning (10 AM - 1 PM) or Evening (3 PM - 6 PM)")
    
    status = models.CharField(
        max_length=20,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
        db_index=True
    )
    owner_notes = models.TextField(blank=True, help_text="Internal notes added by shop owner/technician")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "AC Service Booking"
        verbose_name_plural = "AC Service Bookings"

    def __str__(self):
        svc_name = self.service.name if self.service else "Custom AC Service"
        return f"Booking #{self.id}: {self.customer.phone_number} - {svc_name} [{self.get_status_display()}]"

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
