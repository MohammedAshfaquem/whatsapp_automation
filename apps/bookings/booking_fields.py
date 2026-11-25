"""Validate proposed language-model fields before changing a booking draft."""
from django.db import transaction

from apps.chatbot.language import say
from apps.chatbot.intent_service import IntentService
from apps.services.models import Service
from .models import BookingSession, BookingStep

FIELD_LIMITS = {'name': 100, 'recipient_name': 100, 'service_name': 150, 'ac_type': 100,
                'problem_description': 1500, 'service_address': 1500,
                'preferred_date': 100, 'preferred_time_slot': 100}


def valid_name(value):
    return (2 <= len(value) <= 100 and not IntentService.is_clarification(value)
            and all(c.isalpha() or c.isspace() or c in ".'-" for c in value))


def next_missing_step(data):
    from .booking_service import BookingService
    if ((data.get('booking_for_other') and not data.get('recipient_name'))
            or (not data.get('booking_for_other') and not data.get('name'))):
        return BookingStep.NAME
    has_target = False
    if data.get('product_id'):
        from apps.business.models import Product
        has_target = Product.objects.filter(pk=data['product_id'], is_active=True).exists()
    if not has_target and data.get('service_id'):
        has_target = Service.objects.filter(pk=data['service_id'], is_active=True).exists()
    if not has_target:
        return BookingStep.SERVICE
    if not data.get('ac_type') or not data.get('problem_description'):
        return BookingStep.AC_DETAILS
    if not data.get('service_address'):
        return BookingStep.ADDRESS
    if not BookingService.parse_schedule(f"{data.get('preferred_date', '')} {data.get('preferred_time_slot', '')}"):
        return BookingStep.SCHEDULE
    return BookingStep.REVIEW



@transaction.atomic
def apply_booking_fields(session, interpretation):
    """Apply explicit updates only. Never submit a booking or trust model action IDs."""
    from .booking_service import BookingService
    session = BookingSession.objects.select_for_update(of=('self',)).select_related('conversation__customer').get(pk=session.pk)
    data = dict(session.data)
    fields = interpretation.get('fields', {})
    errors = []
    updated_name = None
    recipient = interpretation.get('recipient')
    if recipient in ('self', 'other'):
        data['booking_for_other'] = recipient == 'other'
        if recipient == 'self':
            data.pop('recipient_name', None)
        data.pop('recipient_resume_step', None)
    for field in interpretation.get('clear_fields', []):
        if field in FIELD_LIMITS:
            data.pop(field if field != 'service_name' else 'service_id', None)
            if field == 'service_name':
                data.pop('service_name', None)
            if field == 'preferred_date':
                data.pop('preferred_time_slot', None)
    # Date first regardless of JSON key order: a newly supplied time must survive its date.
    ordered = [key for key in FIELD_LIMITS if key in fields]
    for field in ordered:
        value = fields[field]
        if not isinstance(value, str) or not value.strip():
            continue
        value = value.strip()
        if len(value) > FIELD_LIMITS[field]:
            errors.append(field)
            continue
        valid = True
        if field in ('name', 'recipient_name'):
            valid = valid_name(value) and (field != 'recipient_name' or data.get('booking_for_other'))
            valid = valid and not (field == 'name' and data.get('booking_for_other'))
        elif field == 'service_name':
            from apps.business.domain import is_it_business
            if is_it_business():
                from apps.business.models import Product
                prod = Product.objects.filter(name__iexact=value, is_active=True).first()
                if not prod:
                    prod = IntentService.find_matching_product(value.lower())
                if prod:
                    data.update(product_id=prod.pk, product_name=prod.name, request_type='product_demo',
                                ac_type=f"{prod.name} Demo")
                    data.pop('service_id', None)
                    data.pop('service_name', None)
                    continue
            service = Service.objects.filter(name__iexact=value, is_active=True).first()
            if not service and is_it_business():
                service = IntentService.find_matching_service(value.lower())
            if service:
                data.update(service_id=service.pk, service_name=service.name, request_type='consultation',
                            ac_type=service.name)
                data.pop('product_id', None)
                data.pop('product_name', None)
            else:
                errors.append(field)
            continue

        elif field == 'ac_type':
            from apps.business.domain import is_it_business
            if is_it_business():
                valid = len(value) >= 2 and not IntentService.is_clarification(value)
            else:
                types = {f'{kind} ac': f'{kind.title()} AC' for kind in ('window', 'split', 'inverter', 'cassette', 'tower', 'other')}
                types['type to be confirmed'] = 'Type to be confirmed'
                value = types.get(value.lower(), '')
                valid = bool(value)
        elif field == 'service_address':
            from apps.business.domain import is_it_business
            valid = (len(value) >= 3 if is_it_business() else len(value) >= 12 and len(value.split()) >= 3) and '?' not in value
            valid = valid and not IntentService.is_clarification(value)
        elif field == 'problem_description':
            valid = len(value) >= 2 and any(c.isalpha() for c in value) and '?' not in value
            valid = valid and not BookingService.recipient_correction(value)
            valid = valid and not IntentService.is_clarification(value)
        elif field == 'preferred_date':
            parsed = BookingService.parse_schedule_date(value)
            valid = parsed is not None
            if parsed:
                value = parsed.isoformat()
                if value != data.get(field):
                    data.pop('preferred_time_slot', None)
        elif field == 'preferred_time_slot':
            parsed = BookingService.parse_schedule_time(value)
            valid = parsed is not None
            if parsed:
                value = parsed[0]
        if valid:
            data[field] = value.title() if field in ('name', 'recipient_name') else value
            if field == 'name':
                updated_name = data[field]
        else:
            errors.append(field)
    if data.get('preferred_date') and not BookingService.parse_schedule_date(data['preferred_date']):
        data.pop('preferred_date', None)
        data.pop('preferred_time_slot', None)
    if data.get('preferred_date') and data.get('preferred_time_slot') and not BookingService.parse_schedule(
            f"{data['preferred_date']} {data['preferred_time_slot']}"):
        data.pop('preferred_time_slot', None)
        errors.append('preferred_time_slot')
    data.pop('return_to_review', None)
    session.data = data
    session.step = next_missing_step(data)
    session.save(update_fields=['data', 'step', 'updated_at'])
    conversation = session.conversation
    conversation.service_id = data.get('service_id')
    conversation.save(update_fields=['service'])
    if updated_name is not None:
        conversation.customer.name = updated_name
        conversation.customer.save(update_fields=['name'])
    reply = BookingService.review(session) if session.step == BookingStep.REVIEW else BookingService.prompt(session)
    if errors:
        reply = say('invalid', conversation.customer.preferred_language) + '\n\n' + reply
    return reply
