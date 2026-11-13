"""One status transition and durable customer notification across all staff entry points."""
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from apps.chatbot.models import ChannelChoice, MessageDirection
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.delivery import dispatch
from .models import Booking, BookingStatus

ALLOWED = {
    BookingStatus.PENDING: {BookingStatus.CONFIRMED, BookingStatus.REJECTED, BookingStatus.CANCELLED},
    BookingStatus.CONFIRMED: {BookingStatus.COMPLETED, BookingStatus.CANCELLED},
}


def change_booking_status(booking, target, owner_notes=None):
    with transaction.atomic():
        locked = Booking.objects.select_for_update().get(pk=booking.pk)
        if locked.status == target:
            return locked
        if target not in ALLOWED.get(locked.status, set()):
            raise ValueError('This booking cannot move to that status.')
        locked.status = target
        if owner_notes is not None:
            locked.owner_notes = owner_notes
        locked.save()
        if locked.conversation and locked.conversation.channel == ChannelChoice.WHATSAPP:
            last_inbound = locked.conversation.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
            in_window = last_inbound and last_inbound.created_at >= timezone.now() - timedelta(hours=24)
            text = f'Booking #{locked.id}: {locked.get_status_display()}.\n{locked.service.name if locked.service else "AC service"}\n{locked.preferred_date or "Date to be arranged"} · {locked.preferred_time_slot}'
            payload = {'text': text}
            blocked = False
            if not in_window:
                template = getattr(settings, 'WHATSAPP_BOOKING_STATUS_TEMPLATE', '')
                if template:
                    payload = {'template': {'name': template, 'language': getattr(settings, 'WHATSAPP_TEMPLATE_LANGUAGE', 'en'),
                        'parameters': [str(locked.id), locked.get_status_display()]}}
                else:
                    blocked = True
            delivery, _ = WhatsAppDelivery.objects.get_or_create(dedup_key=f'booking:{locked.id}:{target}', defaults={
                'recipient_phone': locked.customer.phone_number, 'payload': payload,
                'status': 'BLOCKED' if blocked else 'PENDING',
                'last_error': 'An approved booking-status template is required outside the customer service window.' if blocked else ''})
            if not blocked:
                transaction.on_commit(lambda: dispatch(delivery.pk))
        return locked
