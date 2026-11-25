"""Fetch slow replies before the short transaction that applies a chat turn."""
import json
import re
from copy import copy
from dataclasses import dataclass

from apps.bookings.booking_service import BookingService
from apps.bookings.models import BookingSession, BookingStep
from .gemini_service import GeminiChatService
from .handlers import booking, booking_followup, image, text
from .intent_service import IntentType
from .models import ConversationStatus


@dataclass
class PreparedTurn:
    text_reply: str = ''
    image_reply: str = ''
    booking_interpretation: dict | None = None


def prepare_turn(message, conversation, intent, entity, media_id, flow_response):
    result = PreparedTurn()
    if conversation.status != ConversationStatus.BOT_ACTIVE or flow_response is not None:
        return result
    if message.startswith('[attachment:image]'):
        result.image_reply = image.generate_reply(message, media_id, conversation)
        return result
    if (message.startswith('[attachment:') or intent in (
            IntentType.HANDOVER, IntentType.BOOKING_STATUS, IntentType.IDENTITY)
            or message.lower() in ('main menu', 'menu', 'start fresh', 'booking_start_fresh')
            or re.match(r'^(cancel_booking|confirm_cancel|reschedule_booking)_\d+$', message)
            or booking_followup.generate_reply(message, conversation)):
        return result
    if BookingService.is_in_active_booking(conversation):
        session = BookingSession.objects.get(conversation=conversation)
        # Short AC-type answers are handled by the existing typo clarifier/collector.
        short_type = (session.step == BookingStep.AC_DETAILS and not session.data.get('ac_type')
                      and re.fullmatch(r'[A-Za-z]+(?:\s+[Aa][Cc])?', message.strip()))
        if not booking.is_control(message, session) and not short_type:
            result.booking_interpretation = GeminiChatService.interpret_booking_turn(
                text.build_contextual_prompt(message, conversation))
    elif intent == IntentType.BOOKING_START:
        if not message.startswith('book_service_'):
            for_other = BookingService.recipient_correction(message) == 'other'
            selected = entity or (None if for_other else conversation.service)
            step, data = BookingService.initial_state(conversation, selected, for_other)
            prompt_conversation = copy(conversation)
            from apps.services.models import Service
            if isinstance(selected, Service) or (for_other and not selected):
                prompt_conversation.service = selected
            result.booking_interpretation = GeminiChatService.interpret_booking_turn(text.build_contextual_prompt(
                message, prompt_conversation, booking_context=json.dumps({'step': step, 'details': data}, ensure_ascii=False)))
    elif intent != IntentType.UNKNOWN or conversation.unresolved_count < 1:
        result.text_reply = text.generate_reply(message, conversation)
    return result
