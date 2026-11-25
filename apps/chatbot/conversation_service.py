import logging
import re
from typing import Dict, Any, Optional
from django.utils import timezone
from django.db import transaction
from .language import detect_language, say, choice
from .models import (
    Customer,
    Conversation,
    Message,
    ChannelChoice,
    ConversationStatus,
    MessageDirection,
    SenderType,
    ProcessingStatus
)
from .intent_service import IntentService, IntentType
from .handlers import booking, booking_followup, services, text
from .handlers.attachments import generate_reply as attachment_reply
from .reply import ChatReply
from .memory import ConversationMemory
from .processing import customer_turn, ConversationBusyError
from .turn_preparation import prepare_turn
from apps.services.models import Service
from apps.services.services import get_services_formatted_text
from apps.bookings.models import Booking, BookingSession, BookingStatus
from apps.bookings.booking_service import BookingService

logger = logging.getLogger(__name__)

class ConversationService:
    """
    Coordinate message persistence, routing, and shared conversation controls.
    Response generation lives in handlers; booking validation stays in apps.bookings.
    """
    @classmethod
    def extract_name_from_message(cls, text: str) -> Optional[str]:
        """
        Extract customer name when they introduce themselves in chat.
        E.g.
        - 'Hello i am ashfaque' -> 'Ashfaque'
        - 'Hi my name is Ashfaque Khan' -> 'Ashfaque Khan'
        - 'I am Ashfaque' -> 'Ashfaque'
        - 'I'm Ashfaque' -> 'Ashfaque'
        - 'This is Ashfaque' -> 'Ashfaque'
        - 'Myself Ashfaque' -> 'Ashfaque'
        - 'Ashfaque here' -> 'Ashfaque'
        """
        cleaned = text.strip()

        # 1. 'Ashfaque here'
        m_here = re.search(r'\b([A-Za-z]{2,20})\s+here\b', cleaned, re.IGNORECASE)
        if m_here:
            cand = m_here.group(1).strip()
            if cand.lower() not in {"i", "we", "he", "she", "it", "they", "someone", "technician", "customer"}:
                return cand.title()

        # 2. 'i am ...', 'my name is ...', 'i'm ...', 'this is ...', 'myself ...'
        patterns = [
            r"(?:i\s*am|i\'m|im|my\s*name\s*is|this\s*is|myself)\s+([A-Za-z]{2,20}(?:\s+[A-Za-z]{2,20})?)",
        ]
        for pat in patterns:
            m = re.search(pat, cleaned, re.IGNORECASE)
            if m:
                cand = m.group(1).strip()
                first_word = cand.split()[0].lower()
                excluded = {
                    "interested", "looking", "facing", "having", "calling", "asking",
                    "here", "waiting", "ready", "fine", "good", "new", "from", "at",
                    "facing", "getting", "a", "an", "the", "not", "just", "trying",
                    "in", "on", "with", "for", "technician", "customer", "broken", "angry",
                    "unhappy", "upset", "unable", "confused", "still", "without", "working", "ac"
                }
                if first_word not in excluded:
                    return cand.title()

        return None


    @classmethod
    def generate_handoff_summary(cls, conversation: Conversation, reason: str = "Customer requested human support") -> str:
        """
        Generate a structured handoff note so human technicians and staff
        have immediate context without asking the customer to repeat.
        """
        from apps.business.domain import is_it_business
        cust = conversation.customer
        last_inbounds = Message.objects.filter(
            conversation=conversation,
            direction=MessageDirection.INBOUND
        ).order_by('-created_at')[:4]
        recent_queries = " -> ".join([f'"{m.message_text}"' for m in reversed(last_inbounds)])

        session = BookingSession.objects.filter(conversation=conversation).first()
        session_data = session.data if session else {}

        if is_it_business():
            target = session_data.get('product_name') or (conversation.service.name if conversation.service else "IT Agency / Product Enquiry")
            req_type = session_data.get('request_type', 'Enquiry / Consultation')
            draft_details = []
            if session_data.get('organization'):
                draft_details.append(f"• Organization: {session_data['organization']}")
            if session_data.get('service_address'):
                draft_details.append(f"• Contact/Location: {session_data['service_address']}")
            if session_data.get('problem_description'):
                draft_details.append(f"• Business Context / Requirements: {session_data['problem_description']}")
            if session_data.get('preferred_date') or session_data.get('preferred_time_slot'):
                draft_details.append(f"• Requested Timing: {session_data.get('preferred_date', '')} {session_data.get('preferred_time_slot', '')}".strip())

            draft_block = "\n".join(draft_details)
            if draft_block:
                draft_block = "\n" + draft_block

            return (
                f"📋 NEORIZ SOLUTIONS HANDOFF SUMMARY\n"
                f"• Customer: {cust.name or 'Unknown'} ({cust.phone_number})\n"
                f"• Escalation Reason: {reason}\n"
                f"• Area of Interest: {target} ({req_type})\n"
                f"• Customer Goal / Recent Inquiries: {recent_queries or 'None'}"
                f"{draft_block}\n"
                f"• Unresolved / Action Required: Staff review and direct follow-up on verified details/quote."
            )

        svc_name = conversation.service.name if conversation.service else "General AC Support"
        recipient = session.data.get('recipient_name') if session else None
        recipient_line = f'• Service recipient: {recipient} (arranged by customer)\n' if recipient else ''
        draft_lines = ''
        if session and BookingService.is_in_active_booking(conversation):
            draft_lines = '\n'.join(f'• {label}: {session.data[key]}' for key, label in (
                ('ac_type', 'AC type'), ('problem_description', 'Issue'), ('service_address', 'Visit address'),
                ('preferred_date', 'Preferred date'), ('preferred_time_slot', 'Time preference')) if session.data.get(key))
            draft_lines += '\n• Next booking question: ' + BookingService.prompt(session)

        return (
            f"📋 HANDOFF SUMMARY NOTE\n"
            f"• Customer: {cust.name or 'Unknown'} ({cust.phone_number})\n"
            f"• Escalation Reason: {reason}\n"
            f"• Scoped Service: {svc_name}\n"
            f"{recipient_line}"
            f"• Recent Inquiries: {recent_queries or 'None'}\n{draft_lines}"
        )


    @classmethod
    def process_message(
        cls, phone_number, message_text, channel=ChannelChoice.SIMULATED,
        external_message_id=None, service_id=None, customer_name=None, conversation_id=None,
        external_timestamp=None, image_media_id=None, flow_response=None, tenant=None,
        external_media=None
    ):
        from apps.tenants.context import get_current_tenant
        if tenant is None:
            tenant = get_current_tenant()
        if tenant is None:
            # Try resolving tenant from an existing customer with this phone number
            existing_cust = Customer.objects.filter(phone_number=phone_number.strip()).select_related('tenant').first()
            if existing_cust and existing_cust.tenant:
                tenant = existing_cust.tenant

        if tenant and not tenant.is_active:
            return {
                'conversation_id': None,
                'reply': 'This business service is currently inactive. Please contact support.',
                'handover_required': False,
                'booking_id': None,
                'status': 'suspended'
            }

        customer, _ = Customer.objects.get_or_create(tenant=tenant, phone_number=phone_number.strip())
        # A lease serializes turns across processes without blocking other DB writers.
        with customer_turn(customer) as token:
            customer.refresh_from_db()
            existing = Message.objects.filter(external_message_id=external_message_id).first() if external_message_id else None
            if existing:
                if (existing.conversation.customer_id != customer.pk or existing.conversation.channel != channel
                        or existing.message_text != message_text.strip()):
                    raise ValueError('Message identifier does not match this request.')
                if existing.response_data:
                    return existing.response_data
            unfinished = Message.objects.filter(
                conversation__customer=customer, direction=MessageDirection.INBOUND,
                processing_status=ProcessingStatus.PROCESSING, response_data={},
                external_message_id__isnull=False).exclude(external_message_id='').order_by('pk').first()
            if unfinished and (not existing or unfinished.pk != existing.pk):
                raise ConversationBusyError('An earlier message must finish before the next turn.')
            if (channel == ChannelChoice.WHATSAPP and external_timestamp and customer.last_whatsapp_event_at
                    and external_timestamp < customer.last_whatsapp_event_at and not existing):
                conversation = customer.conversations.filter(channel=channel).exclude(status=ConversationStatus.CLOSED).first()
                return {'conversation_id': conversation.pk if conversation else None, 'reply': '',
                        'handover_required': bool(conversation and conversation.status == ConversationStatus.HUMAN_HANDOVER),
                        'booking_id': None, 'ignored_reason': 'out_of_order'}
            return cls._process_message(phone_number, message_text, channel, external_message_id,
                service_id, customer_name, conversation_id, image_media_id, flow_response,
                processing_token=token, external_timestamp=external_timestamp, tenant=tenant,
                external_media=external_media)

    @classmethod
    def _process_message(
        cls,
        phone_number: str,
        message_text: str,
        channel: str = ChannelChoice.SIMULATED,
        external_message_id: Optional[str] = None,
        service_id: Optional[int] = None,
        customer_name: Optional[str] = None,
        conversation_id: Optional[int] = None,
        image_media_id: Optional[str] = None,
        flow_response=None, processing_token=None, external_timestamp=None,
        tenant=None, external_media=None
    ) -> Dict[str, Any]:
        """
        Process incoming customer message and generate an accurate, grounded reply.
        Optionally scoped to a specific tagged Service and its contact number.
        """
        cleaned_phone = phone_number.strip()
        cleaned_text = message_text.strip()

        # 1. Message deduplication for external channels (e.g. Meta WhatsApp)
        existing = None
        if external_message_id:
            existing = Message.objects.filter(external_message_id=external_message_id).first()
            if existing:
                if (existing.conversation.customer.phone_number != cleaned_phone
                        or existing.conversation.channel != channel):
                    raise ValueError('Message identifier belongs to another conversation.')
                if existing.response_data:
                    return existing.response_data
                if existing.message_text != cleaned_text:
                    raise ValueError('Message content changed for an existing identifier.')
                conversation_id = existing.conversation_id

        # 2. Get or create Customer
        customer, created = Customer.objects.get_or_create(
            tenant=tenant,
            phone_number=cleaned_phone,
            defaults={
                'name': customer_name or '',
                'source': 'WHATSAPP_INBOUND' if channel == ChannelChoice.WHATSAPP else 'WEBSITE',
                'last_contacted_at': timezone.now()
            }
        )
        if flow_response is not None and channel == ChannelChoice.WHATSAPP:
            from apps.whatsapp.booking_flows import response_conversation_id
            conversation_id = response_conversation_id(customer, flow_response)
        update_fields = []
        if not created:
            customer.last_contacted_at = timezone.now()
            update_fields.append('last_contacted_at')
            if customer_name and not customer.name:
                customer.name = customer_name
                update_fields.append('name')

        language = detect_language(cleaned_text, customer.preferred_language)
        if language != customer.preferred_language:
            customer.preferred_language = language
            update_fields.append('preferred_language')

        if update_fields:
            customer.save(update_fields=update_fields)
        # Look up optional service context
        service = None
        if service_id:
            service = Service.objects.filter(id=service_id, is_active=True).first()

        # Share the parent lock with outbound new-chat resolution.
        with transaction.atomic():
            Customer.objects.select_for_update().get(pk=customer.pk)
            # 3. Get or create active Conversation (scoped to service if provided)
            conv_query = Conversation.objects.filter(
                tenant=tenant,
                customer=customer,
                channel=channel
            ).exclude(status=ConversationStatus.CLOSED)
            if conversation_id:
                conv_query = conv_query.filter(pk=conversation_id)
            elif service:
                conv_query = conv_query.filter(service=service)

            # A retry belongs to its original conversation even if staff closed it.
            conversation = existing.conversation if existing else conv_query.order_by('-updated_at').first()

            if not conversation:
                conversation = Conversation.objects.create(
                    tenant=tenant,
                    customer=customer,
                    service=service,
                    channel=channel,
                    status=ConversationStatus.BOT_ACTIVE
                )
            elif service and conversation.service != service:
                conversation.service = service
                conversation.save(update_fields=['service'])

        # A name supplied for a service recipient must never rename the requester.
        draft = BookingSession.objects.filter(conversation=conversation).first()
        for_other = (BookingService.recipient_correction(cleaned_text) == 'other'
                     or bool(draft and draft.data.get('booking_for_other')))
        extracted_name = None if for_other else cls.extract_name_from_message(cleaned_text)
        if extracted_name:
            customer.name = extracted_name
            customer.save(update_fields=['name'])
        elif not customer.name and customer_name:
            customer.name = customer_name.strip().title()
            customer.save(update_fields=['name'])

        # 4. Persist Inbound Message
        media_fields = {}
        if isinstance(external_media, dict) and external_media.get('media_type'):
            media_fields = {
                'media_type': str(external_media.get('media_type') or '')[:20],
                'media_name': str(external_media.get('media_name') or '')[:200],
                'media_mime': str(external_media.get('media_mime') or '')[:100],
            }
        if existing:
            inbound = existing
        else:
            inbound = Message.objects.create(
                conversation=conversation,
                direction=MessageDirection.INBOUND,
                sender_type=SenderType.CUSTOMER,
                message_text=cleaned_text,
                external_message_id=external_message_id,
                processing_status=ProcessingStatus.PROCESSING,
                **media_fields,
            )
            from django.db.models import F as _F
            Conversation.objects.filter(pk=conversation.pk).update(
                unread_count=_F('unread_count') + 1,
                last_inbound_at=timezone.now(),
                followup_alert_sent_at=None,
            )

        # Route the message, then add shared controls and persist the exact response.
        if (channel == ChannelChoice.WHATSAPP and external_message_id
                and (conversation.status != ConversationStatus.HUMAN_HANDOVER
                     or cleaned_text.lower() in ('resume bot', 'resume assistant'))):
            from apps.whatsapp.whatsapp_client import WhatsAppClient
            WhatsAppClient.send_typing_indicator(external_message_id)
        intent, matched_entity = IntentService.detect_intent(cleaned_text)
        if (conversation.status == ConversationStatus.BOT_ACTIVE
                and intent not in (IntentType.HANDOVER, IntentType.BOOKING_STATUS)
                and flow_response is None
                and not booking_followup.is_approval_question(cleaned_text)):
            ConversationMemory.prepare(conversation, inbound.pk, processing_token=processing_token)
        if (conversation.service and not matched_entity and intent == IntentType.SERVICE_LIST
                and re.search(r'\b(price|cost|how much|rate)\b', cleaned_text, re.I)
                and not re.search(r'\b(all|services|packages)\b', cleaned_text, re.I)):
            intent, matched_entity = IntentType.SERVICE_PRICE, conversation.service
        prepared = prepare_turn(cleaned_text, conversation, intent, matched_entity, image_media_id, flow_response)
        return cls._finalize_message(conversation, inbound, intent, matched_entity, prepared,
                                     flow_response, processing_token, external_timestamp)

    @classmethod
    @transaction.atomic
    def _finalize_message(cls, conversation, inbound, intent, matched_entity, prepared,
                          flow_response, processing_token, external_timestamp):
        """Apply business changes and the exact reply together; no provider calls here."""
        customer = Customer.objects.select_for_update().get(pk=conversation.customer_id)
        if customer.processing_token != processing_token or customer.processing_until <= timezone.now():
            raise ConversationBusyError('Message processing expired; retry this message.')
        # Staff may have taken over while the provider was responding.
        conversation.refresh_from_db()
        conversation.customer = customer
        inbound.refresh_from_db()
        if inbound.response_data:
            return inbound.response_data
        cleaned_text = inbound.message_text
        channel = conversation.channel
        reply = cls._route_message(cleaned_text, conversation, intent, matched_entity, prepared, flow_response)
        reply_text = reply.text
        booking_id = reply.booking_id
        handover_required = reply.handover_required

        options, interactive = cls._build_controls(conversation, intent, matched_entity, reply, cleaned_text)
        flow = None
        if (channel == ChannelChoice.WHATSAPP and not handover_required and reply_text and reply.offer_booking_form):
            from apps.whatsapp.booking_flows import build_offer
            flow = build_offer(conversation)
            if flow:
                reply_text += '\n\nOpen the form below, or type the details here. You can type cancel or talk to team at any time.'
                options = None
                interactive = {'type': 'flow'}

        outbound = None
        if reply_text:
            outbound = Message.objects.create(conversation=conversation, direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.BOT, message_text=reply_text, processing_status=ProcessingStatus.PROCESSED)

        # Update conversation activity and unresolved-query tracking.
        conversation.last_message_at = timezone.now()
        conversation.unresolved_count = min(conversation.unresolved_count + 1, 2) if getattr(conversation, '_unresolved', False) else 0
        conversation.save(update_fields=['last_message_at', 'unresolved_count', 'updated_at'])

        result = {
            "conversation_id": conversation.id,
            "reply": reply_text,
            "handover_required": handover_required,
            "booking_id": booking_id,
            "interactive": interactive,
            "flow": flow,
            "options": options,
            "booking_progress": BookingService.progress(conversation),
            "outbound_message_id": outbound.id if outbound else None,
            "booking_context": reply.booking_context if reply.booking_context is not None else ([booking_id] if booking_id else None),
            "bookings": [{'id': booking.pk, 'service': booking.service.name if booking.service else 'Service visit',
                          'recipient_name': booking.recipient_name,
                          'date': str(booking.preferred_date) if booking.preferred_date else 'Scheduling pending',
                          'time': booking.preferred_time_slot, 'status': booking.status, 'status_label': booking.get_status_display()}
                         for booking in customer.bookings.select_related('service').order_by('-created_at')[:5]],
        }
        inbound.response_data = result
        inbound.processing_status = ProcessingStatus.PROCESSED
        inbound.save(update_fields=['response_data', 'processing_status'])
        if outbound:
            out_data = dict(result)
            try:
                from apps.business.models import BusinessProfile
                from apps.crm.business_hours import is_within_business_hours
                bp = BusinessProfile.get_active(tenant=conversation.tenant)
                if bp and bp.after_hours_auto_reply and reply_text == bp.after_hours_auto_reply.strip() and not is_within_business_hours(bp):
                    out_data['after_hours_auto_reply'] = True
            except Exception:
                pass
            outbound.response_data = out_data
            outbound.save(update_fields=['response_data'])
        if channel == ChannelChoice.WHATSAPP and external_timestamp:
            customer.last_whatsapp_event_at = external_timestamp
            customer.save(update_fields=['last_whatsapp_event_at'])
        return result

    @classmethod
    def _route_message(cls, message, conversation, intent, entity, prepared, flow_response=None):
        """Route in priority order: handover, media, commands, booking, services, text."""
        language = conversation.customer.preferred_language
        if conversation.status == ConversationStatus.CLOSED:
            return ChatReply('')

        # Business hours / away auto-reply & first-inbound greeting hooks (opt-in per tenant BusinessProfile)
        try:
            from apps.business.models import BusinessProfile
            from apps.crm.business_hours import is_within_business_hours
            b_profile = BusinessProfile.get_active(tenant=conversation.tenant)
        except Exception:
            b_profile = None

        if b_profile and (b_profile.after_hours_auto_reply or '').strip() and not is_within_business_hours(b_profile):
            from datetime import timedelta
            recently_sent = Message.objects.filter(
                conversation=conversation,
                sender_type=SenderType.BOT,
                response_data__after_hours_auto_reply=True,
                created_at__gte=timezone.now() - timedelta(hours=6),
            ).exists()
            if not recently_sent:
                try:
                    from apps.crm.automation_engine import record_business_event
                    if conversation.tenant_id:
                        record_business_event(
                            tenant=conversation.tenant,
                            event_type='conversation.after_hours',
                            entity_type='conversation',
                            entity_id=conversation.pk,
                            payload={'conversation_id': conversation.pk, 'customer_id': conversation.customer_id},
                        )
                except Exception:
                    pass
                return ChatReply(b_profile.after_hours_auto_reply.strip())

        if conversation.status == ConversationStatus.HUMAN_HANDOVER:
            if message.lower() not in ('resume bot', 'resume assistant'):
                return ChatReply('', handover_required=True)
            conversation.status = ConversationStatus.BOT_ACTIVE
            conversation.assigned_staff = None
            conversation.picked_up_at = None
            conversation.unresolved_count = 0
            conversation.save(update_fields=['status', 'unresolved_count', 'assigned_staff', 'picked_up_at'])
            if BookingService.is_in_active_booking(conversation):
                greeting, options = booking.welcome_back(conversation)
                return ChatReply(greeting, options=options)
            return ChatReply(say('greeting', language))

        if flow_response is not None:
            from apps.whatsapp.booking_flows import apply_response
            return ChatReply(apply_response(conversation, flow_response), offer_booking_form=True)

        if message.startswith('[attachment:image]'):
            reply_text = prepared.image_reply
            if BookingService.is_in_active_booking(conversation):
                session = BookingSession.objects.get(conversation=conversation)
                reply_text += '\n\n' + BookingService.prompt(session)
            return ChatReply(reply_text)

        if intent == IntentType.HANDOVER:
            cls._start_handover(conversation, 'Customer explicitly requested agent')
            return ChatReply(say('team', language), handover_required=True)

        if message.lower() in ('main menu', 'menu', 'start fresh', 'booking_start_fresh'):
            if BookingService.is_in_active_booking(conversation):
                BookingService.cancel_booking_session(conversation)
            conversation.service = None
            conversation.save(update_fields=['service'])
            return ChatReply(say('greeting', language))

        if re.match(r'^(cancel_booking|confirm_cancel|reschedule_booking)_\d+$', message):
            return cls._handle_booking_action(message, conversation)
        if message.startswith('[attachment:'):
            return ChatReply(attachment_reply(message))
        if intent == IntentType.BOOKING_STATUS:
            page, _, _, _ = text.booking_history_page(conversation.customer, message)
            return ChatReply(text.generate_deterministic_reply(
                intent, entity, get_services_formatted_text(), conversation, message),
                booking_context=[item.pk for item in page])
        followup = booking_followup.generate_reply(message, conversation)
        if followup:
            return followup
        if intent == IntentType.IDENTITY:
            reply_text = text.generate_deterministic_reply(intent, None, get_services_formatted_text(), conversation, message)
            if BookingService.is_in_active_booking(conversation):
                reply_text += '\n\n' + BookingService.prompt(BookingSession.objects.get(conversation=conversation))
            return ChatReply(reply_text)
        if BookingService.is_in_active_booking(conversation):
            return booking.handle_active_booking(message, conversation, intent, entity, prepared.booking_interpretation)
        if intent == IntentType.BOOKING_START:
            for_other = BookingService.recipient_correction(message) == 'other'
            reply_text, booking_id = BookingService.start_booking_session(
                conversation, matched_service=entity or (None if for_other else conversation.service), for_other=for_other)
            if not message.startswith('book_service_'):
                interpreted = booking.interpret_update(message, conversation, prepared.booking_interpretation, initial=True)
                if interpreted:
                    return interpreted
            return ChatReply(reply_text, booking_id=booking_id)
        if message.startswith('check_price_'):
            return services.show_price(message, conversation)
        if message.startswith(('service_', 'select_service_')) or intent == IntentType.SERVICE_SELECT:
            return services.select_service(message, conversation, entity, prepared.text_reply)
        if intent == IntentType.SERVICE_LIST or message.lower() in ('view_services', 'all_services', 'options'):
            return services.list_services(conversation)
        if intent == IntentType.UNKNOWN and conversation.unresolved_count >= 1:
            cls._start_handover(conversation, 'Unresolved query after 2 bot attempts')
            return ChatReply(
                'I want to make sure you get the exact right assistance. '
                'Your conversation has been handed over to our human support team. '
                'A member of our service team will review your request.',
                handover_required=True)
        return ChatReply(prepared.text_reply)

    @classmethod
    def _start_handover(cls, conversation, reason):
        if conversation.status != ConversationStatus.HUMAN_HANDOVER:
            conversation.assigned_staff = None
            conversation.picked_up_at = None
        conversation.status = ConversationStatus.HUMAN_HANDOVER
        conversation.handoff_summary = cls.generate_handoff_summary(conversation, reason=reason)
        if conversation.assigned_staff is None and conversation.tenant_id:
            try:
                from apps.business.models import BusinessProfile
                from apps.crm.assignment_service import assign_lead_round_robin
                b_profile = BusinessProfile.get_active(tenant=conversation.tenant)
                if b_profile and b_profile.auto_assign_inbound:
                    assigned = assign_lead_round_robin(conversation.tenant, contact=conversation.customer)
                    if assigned:
                        conversation.assigned_staff = assigned
                        conversation.picked_up_at = timezone.now()
            except Exception:
                pass
        conversation.save(update_fields=['status', 'handoff_summary', 'assigned_staff', 'picked_up_at'])
        logger.info('Handover triggered:\n%s', conversation.handoff_summary)

    @classmethod
    def _handle_booking_action(cls, message, conversation):
        action, raw_id = message.rsplit('_', 1)
        selected_booking = Booking.objects.filter(pk=int(raw_id), customer=conversation.customer).first()
        if not selected_booking or selected_booking.status not in (BookingStatus.PENDING, BookingStatus.CONFIRMED):
            return ChatReply('That booking is unavailable for changes. Please contact our team.')
        language = conversation.customer.preferred_language
        if action == 'cancel_booking':
            return ChatReply(
                f'Cancel booking #{selected_booking.id}? This will cancel the requested visit.',
                options=[{'id': f'confirm_cancel_{selected_booking.id}', 'title': 'Cancel this booking'},
                         choice('booking status', 'status', language)])
        if action == 'confirm_cancel':
            from apps.bookings.notifications import change_booking_status
            change_booking_status(selected_booking, BookingStatus.CANCELLED)
            return ChatReply(f'Booking #{selected_booking.id} has been cancelled.')
        cls._start_handover(conversation, f'Reschedule booking #{selected_booking.id}')
        return ChatReply(
            f'Our team can arrange a new time for booking #{selected_booking.id}. ' + say('team', language),
            handover_required=True)

    @staticmethod
    def _build_controls(conversation, intent, matched_entity, reply, message=''):
        """Attach the same contextual buttons to every channel."""
        customer = conversation.customer
        language = customer.preferred_language
        options = reply.options
        booking_id = reply.booking_id
        handover_required = reply.handover_required
        interactive = None
        active_booking = BookingService.is_in_active_booking(conversation)
        if active_booking and not handover_required and intent != IntentType.BOOKING_STATUS:
            options = options or BookingService.options(conversation)
        elif not options and not handover_required:
            if intent == IntentType.BOOKING_STATUS:
                options = []
                page, total, offset, scope = text.booking_history_page(customer, message)
                for booking in [item for item in page if item.status in (BookingStatus.PENDING, BookingStatus.CONFIRMED)][:3]:
                    options.extend([{'id': f'cancel_booking_{booking.id}', 'title': f'Cancel #{booking.id}'},
                                    {'id': f'reschedule_booking_{booking.id}', 'title': f'Reschedule #{booking.id}'}])
                if scope == 'all':
                    if offset + len(page) < total:
                        options.append({'id': f'booking_history_{offset + 5}', 'title': 'Older bookings'})
                    if offset:
                        options.append({'id': f'booking_history_{max(0, offset - 5)}', 'title': 'Newer bookings'})
                if active_booking:
                    options.append(choice('booking_resume', 'continue_booking', language))
            elif booking_id:
                options = [choice('booking status', 'status', language), choice('view_services', 'view', language)]
            elif intent == IntentType.DISCOUNT_ENQUIRY and conversation.service:
                options = [choice(f'book_service_{conversation.service.pk}', 'book', language),
                           choice('view_services', 'view', language), choice('talk to agent', 'human', language)]
            elif intent == IntentType.SERVICE_PRICE and (matched_entity or conversation.service):
                svc = matched_entity or conversation.service
                options = [choice(f'book_service_{svc.id}', 'book', language), choice('view_services', 'view', language)]
            elif intent == IntentType.AC_PROBLEM:
                options = [choice('talk to agent', 'human', language)]
                if isinstance(matched_entity, Service):
                    options.insert(0, choice(f'book_service_{matched_entity.id}', 'book', language))
            else:
                options = [choice('view_services', 'view', language), choice('book', 'book', language), choice('talk to agent', 'human', language)]
        if options:
            # Translate fixed labels even when the selected branch built them in English.
            labels = {'Check Price': 'price', 'Book Appointment': 'book', 'View Services': 'view'}
            for option in options:
                if option['title'] in labels:
                    option['title'] = say(labels[option['title']], language)
            interactive = {'type': 'button' if len(options) <= 3 else 'list', 'options': options}

        return options, interactive

    # Kept as a public helper for callers that need verified customer booking context.
    get_customer_account_summary = staticmethod(text.get_customer_account_summary)
