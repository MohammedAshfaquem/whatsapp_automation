"""Native booking forms: signed draft context and strictly validated field updates."""
import hashlib
import json
import re
from datetime import timedelta

from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone

from apps.bookings.booking_fields import apply_booking_fields
from apps.bookings.booking_service import BookingService
from apps.bookings.models import BookingSession, BookingStep
from apps.chatbot.models import ChannelChoice, Conversation

TOKEN_SALT = 'whatsapp-booking-form-v1'
INVALID_FORM = 'This form is no longer valid. Please use the latest form, or type your details in chat.'
ADDRESS_FIELDS = {'house': 100, 'street': 100, 'locality': 100, 'pin_code': 6, 'landmark': 120}


def formatted_address(values):
    return '\n'.join(f'{label}: {values[key]}' for key, label in (
        ('house', 'House/flat'), ('street', 'Street'), ('locality', 'Locality'),
        ('pin_code', 'PIN code'), ('landmark', 'Landmark')) if values.get(key))


def draft_revision(session):
    value = json.dumps(session.data, sort_keys=True, ensure_ascii=False) + session.updated_at.isoformat()
    return hashlib.sha256(value.encode()).hexdigest()


def read_token(response):
    token = response.get('flow_token') if isinstance(response, dict) else None
    if not isinstance(token, str) or len(token) > 2000:
        return None
    try:
        data = signing.loads(token, salt=TOKEN_SALT, max_age=7200)
        return data if isinstance(data, dict) else None
    except (signing.BadSignature, ValueError, TypeError):
        return None


def response_conversation_id(customer, response):
    claims = read_token(response)
    if not claims or claims.get('customer') != customer.pk:
        return None
    return Conversation.objects.filter(pk=claims.get('conversation'), customer=customer,
                                       channel=ChannelChoice.WHATSAPP).values_list('pk', flat=True).first()


def build_offer(conversation):
    flow_id = getattr(settings, 'WHATSAPP_BOOKING_FLOW_ID', '').strip()
    if not re.fullmatch(r'\d+', flow_id) or conversation.channel != ChannelChoice.WHATSAPP:
        return None
    session = BookingSession.objects.filter(conversation=conversation,
        step__in=(BookingStep.ADDRESS, BookingStep.SCHEDULE)).first()
    if not session:
        return None
    from apps.business.domain import is_it_business
    if is_it_business() and session.step == BookingStep.ADDRESS:
        return None
    claims = {'customer': conversation.customer_id, 'conversation': conversation.pk, 'session': session.pk,
              'step': session.step, 'revision': draft_revision(session)}
    today = timezone.localdate()
    selected = BookingService.parse_schedule_date(session.data.get('preferred_date', ''))
    data = {'min_date': today.isoformat(), 'max_date': (today + timedelta(days=180)).isoformat(),
            'selected_date': (selected or today).isoformat()}
    if session.step == BookingStep.ADDRESS:
        saved = session.data.get('address_fields', {})
        if formatted_address(saved) != session.data.get('service_address'):
            saved = {}
        data.update({key: saved.get(key, '') for key in ADDRESS_FIELDS})
    else:
        data.update({key: '' for key in ADDRESS_FIELDS})
    return {'flow_id': flow_id, 'flow_token': signing.dumps(claims, salt=TOKEN_SALT, compress=True),
            'screen': session.step, 'data': data}


@transaction.atomic
def apply_response(conversation, response):
    claims = read_token(response)
    session = BookingSession.objects.select_for_update().filter(conversation=conversation).first()
    if (not claims or not session or conversation.channel != ChannelChoice.WHATSAPP
            or claims.get('customer') != conversation.customer_id or claims.get('conversation') != conversation.pk
            or claims.get('session') != session.pk or claims.get('step') != session.step
            or claims.get('revision') != draft_revision(session)
            or session.step not in (BookingStep.ADDRESS, BookingStep.SCHEDULE)):
        return INVALID_FORM
    values = None
    fields = {}
    if session.step == BookingStep.ADDRESS:
        values = {}
        for key, limit in ADDRESS_FIELDS.items():
            value = response.get(key, '')
            if not isinstance(value, str) or len(value.strip()) > limit or '\n' in value or '\r' in value:
                return 'Please check the address fields and use a six-digit PIN code.'
            values[key] = value.strip()
        if (any(len(values[key]) < 2 for key in ('house', 'street', 'locality'))
                or not re.fullmatch(r'[1-9][0-9]{5}', values['pin_code'])):
            return 'Please complete the house, street and locality, with a valid six-digit PIN code.'
        address = formatted_address(values)
        # Apply through the same validator as typed/AI-proposed updates.
        if any(re.search(r'\?', values[key]) for key in values):
            return 'Please enter the service address in the form, or ask your question in chat.'
        fields['service_address'] = address
    requested_date = response.get('preferred_date')
    slot = response.get('time_slot')
    if (not isinstance(requested_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', requested_date)
            or not isinstance(slot, str) or slot not in ('morning', 'afternoon', 'evening')
            or not BookingService.parse_schedule(f'{requested_date} {slot}')):
        return 'Please choose a future visit date and time preference. Our team will confirm availability.'
    fields.update(preferred_date=requested_date, preferred_time_slot=slot)
    answer = apply_booking_fields(session, {'fields': fields})
    session.refresh_from_db()
    if values and session.data.get('service_address') == fields['service_address']:
        session.data['address_fields'] = values
        session.save(update_fields=['data', 'updated_at'])
    return answer
