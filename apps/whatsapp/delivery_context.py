"""Shared dispatch/takeover gate. Lock order: customer, conversation, delivery, quota."""
from contextlib import contextmanager
from django.db import transaction
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice
from .models import WhatsAppDelivery


def resolve_conversation(record):
    payload = record.payload or {}
    qs = Conversation.objects.filter(tenant_id=record.tenant_id, customer__phone_number=record.recipient_phone, channel=ChannelChoice.WHATSAPP)
    if payload.get('conversation_id'):
        return qs.filter(pk=payload['conversation_id']).first()
    if str(record.dedup_key).startswith('staff:'):
        try:
            message = Message.objects.filter(pk=int(record.dedup_key.split(':')[1]), conversation__tenant_id=record.tenant_id).first()
        except (ValueError, IndexError):
            message = None
        return qs.filter(pk=message.conversation_id).first() if message else None
    matches = list(qs.order_by('pk')[:2])
    return matches[0] if len(matches) == 1 else None


def sender_kind(record):
    return (record.payload or {}).get('sender_type') or ('BOT' if str(record.dedup_key).startswith('reply:') else 'HUMAN' if str(record.dedup_key).startswith('staff:') else '')


@contextmanager
def locked_delivery(delivery_id):
    with transaction.atomic():
        preview = WhatsAppDelivery.objects.get(pk=delivery_id)
        conversation = resolve_conversation(preview)
        if conversation:
            Customer.objects.select_for_update().get(pk=conversation.customer_id)
            conversation = Conversation.objects.select_for_update().get(pk=conversation.pk)
        record = WhatsAppDelivery.objects.select_for_update().get(pk=delivery_id)
        # Origin and mode cannot change after this gate until provider result commits.
        current = resolve_conversation(record)
        if not conversation or not current or current.pk != conversation.pk:
            conversation = None
        from apps.crm.broadcasts import dispatch_gate
        with dispatch_gate(record, conversation) as campaign_check:
            record._campaign_check = campaign_check
            yield record, conversation


def cancel_pending_bot_deliveries(conversation, action):
    from django.db.models import Q
    records = WhatsAppDelivery.objects.select_for_update().filter(
        tenant_id=conversation.tenant_id, recipient_phone=conversation.customer.phone_number,
        status__in=['PENDING', 'FAILED', 'SENDING']).filter(Q(dedup_key__startswith='reply:') | Q(payload__sender_type='BOT'))
    for record in records:
        origin = (record.payload or {}).get('conversation_id')
        if origin and origin != conversation.pk:
            continue
        if record.status == 'SENDING':
            # It may be a pre-gate claim OR a worker that died after Meta accepted.
            # Never turn this ambiguous state into a conclusively retryable failure.
            record.status = 'UNKNOWN'
            record.last_error = 'Human takeover interrupted an ambiguous send; inspect provider delivery before retry.'
            record.save(update_fields=['status', 'last_error', 'updated_at'])
            continue
        record.status = 'BLOCKED'
        record.last_error = 'Cancelled before provider dispatch by human takeover: ' + action
        if record.tenant and record.quota_reserved:
            record.tenant.finalize_monthly_message_reservation(succeeded=False)
            record.quota_reserved = False
        record.save(update_fields=['status', 'last_error', 'quota_reserved', 'updated_at'])
