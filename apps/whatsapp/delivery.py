import logging
from django.db import transaction
from django.utils import timezone
from .models import WhatsAppDelivery
from .whatsapp_client import WhatsAppClient

logger = logging.getLogger(__name__)


def dispatch(delivery_id):
    """Claim once. Ambiguous timeouts require review, never an automatic duplicate."""
    with transaction.atomic():
        record = WhatsAppDelivery.objects.select_for_update().get(pk=delivery_id)
        if record.status not in ('PENDING', 'FAILED') or record.attempts >= 3:
            return record.status in ('SENT', 'DELIVERED', 'READ')
        record.status = 'SENDING'
        record.attempts += 1
        record.save(update_fields=['status', 'attempts', 'updated_at'])
    payload = record.payload
    try:
        if payload.get('template'):
            ok, provider_id = WhatsAppClient.send_template_message(record.recipient_phone, **payload['template'])
        elif payload.get('flow'):
            ok, provider_id = WhatsAppClient.send_flow_message(record.recipient_phone, payload['text'], **payload['flow'])
        elif payload.get('options'):
            ok, provider_id = WhatsAppClient.send_interactive_options(recipient_phone=record.recipient_phone,
                body_text=payload['text'], options=payload['options'])
        else:
            ok, provider_id = WhatsAppClient.send_text_message(recipient_phone=record.recipient_phone,
                message_text=payload['text'])
    except Exception as error:
        ok, provider_id = False, f'Uncertain delivery: {type(error).__name__}'
        logger.exception('Outbound delivery failed for record %s', record.pk)
    error = str(provider_id or '')
    state = 'SENT' if ok else ('UNKNOWN' if any(word in error.lower() for word in ('timeout', 'uncertain', 'connection')) else 'FAILED')
    WhatsAppDelivery.objects.filter(pk=record.pk, status='SENDING').update(
        status=state, provider_message_id=provider_id if ok else '',
        last_error='' if ok else error, updated_at=timezone.now())
    return ok
