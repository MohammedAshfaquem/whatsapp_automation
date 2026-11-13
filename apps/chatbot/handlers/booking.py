"""Chat around an active booking; slot validation remains in apps.bookings."""
import re
from apps.bookings.booking_service import BookingService
from apps.bookings.models import BookingSession, BookingStep
from apps.bookings.booking_fields import apply_booking_fields
from apps.bookings.ac_clarification import clarify_ac_type
from apps.business.models import BusinessProfile
from apps.services.models import Service
from apps.services.services import get_services_formatted_text
from ..intent_service import IntentService, IntentType
from ..language import say, choice
from ..reply import ChatReply
from . import text


def welcome_back(conversation):
    customer = conversation.customer
    language = customer.preferred_language
    profile = BusinessProfile.get_active()
    reply = say('returning_greeting', language).format(
        name=f' {customer.name}' if customer.name else '',
        shop=profile.shop_name if profile else 'our service desk')
    reply += '\n\n' + say('unfinished_booking', language)
    options = [choice('booking_resume', 'continue_booking', language),
               choice('booking_start_fresh', 'start_fresh', language),
               choice('talk to agent', 'human', language)]
    return reply, options


def interpret_update(message, conversation, interpretation, initial=False, intent=None, entity=None):
    """Understand a free-text turn; mutations are validated by the booking service."""
    if not interpretation:
        return None
    if intent is None:
        intent, entity = IntentService.detect_intent(message)
    session = BookingSession.objects.get(conversation=conversation)
    if interpretation.get('fields') or interpretation.get('clear_fields'):
        reply = apply_booking_fields(session, interpretation)
        if interpretation['kind'] == 'conversation' and interpretation['reply'].strip():
            if intent in (IntentType.SERVICE_PRICE, IntentType.WORKING_HOURS, IntentType.SERVICE_AREAS,
                          IntentType.SHOP_LOCATION, IntentType.PAYMENT_METHODS, IntentType.WARRANTY_POLICY,
                          IntentType.BOOKING_STATUS, IntentType.DISCOUNT_ENQUIRY, IntentType.FAQ_MATCH):
                conversation.refresh_from_db()
                answer = text.generate_deterministic_reply(intent, entity or conversation.service,
                    get_services_formatted_text(), conversation, message)
            else:
                answer = interpretation['reply'].strip()[:2000]
            reply = answer + '\n\n' + reply
        return ChatReply(reply, offer_booking_form=True)
    if initial:
        return None
    if interpretation['kind'] == 'recipient_correction' and interpretation['recipient'] in ('self', 'other'):
        return ChatReply(BookingService.set_recipient(session, interpretation['recipient']), offer_booking_form=True)
    if interpretation['kind'] == 'conversation' and 5 < len(interpretation['reply'].strip()) <= 2000:
        if intent in (IntentType.SERVICE_PRICE, IntentType.WORKING_HOURS, IntentType.SERVICE_AREAS,
                      IntentType.SHOP_LOCATION, IntentType.PAYMENT_METHODS, IntentType.WARRANTY_POLICY,
                      IntentType.BOOKING_STATUS, IntentType.DISCOUNT_ENQUIRY, IntentType.FAQ_MATCH):
            return None  # Verified facts keep their existing deterministic response.
        return ChatReply(interpretation['reply'].strip())
    return None


def is_control(message, session):
    return (message.lower() in ('cancel', 'cancel booking', 'stop', 'quit', 'exit', 'submit', 'confirm', 'yes',
                                'booking_resume', 'continue booking', 'resume booking')
            or message.startswith(('booking_', 'service_', 'select_service_', 'book_service_'))
            or (session.step == BookingStep.SCHEDULE and message.lower() in BookingService.DATE_CHANGE_REQUESTS)
            or session.step == BookingStep.EDIT or IntentService.is_simple_greeting(message))


def handle_active_booking(message, conversation, intent, entity, interpretation=None):
    options = None
    booking_id = None
    session = BookingSession.objects.get(conversation=conversation)
    control = is_control(message, session)
    if ((not control and intent in (IntentType.UNKNOWN, IntentType.AC_PROBLEM))
            or (session.data.get('pending_ac_type') and message.lower() in ('yes', 'yes please', 'correct', 'yeah', 'no', 'nope'))):
        clarification = clarify_ac_type(session, message)
        if clarification:
            return ChatReply(clarification)
    if not control:
        interpreted = interpret_update(message, conversation, interpretation, intent=intent, entity=entity)
        if interpreted:
            return interpreted
    recipient = BookingService.recipient_correction(message)
    if recipient:
        return ChatReply(BookingService.set_recipient(session, recipient), offer_booking_form=True)
    explicit_service = (intent in (IntentType.BOOKING_START, IntentType.SERVICE_SELECT)
                        and isinstance(entity, Service))
    side_question = intent in (IntentType.SERVICE_PRICE, IntentType.WORKING_HOURS, IntentType.SERVICE_AREAS,
        IntentType.SHOP_LOCATION, IntentType.PAYMENT_METHODS, IntentType.WARRANTY_POLICY,
        IntentType.FAQ_MATCH, IntentType.BOOKING_STATUS, IntentType.DISCOUNT_ENQUIRY)
    side_question = side_question or (intent == IntentType.SERVICE_LIST and session.step != BookingStep.SERVICE)
    side_question = side_question or (intent == IntentType.AC_PROBLEM and session.step != BookingStep.AC_DETAILS)
    if session.step == BookingStep.AC_DETAILS and intent == IntentType.SERVICE_PRICE:
        side_question = any(re.search(pattern, message, re.I) for pattern in IntentService.PRICE_PATTERNS)
    if IntentService.is_simple_greeting(message):
        reply_text, options = welcome_back(conversation)
    elif message.lower() in ('booking_resume', 'continue booking', 'resume booking'):
        reply_text = BookingService.review(session) if session.step == BookingStep.REVIEW else BookingService.prompt(session)
    elif explicit_service:
        session.data.update(service_id=entity.pk, service_name=entity.name)
        if session.step == BookingStep.SERVICE:
            session.step = BookingStep.AC_DETAILS
        session.save()
        conversation.service = entity
        conversation.save(update_fields=['service'])
        reply_text = f'*{entity.name}*\n\n' + (BookingService.review(session) if session.step == BookingStep.REVIEW else BookingService.prompt(session))
    elif (session.step == BookingStep.SCHEDULE and BookingService.is_schedule_answer(message)
            and (not side_question or intent == IntentType.WORKING_HOURS)):
        reply_text, booking_id = BookingService.process_booking_step(conversation, message)
    elif side_question:
        if intent == IntentType.SERVICE_PRICE and not entity:
            entity = conversation.service
        if intent == IntentType.UNKNOWN:
            reply_text = BookingService.prompt(session)
        else:
            reply_text = text.generate_deterministic_reply(intent, entity, get_services_formatted_text(), conversation, message)
            reply_text += '\n\n' + BookingService.prompt(session)
    else:
        if not control and (
                ('?' in message and session.step in (BookingStep.NAME, BookingStep.ADDRESS, BookingStep.SCHEDULE))
                or IntentService.is_clarification(message)):
            return ChatReply(BookingService.prompt(session))
        reply_text, booking_id = BookingService.process_booking_step(conversation, message)
    return ChatReply(reply_text, options=options, booking_id=booking_id,
                     offer_booking_form=not IntentService.is_simple_greeting(message))
