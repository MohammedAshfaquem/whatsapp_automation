"""Service selection and price/menu controls shared by WhatsApp and the portal."""
from apps.services.models import Service, PriceType
from ..reply import ChatReply
from ..language import say
from . import text


def show_price(message, conversation):
    customer_name = conversation.customer.name or None
    options = None
    try:
        s_id = int(message.split("_")[-1])
        svc = Service.objects.filter(id=s_id, is_active=True).first()
    except (ValueError, TypeError):
        svc = conversation.service

    if svc:
        duration_str = f"\n• Duration: {svc.estimated_duration}" if svc.estimated_duration else ""
        desc_str = f"\n• Details: {svc.description}" if svc.description else ""
        prefix = f"Hi {customer_name}, our" if customer_name else "Our"
        reply_text = (
            f"{prefix} price for *{svc.name}* is {svc.formatted_price}.{duration_str}{desc_str}\n\n"
            f"Would you like to schedule an appointment for this service?"
        )
        if svc.price_type == PriceType.INSPECTION_REQUIRED:
            reply_text = text.inspection_price_reply(svc, conversation.customer.preferred_language)
            reply_text += '\n\n' + say('request_visit', conversation.customer.preferred_language)
        options = [
            {"id": f"book_service_{svc.id}", "title": "Book Appointment"},
            {"id": "view_services", "title": "View Services"}
        ]
        conversation.service = svc
        conversation.save(update_fields=['service'])
    else:
        reply_text = "Please select a service from our menu to view its price."
    return ChatReply(reply_text, options=options)


def select_service(message, conversation, entity, fallback_reply=None):
    customer_name = conversation.customer.name or None
    options = None
    selected_svc = entity if isinstance(entity, Service) else None
    if not selected_svc and "_" in message:
        try:
            s_id = int(message.split("_")[-1])
            selected_svc = Service.objects.filter(id=s_id, is_active=True).first()
        except (ValueError, TypeError):
            pass

    if selected_svc:
        conversation.service = selected_svc
        conversation.save(update_fields=['service'])
        prefix = f"Great {customer_name}! " if customer_name else "Great! "
        reply_text = f"{prefix}Would you like to check the service price or book an appointment?"
        options = [
            {"id": f"check_price_{selected_svc.id}", "title": "Check Price"},
            {"id": f"book_service_{selected_svc.id}", "title": "Book Appointment"}
        ]
    else:
        reply_text = fallback_reply or 'Please select a service from our menu.'
    return ChatReply(reply_text, options=options)


def list_services(conversation):
    customer_name = conversation.customer.name or None
    options = None
    active_services = list(Service.objects.filter(is_active=True).order_by('id'))
    if not active_services:
        reply_text = "No services are currently listed. Please contact our shop directly."
        options = []
    else:
        prefix = f"Sure {customer_name}! " if customer_name else "Sure! "
        reply_text = f"{prefix}Which service are you interested in?"
        options = [
            {
                "id": f"service_{s.id}",
                "title": s.name[:24],
                "description": s.formatted_price[:72]
            }
            for s in active_services[:10]
        ]
    return ChatReply(reply_text, options=options)


