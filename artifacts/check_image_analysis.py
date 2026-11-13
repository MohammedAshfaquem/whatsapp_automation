"""Verify the latest received WhatsApp photo without sending a customer message."""
import os
import json

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from apps.whatsapp.models import WhatsAppWebhookLog
from apps.chatbot.models import Message
from apps.chatbot.handlers.image import generate_reply, PHOTO_UNAVAILABLE, ANALYSIS_UNAVAILABLE
from apps.chatbot.ai_status import get_ai_status

event = WhatsAppWebhookLog.objects.filter(raw_payload__type='image').order_by('-pk').first()
inbound = Message.objects.select_related('conversation__customer', 'conversation__service').filter(
    external_message_id=event.whatsapp_message_id).first() if event else None
if not inbound:
    print(json.dumps({'image_event_found': False}))
else:
    reply = generate_reply(inbound.message_text, event.raw_payload.get('image', {}).get('id'), inbound.conversation)
    print(json.dumps({'image_event_found': True, 'analysis_reply_generated': bool(reply) and reply not in (
        PHOTO_UNAVAILABLE, ANALYSIS_UNAVAILABLE), 'media_unavailable': reply == PHOTO_UNAVAILABLE,
        'ai_status': get_ai_status()['status']}))
