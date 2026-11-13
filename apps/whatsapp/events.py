"""Inbound events preserve real user content and replay stored responses on retries."""
import logging
import json
import re
from datetime import datetime, timezone as utc_timezone
from django.utils import timezone
from django.db import DatabaseError
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import ChannelChoice
from .models import WhatsAppDelivery, WhatsAppWebhookLog
from .delivery import dispatch

logger = logging.getLogger(__name__)


def process_events(payload):
    processed = 0
    failures = 0
    for entry in payload.get('entry', []):
        for change in entry.get('changes', []):
            value = change.get('value', {})
            for event in value.get('statuses', []):
                if not event.get('id'):
                    continue
                state = event.get('status', '').upper()
                delivery = WhatsAppDelivery.objects.filter(provider_message_id=event.get('id', '')).first()
                if delivery and state in ('SENT', 'DELIVERED', 'READ', 'FAILED'):
                    ranks = {'PENDING': 0, 'SENDING': 0, 'UNKNOWN': 0, 'FAILED': 0, 'SENT': 1, 'DELIVERED': 2, 'READ': 3}
                    if ranks[state] >= ranks.get(delivery.status, 0) or (state == 'FAILED' and delivery.status not in ('DELIVERED', 'READ')):
                        # A failure webhook is final until staff have inspected the error.
                        delivery.status = 'BLOCKED' if state == 'FAILED' else state
                        delivery.last_error = str(event.get('errors', '')) if state == 'FAILED' else ''
                        delivery.save()
            names = {contact.get('wa_id'): contact.get('profile', {}).get('name') for contact in value.get('contacts', [])}
            for message in value.get('messages', []):
                message_id = message.get('id', '')
                sender = str(message.get('from', ''))
                if not message_id or not re.fullmatch(r'\+?\d{7,20}', sender):
                    continue
                phone = '+' + sender.lstrip('+')
                log, _ = WhatsAppWebhookLog.objects.get_or_create(event_type='message', whatsapp_message_id=message_id,
                    defaults={'sender_phone': phone, 'raw_payload': message})
                if log.is_processed:
                    continue
                try:
                    flow_response = None
                    kind = message.get('type')
                    if kind == 'text':
                        text = message.get('text', {}).get('body', '').strip()
                    elif kind == 'image':
                        caption = message.get('image', {}).get('caption', '').strip()
                        text = '[attachment:image]' + (f'\n{caption}' if caption else '')
                    elif kind == 'interactive':
                        interactive = message.get('interactive', {})
                        selected = interactive.get(interactive.get('type', ''), {})
                        if interactive.get('type') == 'nfm_reply':
                            raw = selected.get('response_json', '')
                            try:
                                flow_response = json.loads(raw) if isinstance(raw, str) and len(raw) <= 8000 else {}
                            except (ValueError, TypeError):
                                flow_response = {}
                            if not isinstance(flow_response, dict):
                                flow_response = {}
                            text = 'Booking form submitted'
                        else:
                            text = selected.get('id') or selected.get('title', '')
                    elif kind == 'button':
                        text = message.get('button', {}).get('payload') or message.get('button', {}).get('text', '')
                    elif kind == 'location':
                        location = message.get('location', {})
                        lat, lng = float(location['latitude']), float(location['longitude'])
                        if not (-90 <= lat <= 90 and -180 <= lng <= 180):
                            raise ValueError('Invalid shared location')
                        text = f"Shared location: {location.get('name', '')} {location.get('address', '')} https://maps.google.com/?q={lat},{lng}"
                    else:
                        text = f'[attachment:{kind}]'
                    if not text:
                        text = '[attachment:unsupported]'
                    source_time = None
                    try:
                        if message.get('timestamp'):
                            source_time = datetime.fromtimestamp(int(message['timestamp']), tz=utc_timezone.utc)
                    except (ValueError, TypeError, OverflowError, OSError):
                        logger.warning('Invalid source timestamp on inbound event %s', message_id)
                    image_options = {'image_media_id': message.get('image', {}).get('id')} if kind == 'image' else {}
                    if flow_response is not None:
                        image_options['flow_response'] = flow_response
                    result = ConversationService.process_message(phone_number=phone, message_text=text,
                        channel=ChannelChoice.WHATSAPP, external_message_id=message_id,
                        customer_name=names.get(sender.lstrip('+')), external_timestamp=source_time, **image_options)
                    if result.get('ignored_reason'):
                        logger.info('Ignored out-of-order inbound event %s', message_id)
                    ok = True
                    if result.get('reply'):
                        record, _ = WhatsAppDelivery.objects.get_or_create(dedup_key=f'reply:{message_id}', defaults={
                            'recipient_phone': phone, 'payload': {'text': result['reply'], 'options': result.get('options'),
                                                                 'flow': result.get('flow')}})
                        ok = dispatch(record.pk)
                    log.is_processed = ok
                    log.error_message = '' if ok else 'Reply delivery failed or is uncertain. Review the outbound queue.'
                    log.save()
                    processed += int(ok)
                except Exception as error:
                    logger.exception('Unable to process inbound event %s', message_id)
                    log.error_message = str(error)
                    try:
                        log.save(update_fields=['error_message'])
                    except DatabaseError:
                        logger.warning('Could not persist failure log for inbound event %s', message_id)
                    failures += 1
    return {'status': 'EVENT_PROCESSED', 'processed': processed, 'failures': failures}
