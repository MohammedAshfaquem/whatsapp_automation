"""Validated, resumable booking requests; availability is confirmed by staff."""
import re
from datetime import date, datetime, time, timedelta

from django.db import transaction
from django.utils import timezone

from apps.chatbot.language import say, choice
from apps.chatbot.intent_service import IntentService
from apps.services.models import Service, PriceType
from .models import Booking, BookingSession, BookingStep, BookingStatus


class BookingService:
    DATE_CHANGE_REQUESTS = ('choose date', 'another date')
    STEPS = [BookingStep.NAME, BookingStep.SERVICE, BookingStep.AC_DETAILS,
             BookingStep.ADDRESS, BookingStep.SCHEDULE, BookingStep.REVIEW]
    KEYS = {BookingStep.NAME: 'name', BookingStep.SERVICE: 'service',
            BookingStep.AC_DETAILS: 'details', BookingStep.ADDRESS: 'address',
            BookingStep.SCHEDULE: 'schedule', BookingStep.REVIEW: 'review', BookingStep.EDIT: 'edit'}

    @classmethod
    def is_in_active_booking(cls, conversation):
        return BookingSession.objects.filter(conversation=conversation).exclude(
            step__in=[BookingStep.COMPLETED, BookingStep.CANCELLED]).exists()

    @classmethod
    def prompt(cls, session):
        lang = session.conversation.customer.preferred_language
        data = session.data
        from apps.business.domain import is_it_business
        if is_it_business():
            prod_name = data.get('product_name', '')
            if session.step == BookingStep.NAME:
                if data.get('booking_for_other'):
                    return say('recipient_name', lang)
                if prod_name:
                    return f"May I have your name to arrange the {prod_name} demo?"
                return say('name', lang)
            if session.step == BookingStep.SERVICE:
                return "Which IT agency service or product would you like to explore (e.g. Website Development, Mobile App, TABLO, or WhatsApp CRM)?"
            if session.step == BookingStep.AC_DETAILS:
                if prod_name:
                    if 'tablo' in prod_name.lower():
                        return "Could you briefly share your restaurant type (e.g. QSR, café, food court) and any key operational challenge?"
                    if 'whatsapp' in prod_name.lower():
                        return "Could you briefly share your business type and your current customer enquiry workflow?"
                    return f"What are your requirements for {prod_name}?"
                return say('details', lang)
            if session.step == BookingStep.ADDRESS:
                if data.get('booking_for_other'):
                    return say('recipient_address', lang)
                return say('address', lang)
            if session.step == BookingStep.SCHEDULE:
                if data.get('preferred_date'):
                    return say('time_for_date', lang).format(date=cls.display_date(data['preferred_date'], lang))
                if data.get('preferred_time_slot'):
                    return say('date_for_time', lang).format(time=data['preferred_time_slot'])
                return say('schedule', lang)
            if session.step == BookingStep.REVIEW:
                return cls.review(session)
            return say(cls.KEYS.get(session.step, 'service'), lang)

        if data.get('booking_for_other'):
            if session.step == BookingStep.NAME and not data.get('recipient_name'):
                return say('recipient_name', lang)
            if session.step == BookingStep.AC_DETAILS:
                if data.get('ac_type') and not data.get('problem_description'):
                    return say('recipient_issue', lang).format(ac_type=data['ac_type'])
                return say('recipient_type', lang)
            if session.step == BookingStep.ADDRESS:
                return say('recipient_address', lang)
        if session.step == BookingStep.AC_DETAILS and data.get('ac_type') and not data.get('problem_description'):
            return say('issue', lang).format(ac_type=data['ac_type'])
        if session.step == BookingStep.SCHEDULE:
            if data.get('preferred_date'):
                return say('time_for_date', lang).format(date=cls.display_date(data['preferred_date'], lang))
            if data.get('preferred_time_slot'):
                return say('date_for_time', lang).format(time=data['preferred_time_slot'])
        return say(cls.KEYS.get(session.step, 'service'), lang)


    @classmethod
    def progress(cls, conversation):
        session = BookingSession.objects.filter(conversation=conversation).first()
        active = bool(session and session.step not in [BookingStep.COMPLETED, BookingStep.CANCELLED])
        step = session.step if active else None
        return {'active': active, 'step': step, 'current': cls.STEPS.index(step) + 1 if step in cls.STEPS else 6,
                'total': 6, 'label': say(cls.KEYS.get(step, 'edit') + '_label', conversation.customer.preferred_language) if active else '',
                'ac_type': session.data.get('ac_type', '') if active else '',
                'preferred_date': session.data.get('preferred_date', '') if active else ''}

    @classmethod
    def options(cls, conversation):
        session = BookingSession.objects.filter(conversation=conversation).first()
        if not session or not cls.is_in_active_booking(conversation):
            return None
        lang = conversation.customer.preferred_language
        if session.step == BookingStep.REVIEW:
            return [choice('booking_submit', 'submit', lang), choice('booking_edit', 'edit_button', lang), choice('cancel', 'cancel', lang)]
        if session.step == BookingStep.EDIT:
            return [{'id': f'booking_edit_{step.lower()}', 'title': say(cls.KEYS[step] + '_label', lang)[:24]}
                    for step in cls.STEPS[:-1]]
        if session.step == BookingStep.SERVICE:
            return [{'id': f'service_{s.id}', 'title': s.name[:24], 'description': s.formatted_price[:72]}
                    for s in Service.objects.filter(is_active=True)[:10]]
        if session.step == BookingStep.SCHEDULE:
            if not session.data.get('preferred_date'):
                return [choice('today', 'today', lang), choice('tomorrow', 'tomorrow', lang),
                        choice('choose date', 'another_date', lang)]
            return [choice(slot, slot, lang) for slot in ('morning', 'afternoon', 'evening')
                    if cls.parse_schedule(f"{session.data['preferred_date']} {slot}")]
        # Keep data-entry turns quiet. Cancel/help still work when typed.
        return []

    @classmethod
    def cancel_booking_session(cls, conversation):
        BookingSession.objects.filter(conversation=conversation).update(step=BookingStep.CANCELLED)
        return say('cancelled', conversation.customer.preferred_language)

    @classmethod
    def initial_state(cls, conversation, matched_service=None, for_other=False):
        """Build the same initial draft for AI context and for persistence."""
        data = {}
        if conversation.customer.name:
            data['name'] = conversation.customer.name
        from apps.business.models import Product
        if isinstance(matched_service, Product):
            data.update(product_id=matched_service.id, product_name=matched_service.name, request_type='product_demo',
                        ac_type=f"{matched_service.name} Demo")
        elif matched_service and matched_service.is_active:
            from apps.business.domain import is_it_business
            if is_it_business():
                data.update(service_id=matched_service.id, service_name=matched_service.name, request_type='consultation',
                            ac_type='Project consultation')
            else:
                data.update(service_id=matched_service.id, service_name=matched_service.name)
        if for_other:
            data['booking_for_other'] = True
        has_item = bool(data.get('service_id') or data.get('product_id'))
        step = BookingStep.NAME if not data.get('name') else (BookingStep.AC_DETAILS if has_item else BookingStep.SERVICE)
        if for_other:
            step = BookingStep.NAME
        return step, data

    @classmethod
    def start_booking_session(cls, conversation, matched_service=None, for_other=False):
        step, data = cls.initial_state(conversation, matched_service, for_other)
        if isinstance(matched_service, Service) or for_other:
            conversation.service = matched_service if isinstance(matched_service, Service) else None
            conversation.save(update_fields=['service'])
        session, _ = BookingSession.objects.update_or_create(conversation=conversation, defaults={'data': data, 'step': step})
        target_name = matched_service.name if hasattr(matched_service, 'name') else ''
        service = f" {target_name}." if target_name else ''
        lang = conversation.customer.preferred_language
        return f"{say('start', lang)}{service}\n{say('booking_help', lang)}\n\n{cls.prompt(session)}", None


    @staticmethod
    def recipient_correction(message):
        """Recognize explicit recipient corrections, never infer ownership from a name."""
        text = message.lower().replace('’', "'")
        relation = r'(?:friend|brother|sister|mother|father|wife|husband|parent|neighbour|neighbor)'
        patterns = {
            'self': r"\b(?:for me|my own ac|for myself|it's mine|it is mine)\b",
            'other': (r'\bfor\s+(?:(?:my|a|our)\s+)?' + relation + r'\b|\bfor someone else\b|'
                      r'\bmy\s+' + relation + r"(?:'s|s)?\s+(?:ac|air conditioner|unit|house|home)\b"),
        }
        corrections = []
        for recipient, pattern in patterns.items():
            for match in re.finditer(pattern, text):
                if not re.search(r"\b(?:not|never|isn't|isnt)(?:\s+actually)?\s*$", text[:match.start()]):
                    corrections.append((match.start(), recipient))
        return max(corrections)[1] if corrections else None

    @classmethod
    def set_recipient(cls, session, recipient):
        data = session.data
        lang = session.conversation.customer.preferred_language
        data['booking_for_other'] = recipient == 'other'
        if cls.recipient_correction(data.get('problem_description', '')):
            data.pop('problem_description', None)
        if recipient == 'other' and not data.get('recipient_name'):
            resume_step = session.step
            if not data.get('problem_description') and data.get('ac_type'):
                resume_step = BookingStep.AC_DETAILS
            data.setdefault('recipient_resume_step', resume_step)
            session.step = BookingStep.NAME
        elif recipient == 'self':
            data.pop('recipient_name', None)
            session.step = data.pop('recipient_resume_step', session.step)
            if session.step == BookingStep.NAME and data.get('name'):
                session.step = BookingStep.AC_DETAILS if data.get('service_id') else BookingStep.SERVICE
        session.data = data
        session.save()
        return say('recipient_ack' if recipient == 'other' else 'self_ack', lang) + '\n\n' + cls.prompt(session)

    @staticmethod
    def normalize_schedule(text):
        normalized = text.lower().strip()
        for source, target in {'നാളെ': 'tomorrow', 'ഇന്ന്': 'today', 'രാവിലെ': 'morning', 'വൈകുന്നേരം': 'evening', 'naale': 'tomorrow', 'nale': 'tomorrow', 'ravile': 'morning', 'vaikunneram': 'evening', 'कल': 'tomorrow', 'आज': 'today', 'सुबह': 'morning', 'शाम': 'evening'}.items():
            normalized = normalized.replace(source, target)
        return normalized

    @classmethod
    def has_schedule_date(cls, text):
        return bool(re.search(
            r'\b(?:today|tomorrow|yesterday|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b'
            r'|\b\d{4}-\d{2}-\d{2}\b|\b\d{2}[/-]\d{2}[/-]\d{4}\b', cls.normalize_schedule(text)))

    @classmethod
    def is_schedule_answer(cls, text):
        """A date question is a booking answer; a business question stays a question."""
        normalized = cls.normalize_schedule(text)
        if re.search(r'\b(price|cost|charges|rate|hours|open|close|closed|payment|warranty|discount|offer)\b', normalized):
            return False
        return (cls.has_schedule_date(text) or cls.parse_schedule_time(text) is not None
                or bool(re.search(r'\b\d{1,2}(?::\d{2})?\s*(?:am|pm)\b', normalized))
                or normalized in cls.DATE_CHANGE_REQUESTS)

    @classmethod
    def parse_schedule_date(cls, text):
        """Read a preferred day without requiring a time in the same message."""
        normalized = cls.normalize_schedule(text)
        today = timezone.localdate()
        requested_date = None
        iso = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', normalized)
        indian = re.search(r'\b(\d{2})[/-](\d{2})[/-](\d{4})\b', normalized)
        try:
            if iso:
                requested_date = date.fromisoformat(iso.group(1))
            elif indian:
                requested_date = date(int(indian[3]), int(indian[2]), int(indian[1]))
            elif 'day after tomorrow' in normalized:
                requested_date = today + timedelta(days=2)
            elif 'tomorrow' in normalized:
                requested_date = today + timedelta(days=1)
            elif re.search(r'\btoday\b', normalized):
                requested_date = today
            else:
                for index, day in enumerate(['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']):
                    if re.search(r'\b' + day + r'\b', normalized):
                        requested_date = today + timedelta(days=(index - today.weekday()) % 7 or 7)
                        break
        except ValueError:
            return None
        if not requested_date or requested_date < today or requested_date > today + timedelta(days=180):
            return None
        return requested_date

    @classmethod
    def parse_schedule_time(cls, text):
        """Return a readable time/slot and its cutoff for past-time validation."""
        normalized = cls.normalize_schedule(text)
        clock = re.search(r'\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b', normalized)
        military = re.search(r'\b([01]?\d|2[0-3]):([0-5]\d)\b', normalized)
        slot = re.search(r'\b(morning|afternoon|evening)\b', normalized)
        chosen_time = None
        if clock:
            hour, minute = int(clock[1]), int(clock[2] or 0)
            if not 1 <= hour <= 12 or minute > 59:
                return None
            chosen_time = time(hour % 12 + (12 if clock[3] == 'pm' else 0), minute)
        elif military:
            chosen_time = time(int(military[1]), int(military[2]))
        elif slot:
            chosen_time = time({'morning': 12, 'afternoon': 17, 'evening': 21}[slot[1]])
        return ((clock or military or slot).group(0), chosen_time) if chosen_time else None

    @classmethod
    def parse_schedule(cls, text):
        """Validate a complete day and time, including at final submission."""
        requested_date = cls.parse_schedule_date(text)
        parsed_time = cls.parse_schedule_time(text)
        if not requested_date or not parsed_time:
            return None
        if requested_date == timezone.localdate() and timezone.localtime().time().replace(tzinfo=None) >= parsed_time[1]:
            return None
        return requested_date

    @staticmethod
    def display_date(iso_date, lang):
        requested = date.fromisoformat(iso_date)
        today = timezone.localdate()
        if requested == today:
            return say('today', lang).lower()
        if requested == today + timedelta(days=1):
            return say('tomorrow', lang).lower()
        return iso_date

    @staticmethod
    def collect_ac_details(data, message):
        """Keep type and symptoms separately, even when supplied across turns."""
        from apps.business.domain import is_it_business
        if is_it_business():
            from apps.chatbot.intent_service import IntentService
            if len(message.strip()) >= 3 and not IntentService.is_clarification(message):
                data.setdefault('ac_type', 'Project consultation')
                data['problem_description'] = message.strip()[:1500]
            return
        lower = message.lower()
        ac_type = next((kind + ' AC' for kind in ('Window', 'Split', 'Inverter', 'Cassette', 'Tower', 'Other')
                        if re.search(r'\b' + kind.lower() + r'\b', lower)), None)
        if ac_type:
            data['ac_type'] = ac_type
        if lower.strip(' .!?') in ('not sure', 'dont know', "don't know", 'unknown'):
            data['ac_type'] = 'Type to be confirmed'
            return
        # Strip an introduction/type, not symptom words such as "not" or "leaking".
        remainder = re.sub(
            r"\b(?:i|have|a|an|my|the|it|is|its|type|ac|air|conditioner|window|split|inverter|cassette|tower|other)\b",
            ' ', lower)
        remainder = re.sub(r'\b(?:at|in)\s+(?:home|house)\b', ' ', remainder)
        remainder = re.sub(r'\b\d+(?:\.\d+)?\s*(?:tons?|tr|stars?|btu)\b', ' ', remainder)
        words = re.findall(r'\w+', remainder)
        symptom = re.search(
            r'cool|leak|noise|noisy|working|broken|smell|sparking|tripping|water|വെള്ളം|തണു|ശബ്ദ|vellam|thanu|പണി|खराब|पानी|ठंड',
            remainder)
        if words and (not ac_type or len(words) >= 2 or symptom):
            data['problem_description'] = message

    @classmethod
    def collect_schedule(cls, session, message):
        """Remember a partial date/time and ask for the missing part only."""
        data = session.data
        lang = session.conversation.customer.preferred_language
        if message.strip().lower() in cls.DATE_CHANGE_REQUESTS:
            data.pop('preferred_date', None)
            data.pop('preferred_time_slot', None)
            session.data = data
            session.save(update_fields=['data', 'updated_at'])
            return say('choose_date', lang)
        requested_date = cls.parse_schedule_date(message)
        parsed_time = cls.parse_schedule_time(message)
        if cls.has_schedule_date(message) and not requested_date:
            return say('invalid_date', lang)
        if data.get('preferred_date') and not cls.parse_schedule_date(data['preferred_date']):
            data.pop('preferred_date', None)
            data.pop('preferred_time_slot', None)
        if requested_date:
            if data.get('preferred_date'):
                data.pop('preferred_time_slot', None)
            data['preferred_date'] = requested_date.isoformat()
        if parsed_time:
            data['preferred_time_slot'] = message[:100] if requested_date else parsed_time[0]

        error = None
        if data.get('preferred_date') and data.get('preferred_time_slot'):
            if cls.parse_schedule(f"{data['preferred_date']} {data['preferred_time_slot']}"):
                session.step = BookingStep.REVIEW
                data.pop('return_to_review', None)
            else:
                data.pop('preferred_time_slot', None)
                error = say('invalid_time', lang).format(date=cls.display_date(data['preferred_date'], lang))
        session.data = data
        session.save()
        if error:
            return error
        if not requested_date and not parsed_time and not data.get('preferred_date') and not data.get('preferred_time_slot'):
            return say('invalid_date', lang)
        return cls.review(session) if session.step == BookingStep.REVIEW else cls.prompt(session)

    @classmethod
    def review(cls, session):
        data = session.data
        service = Service.objects.filter(pk=data.get('service_id'), is_active=True).first() if data.get('service_id') else None
        from apps.business.models import Product
        product = Product.objects.filter(pk=data.get('product_id'), is_active=True).first() if data.get('product_id') else None
        lang = session.conversation.customer.preferred_language
        from apps.business.domain import is_it_business
        if is_it_business():
            req_type = "Product Demo" if product else "Project Consultation"
            target_name = product.name if product else (service.name if service else data.get('service_name', 'General IT Consultation'))
            recipient = f"{say('name_label', lang)}: {data.get('name', '')}\n{say('recipient_label', lang)}: {data['recipient_name']}\n" if data.get('recipient_name') else f"{say('name_label', lang)}: {data.get('name', '')}\n"
            pricing_text = product.formatted_pricing if product else (say('inspection_quote', lang) if service and service.price_type == PriceType.INSPECTION_REQUIRED else (service.formatted_price if service else 'Quote after review'))
            return (
                f"*Please review your {req_type} request before submitting:*\n\n"
                f"{recipient}"
                f"• Request: *{target_name}* ({req_type})\n"
                f"• {say('details_label', lang)}: {data.get('ac_type', target_name)}\n"
                f"• {say('issue_label', lang)}: {data.get('problem_description', '')}\n"
                f"• {say('address_label', lang)}: {data.get('service_address', '')}\n"
                f"• {say('schedule_label', lang)}: {data.get('preferred_date', '')} · {data.get('preferred_time_slot', '')}\n"
                f"• Pricing: {pricing_text}\n\n"
                f"The requested time slot is pending confirmation by our team. Reply *Confirm* to submit, or let me know if you want to edit any detail."
            )
        recipient = f"{say('recipient_label', lang)}: {data['recipient_name']}\n" if data.get('recipient_name') else ''
        return (f"{say('review', lang)}\n\n"
                f"{say('name_label', lang)}: {data.get('name', '')}\n"
                f"{recipient}"
                f"{say('service_label', lang)}: *{data.get('service_name', 'AC service')}*\n"
                f"{say('details_label', lang)}: {data.get('ac_type', '')}\n"
                f"{say('issue_label', lang)}: {data.get('problem_description', '')}\n"
                f"{say('address_label', lang)}: {data.get('service_address', '')}\n"
                f"{say('schedule_label', lang)}: {data.get('preferred_date', '')} · {data.get('preferred_time_slot', '')}\n"
                f"{say('inspection_quote', lang) if service and service.price_type == PriceType.INSPECTION_REQUIRED else (service.formatted_price if service else '')}\n\n"
                f"{'The team will confirm availability after you submit.' if lang == 'en' else say('schedule', lang)}")

    @classmethod
    @transaction.atomic
    def process_booking_step(cls, conversation, user_message):
        msg = user_message.strip()
        lower = msg.lower()
        lang = conversation.customer.preferred_language
        if lower in ('cancel', 'cancel booking', 'stop', 'quit', 'exit'):
            return cls.cancel_booking_session(conversation), None
        session = BookingSession.objects.select_for_update().filter(conversation=conversation).first()
        if not session or session.step in [BookingStep.COMPLETED, BookingStep.CANCELLED]:
            return cls.start_booking_session(conversation)
        data = session.data
        if lower == 'booking_edit' and session.step == BookingStep.REVIEW:
            session.step = BookingStep.EDIT
            session.save()
            return cls.prompt(session), None
        if lower.startswith('booking_edit_'):
            target = lower.removeprefix('booking_edit_').upper()
            if target in cls.STEPS[:-1]:
                session.step = target
                data['return_to_review'] = True
                if target == BookingStep.SCHEDULE:
                    data.pop('preferred_time_slot', None)
                session.save()
            return cls.prompt(session), None
        if session.step == BookingStep.REVIEW:
            if lower not in ('booking_submit', 'submit', 'confirm', 'yes', 'shari', 'athe', 'ha', 'confirm request'):
                return cls.review(session), None
            if data.get('booking_for_other') and not data.get('recipient_name'):
                data['recipient_resume_step'] = BookingStep.REVIEW
                session.step = BookingStep.NAME
                session.save()
                return cls.prompt(session), None
            from apps.business.models import Product
            product = Product.objects.filter(pk=data.get('product_id'), is_active=True).first() if data.get('product_id') else None
            service = Service.objects.filter(pk=data.get('service_id'), is_active=True).first() if data.get('service_id') else None
            try:
                selected_date = date.fromisoformat(data['preferred_date'])
            except (KeyError, ValueError):
                selected_date = None
            if not selected_date or not cls.parse_schedule(f"{selected_date.isoformat()} {data.get('preferred_time_slot', '')}"):
                session.step = BookingStep.SCHEDULE
                data.pop('preferred_time_slot', None)
                if not selected_date or not cls.parse_schedule_date(selected_date.isoformat()):
                    data.pop('preferred_date', None)
                session.data = data
                session.save()
                return say('invalid_date', lang) + '\n\n' + cls.prompt(session), None
            if not service and not product:
                session.step = BookingStep.SERVICE
                session.save()
                return cls.prompt(session), None

            from apps.business.domain import is_it_business
            from apps.bookings.models import RequestType
            req_type = RequestType.PRODUCT_DEMO if product else (RequestType.CONSULTATION if is_it_business() else RequestType.SERVICE_REQUEST)
            target_name = product.name if product else (service.name if service else 'General Consultation')

            booking = Booking.objects.create(
                customer=conversation.customer,
                conversation=conversation,
                request_type=req_type,
                product=product,
                service=service,
                recipient_name=data.get('recipient_name', ''),
                organization=data.get('organization', data.get('service_address', '')),
                contact_email=data.get('contact_email', ''),
                requirements_summary=data.get('problem_description', ''),
                staff_summary=f"{req_type.label} for {target_name}. Contact: {data.get('service_address')}. Details: {data.get('problem_description')}",
                language=lang,
                service_address=data['service_address'],
                ac_type=data.get('ac_type', f"{target_name} Demo" if product else "Project consultation"),
                problem_description=data.get('problem_description', ''),
                preferred_date=selected_date,
                preferred_time_slot=data['preferred_time_slot'],
                status=BookingStatus.PENDING
            )
            session.step = BookingStep.COMPLETED
            session.save()
            if is_it_business():
                return f"*Request #{booking.id} Submitted*\nStatus: Pending Team Confirmation\n\n{target_name} ({req_type.label})\n{selected_date} · {booking.preferred_time_slot}\n{booking.service_address}\n\nOur team will review your requested time and contact you to confirm.", booking.id
            return f"*Booking #{booking.id}*\n{say('submitted', lang)}\n\n{service.name}\n{selected_date} · {booking.preferred_time_slot}\n{booking.service_address}", booking.id

        if session.step == BookingStep.EDIT:
            return cls.prompt(session), None
        if session.step == BookingStep.NAME:
            name = (re.sub(r'^(?:his|her|their|my)\s+name\s+is\s+', '', msg, flags=re.I)
                    if data.get('booking_for_other') else msg)
            if not 2 <= len(name) <= 100 or not all(c.isalpha() or c.isspace() or c in ".'-" for c in name):
                return say('invalid', lang) + '\n' + cls.prompt(session), None
            if data.get('booking_for_other'):
                data['recipient_name'] = name.title()
                default_step = BookingStep.AC_DETAILS if data.get('service_id') else BookingStep.SERVICE
                session.step = data.pop('recipient_resume_step', default_step)
                if session.step == BookingStep.NAME:
                    session.step = default_step
            else:
                data['name'] = msg.title()
                conversation.customer.name = data['name']
                conversation.customer.save(update_fields=['name'])
                session.step = BookingStep.AC_DETAILS if data.get('service_id') else BookingStep.SERVICE
        elif session.step == BookingStep.SERVICE:
            service = IntentService.find_matching_service(lower)
            if not service:
                from apps.business.domain import is_it_business
                from apps.chatbot.intent_service import IntentService as IS
                prod = IS.find_matching_product(lower) if is_it_business() else None
                if prod:
                    data.update(
                        product_id=prod.id,
                        product_name=prod.name,
                        request_type='product_demo',
                        service_name=f"{prod.name} Demo",
                        ac_type=f"{prod.name} Demo",
                    )
                    data.pop('service_id', None)
                    session.step = BookingStep.AC_DETAILS
                else:
                    return cls.prompt(session), None
            else:
                ac_type_val = 'Project consultation' if is_it_business() else service.name
                data.update(service_id=service.id, service_name=service.name, request_type='consultation', ac_type=ac_type_val)
                data.pop('product_id', None)
                data.pop('product_name', None)
                conversation.service = service
                conversation.save(update_fields=['service'])
                session.step = BookingStep.AC_DETAILS
        elif session.step == BookingStep.AC_DETAILS:
            if len(msg) < 2 or len(msg) > 1500 or not any(c.isalpha() for c in msg):
                return say('invalid', lang) + '\n' + cls.prompt(session), None
            cls.collect_ac_details(data, msg)
            if data.get('ac_type') and data.get('problem_description'):
                session.step = BookingStep.ADDRESS
        elif session.step == BookingStep.ADDRESS:
            from apps.business.domain import is_it_business
            minimum = len(msg) >= 3 if is_it_business() else len(msg) >= 12 and len(msg.split()) >= 3
            if not minimum or len(msg) > 1500 or '?' in msg:
                return say('invalid', lang) + '\n' + cls.prompt(session), None
            data['service_address'] = msg
            session.step = BookingStep.SCHEDULE
        elif session.step == BookingStep.SCHEDULE:
            return cls.collect_schedule(session, msg), None
        if (data.get('return_to_review') and session.step != BookingStep.AC_DETAILS
                and all(data.get(key) for key in ['name', 'service_id', 'ac_type', 'problem_description', 'service_address', 'preferred_date', 'preferred_time_slot'])):
            data.pop('return_to_review')
            session.step = BookingStep.REVIEW
        session.data = data
        from .booking_fields import next_missing_step
        session.step = next_missing_step(data)
        session.save()
        return (cls.review(session) if session.step == BookingStep.REVIEW else cls.prompt(session)), None
