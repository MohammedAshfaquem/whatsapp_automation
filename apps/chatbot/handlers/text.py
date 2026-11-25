"""Text replies: grounded business answers, knowledge retrieval, and AI fallback."""
import logging
import re
from typing import Optional
from django.utils import timezone

from apps.business.models import BusinessProfile
from apps.business.services import get_business_summary
from apps.services.models import Service, PriceType
from apps.services.services import get_services_formatted_text
from apps.knowledge_base.retrieval import retrieve_relevant_knowledge, format_retrieved_context
from ..gemini_service import GeminiChatService
from ..intent_service import IntentService, IntentType
from ..language import say
from ..models import Customer, Conversation, Message, MessageDirection
from ..prompts import build_rag_prompt
from ..memory import ConversationMemory

logger = logging.getLogger(__name__)


def booking_history_page(customer, message):
    """Read only this customer's records; keep longer histories in short chat pages."""
    query = customer.bookings.select_related('service').order_by('-created_at', '-pk')
    total = query.count()
    page = re.fullmatch(r'booking_history_(\d{1,6})', message.strip().lower())
    scope = 'all' if page or IntentService.is_booking_list_enquiry(message) else 'recent'
    if not page and re.search(r'\b(?:last|latest|most recent)\b', message, re.I) and not re.search(r'\ball\b', message, re.I):
        scope = 'latest'
    offset = min(int(page[1]), max(0, (total - 1) // 5 * 5)) if page else 0
    size = 5 if scope == 'all' else (1 if scope == 'latest' else 3)
    return list(query[offset:offset + size]), total, offset, scope


def get_customer_account_summary(customer: Customer) -> str:
    """
    Verified customer account tool (Principle 1 from LLM Support Bot System Design).
    Grounds responses strictly in the customer's authenticated WhatsApp session records,
    preventing prompt injection or unauthorized access to other customers' accounts.
    """
    bookings = customer.bookings.select_related('service').order_by('-created_at')[:3]
    if not bookings.exists():
        return "No previous or active bookings found for this customer phone number."

    lines = []
    for b in bookings:
        svc_name = b.service.name if b.service else "Custom AC Service"
        status_display = b.get_status_display()
        slot = b.preferred_time_slot or "Standard"
        date_str = str(b.preferred_date) if b.preferred_date else "Pending scheduling"
        lines.append(
            f"- Booking #{b.id}: {svc_name} | Status: {status_display} | Date: {date_str} ({slot})"
        )
        if b.recipient_name:
            lines.append(f'Service recipient: {b.recipient_name}; arranged by this customer.')
    return "\n".join(lines)


def build_contextual_prompt(customer_message, conversation, retrieved_context='No additional reference documents.', booking_context=None):
    tenant = getattr(conversation, 'tenant', None)
    services_context = get_services_formatted_text(tenant=tenant)
    if conversation.service:
        svc = conversation.service
        services_context = (
            f"CUSTOMER SELECTED THIS SERVICE:\nService: {svc.name}\n"
            f"Service Contact Number: {svc.contact_number}\nPrice: {svc.formatted_price}\n"
            f"Duration: {svc.estimated_duration}\nDescription: {svc.description}\n\n"
            f"ALL OTHER SERVICES FOR REFERENCE:\n{services_context}")
    from apps.business.domain import is_it_business
    if is_it_business():
        from .it_services import get_products_summary
        prod_summary = get_products_summary(tenant=tenant)
        if prod_summary:
            services_context += f"\n\n[VERIFIED PRODUCTS & PRICING]\n{prod_summary}"
    context = ConversationMemory.context(conversation)
    if booking_context is not None:
        context['booking_context'] = booking_context
    return build_rag_prompt(
        customer_message=customer_message,
        business_summary=f'Server local date/time: {timezone.localtime().isoformat()}\n' + get_business_summary(tenant=tenant),
        active_services_text=services_context,
        retrieved_knowledge_text=retrieved_context,
        customer_name=conversation.customer.name,
        customer_account_data=get_customer_account_summary(conversation.customer),
        **context)



def generate_reply(customer_message: str, conversation: Conversation) -> str:
    """
    RAG pipeline:
    1. Always pull latest active services & prices from PostgreSQL (ensuring zero price latency).
    2. Pull verified customer account data (appointments/bookings) tied strictly to their phone.
    3. Semantic retrieval from ChromaDB for FAQs and policies scoped to tenant.
    4. Multi-turn recent conversation history.
    5. Gemini LLM generation.
    6. Deterministic fallback if Gemini is unconfigured or fails.
    """
    tenant = getattr(conversation, 'tenant', None)
    active_services_text = get_services_formatted_text(tenant=tenant)

    intent, entity = IntentService.detect_intent(customer_message)
    # Business facts are deterministic. Use the LLM for open-ended questions only.
    if intent != IntentType.UNKNOWN:
        return generate_deterministic_reply(intent, entity, active_services_text, conversation, customer_message)
    # If Gemini is configured, run RAG pipeline
    if GeminiChatService.is_configured():
        try:
            # Semantic search in ChromaDB scoped to tenant
            retrieved_chunks = retrieve_relevant_knowledge(customer_message, n_results=3, tenant=tenant)
            retrieved_context_text = format_retrieved_context(retrieved_chunks)

            rag_prompt = build_contextual_prompt(customer_message, conversation, retrieved_context_text)

            # Generate via Gemini
            ai_reply = GeminiChatService.generate_reply(rag_prompt)
            if ai_reply and len(ai_reply.strip()) > 5:
                return ai_reply
        except Exception as e:
            logger.error(f"Error in Gemini RAG pipeline: {e}", exc_info=True)

    # Deterministic Grounded Fallback
    intent, matched_entity = IntentService.detect_intent(customer_message)
    conversation._unresolved = intent == IntentType.UNKNOWN
    return generate_deterministic_reply(intent, matched_entity, active_services_text, conversation=conversation, customer_message=customer_message)


def is_malayalam_or_manglish(text: str) -> bool:
    """
    Detect if text is written in Malayalam script or Manglish (Malayalam written using English alphabet).
    """
    if not text:
        return False
    # Malayalam Unicode block
    if re.search(r'[\u0D00-\u0D7F]', text):
        return True
    # Common Manglish keywords
    manglish_pattern = r'\b(poya|poyi|undoo|undo|aano|aanu|entha|enthoke|vishesham|ethraya|vila|cheyyam|cheyyamo|cheyyaamo|cheyyumo|venam|evide|eppo|vannu|varumo|namaskaram|sahayam|njan|ningal|nanni)\b'
    return bool(re.search(manglish_pattern, text, re.IGNORECASE))


def inspection_price_reply(service, language='en'):
    """An inspection quote is a policy, not a numeric repair price."""
    reply = say('inspection_price', language).format(service=service.name)
    if service.estimated_duration:
        reply += '\n' + say('duration', language).format(duration=service.estimated_duration)
    return reply


def generate_deterministic_reply(
    intent: IntentType,
    matched_entity: Optional[object],
    active_services_text: str,
    conversation: Optional[Conversation] = None,
    customer_message: str = ""
) -> str:
    """
    Formulate accurate replies grounded strictly in current PostgreSQL database records.
    Supports natural Malayalam and Manglish replies if detected.
    """
    profile = BusinessProfile.get_active()
    from apps.business.domain import is_it_business
    if is_it_business():
        from .it_services import business_reply
        it_reply = business_reply(intent, matched_entity, active_services_text, conversation, profile, customer_message=customer_message)
        if it_reply is not None:
            return it_reply

    shop_name = profile.shop_name if profile else "our AC service desk"
    cust_name = conversation.customer.name if (conversation and conversation.customer and conversation.customer.name) else None
    greeting_salutation = f"Hello {cust_name}!" if cust_name else "Hello!"

    is_manglish = is_malayalam_or_manglish(customer_message)

    if intent == IntentType.IDENTITY:
        language = conversation.customer.preferred_language if conversation else 'en'
        return say('identity', language).format(shop=shop_name)

    if intent == IntentType.AC_PROBLEM:
        language = conversation.customer.preferred_language if conversation else 'en'
        if IntentService.ac_problem_kind(customer_message) != 'cooling':
            return say('ac_issue', language)
        reply = say('cooling_issue', language)
        if isinstance(matched_entity, Service):
            return reply + '\n\n' + say('suggest_repair', language).format(service=matched_entity.name)
        return reply + '\n\n' + say('inspection_team', language)

    if intent == IntentType.DISCOUNT_ENQUIRY:
        language = conversation.customer.preferred_language if conversation else 'en'
        if matched_entity:
            return f"{say('listed_offer_info', language)}\n{matched_entity.answer}\n\n{say('offer_eligibility', language)}"
        return say('no_offer_details', language)

    # Presence check in Malayalam / Manglish: 'hello poya?', 'evide poyi?', 'undo?'
    if is_manglish and re.search(r'\b(poya|poyi|undoo|undo|evide)\b', customer_message, re.IGNORECASE):
        salutation = f"Hello {cust_name}!" if cust_name else "Hello!"
        return (
            f"{salutation} Njan ivide thanne undu. {shop_name}-il ninnulla automated assistant aanu. "
            f"Ningalkku AC servicing, repair, allengil booking karyangalil engane sahayam venam?"
        )

    if intent == IntentType.GREETING:
        if is_manglish:
            salutation = f"Namaskaram {cust_name}!" if cust_name else "Namaskaram!"
            return f"{salutation} {shop_name}-ilekku swagatham. Ningalude AC service, repair karyangalil engane sahayam venam?"
        language = conversation.customer.preferred_language if conversation else 'en'
        returning = conversation and Message.objects.filter(
            conversation__customer=conversation.customer, direction=MessageDirection.INBOUND).count() > 1
        if returning:
            greeting = say('returning_greeting', language).format(
                name=f' {cust_name}' if cust_name else '', shop=shop_name)
            if language == 'en' and re.match(r'hey\b', customer_message, re.I):
                greeting = greeting.replace('Hello', 'Hey', 1)
            return f"{greeting} {say('greeting', language)}"
        return f"{greeting_salutation} Welcome to {shop_name}. {say('greeting', language)}"

    elif intent == IntentType.SERVICE_LIST:
        prefix = f"Sure {cust_name}! " if cust_name else "Sure! "
        return (
            f"{prefix}We provide comprehensive AC repair, servicing, and installation. "
            f"Here are our active services and rates:\n\n"
            f"{active_services_text}\n\n"
            f"Would you like to know more about a specific service or book an appointment?"
        )

    elif intent == IntentType.SERVICE_PRICE:
        if isinstance(matched_entity, Service):
            if matched_entity.price_type == PriceType.INSPECTION_REQUIRED:
                language = conversation.customer.preferred_language if conversation else 'en'
                return inspection_price_reply(matched_entity, language)
            duration_str = f"\nEstimated duration: {matched_entity.estimated_duration}." if matched_entity.estimated_duration else ""
            desc_str = f"\n{matched_entity.description}" if matched_entity.description else ""
            prefix = f"Hi {cust_name}, our" if cust_name else "Our"
            return (
                f"{prefix} price for *{matched_entity.name}* is {matched_entity.formatted_price}.{duration_str}{desc_str}"
            )
        else:
            prefix = f"Hi {cust_name}, here" if cust_name else "Here"
            return (
                f"{prefix} is our current pricing for our services:\n\n"
                f"{active_services_text}\n\n"
                f"Which service are you interested in?"
            )

    elif intent == IntentType.WORKING_HOURS:
        if profile and profile.working_hours:
            hours = profile.working_hours
            holidays = f"\nHoliday Note: {profile.holiday_information}" if profile.holiday_information else ""
            return f"Our working hours are:\n{hours}{holidays}\n\nHow can we help you today?"
        return "Our team will confirm the working hours. Please choose Talk to team."

    elif intent == IntentType.SERVICE_AREAS:
        if profile and profile.service_areas:
            return (
                f"We provide services across the following areas:\n"
                f"{profile.service_areas}\n\n"
                f"Please share your requirements or location to get started!"
            )
        return "Our team will confirm coverage for your area. Please share your locality or requirements."

    elif intent == IntentType.SHOP_LOCATION:
        if profile:
            maps_info = f"\nGoogle Maps: {profile.google_maps_url}" if profile.google_maps_url else ""
            return (
                f"Our office address is:\n{profile.address}\n"
                f"Phone: {profile.contact_phone}{maps_info}\n\n"
                f"We also provide consultations and support remotely or on-site!"
            )
        return "Please contact our office phone for exact location directions."

    elif intent == IntentType.PAYMENT_METHODS:
        if profile and profile.accepted_payment_methods:
            return f"We accept the following payment methods:\n{profile.accepted_payment_methods}"
        return "Our team will confirm the available payment methods."

    elif intent == IntentType.WARRANTY_POLICY:
        if profile and profile.warranty_policies:
            policy_note = f"\nGeneral Policy: {profile.general_service_policies}" if profile.general_service_policies else ""
            return f"Warranty & Policy Details:\n{profile.warranty_policies}{policy_note}"
        return "Our team will confirm the warranty and inspection-charge policy for your service."

    elif intent == IntentType.FAQ_MATCH and matched_entity:
        return f"{matched_entity.answer}\n\nWould you like more details or need to book a service?"

    elif intent == IntentType.BOOKING_START:
        svc_name = matched_entity.name if isinstance(matched_entity, Service) else "AC service"
        prefix = f"Sure {cust_name}! " if cust_name else "Sure! "
        return (
            f"{prefix}I'd be happy to help you submit a booking request for {svc_name}.\n\n"
            f"May I please have your name and the service address to get started?"
        )

    elif intent == IntentType.BOOKING_STATUS:
        if conversation and conversation.customer:
            bookings, total, offset, scope = booking_history_page(conversation.customer, customer_message)
            if bookings:
                booking_lines = []
                for b in bookings:
                    svc_name = b.service.name if b.service else "AC Service"
                    status_str = b.get_status_display()
                    date_str = str(b.preferred_date) if b.preferred_date else "Pending scheduling"
                    slot_str = f" ({b.preferred_time_slot})" if b.preferred_time_slot else ""
                    recipient = f'\n  Service recipient: {b.recipient_name}' if b.recipient_name else ''
                    booking_lines.append(f"• *Booking #{b.id}*: {svc_name}\n  Status: *{status_str}*\n  Date: {date_str}{slot_str}{recipient}")

                prefix = f"Hi {cust_name}, here" if cust_name else "Here"
                heading = (f'your bookings ({offset + 1}–{offset + len(bookings)} of {total})'
                           if scope == 'all' else 'your latest booking details')
                return (
                    f"{prefix} are {heading}:\n\n"
                    + "\n\n".join(booking_lines) +
                    "\n\nNeed to reschedule or speak with our technician? Reply 'talk to agent' or let us know!"
                )
            else:
                prefix = f"Hi {cust_name}, we" if cust_name else "We"
                return (
                    f"{prefix} don't have any bookings registered under your phone number ({conversation.customer.phone_number}).\n\n"
                    f"Would you like to schedule a new AC service? Reply 'book' to get started!"
                )
        return "Please provide your booking reference number or contact our office."

    # UNKNOWN / Out-of-scope / Fallback
    contact_phone = profile.contact_phone if profile else "our service team"
    greeting = f"Hi {cust_name}, I" if cust_name else "I"
    return (
        f"{greeting}'m an automated customer support assistant for {shop_name}. "
        f"I can only help with AC repair, general servicing, gas filling, and appointment bookings.\n\n"
        f"Could I assist you with your air conditioner or check our service prices? "
        f"(For other inquiries, our shop contact is {contact_phone}.)"
    )


