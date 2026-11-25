import logging
import uuid
from django.db import transaction
from django.utils import timezone
from .models import WhatsAppDelivery
from .whatsapp_client import WhatsAppClient
from .delivery_context import locked_delivery, sender_kind

logger = logging.getLogger(__name__)


def dispatch(delivery_id):
    """
    Claim once. Ambiguous timeouts require review, never an automatic duplicate.
    Enforces atomic capacity reservation before provider dispatch to avoid race conditions.
    """
    # Commit the claim before provider I/O. If this process dies after Meta
    # accepts the request, SENDING survives and the worker will not resend it.
    from apps.crm.models import CampaignRecipient
    campaign_recipient = CampaignRecipient.objects.filter(delivery_id=delivery_id).select_related('campaign').first()
    if campaign_recipient and campaign_recipient.campaign.status in ('PAUSED', 'SCHEDULED'):
        return False
    claim = uuid.uuid4().hex
    with transaction.atomic():
        record = WhatsAppDelivery.objects.select_for_update().get(pk=delivery_id)
        if record.status not in ('PENDING', 'FAILED') or record.attempts >= 3:
            return record.status in ('SENT', 'DELIVERED', 'READ')
        from apps.tenants.platform_auth import check_outbound_whatsapp_pause
        paused, pause_reason = check_outbound_whatsapp_pause(record.tenant)
        if paused:
            record.status = 'BLOCKED'
            record.last_error = pause_reason[:500]
            record.save(update_fields=['status', 'last_error', 'updated_at'])
            return False
        if record.tenant and (not record.tenant.is_active or not record.tenant.is_subscription_active):
            record.status = 'BLOCKED'
            record.last_error = 'Tenant suspended or pending platform activation'
            record.save(update_fields=['status', 'last_error', 'updated_at'])
            return False
        if record.tenant and not record.quota_reserved:
            if not record.tenant.reserve_monthly_message_slot():
                record.status = 'BLOCKED'
                record.last_error = 'Monthly outbound message allowance exceeded'
                record.save(update_fields=['status', 'last_error', 'updated_at'])
                return False
            record.quota_reserved = True
        record.status = 'SENDING'
        record.attempts += 1
        record.payload = {**(record.payload or {}), 'dispatch_claim': claim}
        record.save(update_fields=['status', 'attempts', 'payload', 'quota_reserved', 'updated_at'])

    with locked_delivery(delivery_id) as (record, conversation):
        if record.status != 'SENDING' or record.payload.get('dispatch_claim') != claim:
            return record.status in ('SENT', 'DELIVERED', 'READ')
        # This customer/conversation gate is held through the external request.
        # A takeover waits for a request already in flight; pending bot sends are suppressed.
        kind = sender_kind(record)
        campaign_ok, campaign_error = getattr(record, '_campaign_check', (True, ''))
        if not campaign_ok or (kind and kind != 'CAMPAIGN' and (not conversation or (kind == 'BOT' and conversation.status != 'BOT_ACTIVE')
                     or (kind == 'HUMAN' and conversation.status != 'HUMAN_HANDOVER'))):
            record.status = 'BLOCKED'
            record.last_error = campaign_error or 'Suppressed: unknown origin or conversation mode changed before provider dispatch'
            if campaign_error == 'Campaign paused, cancelled, or completed' and campaign_recipient:
                campaign_recipient.campaign.refresh_from_db()
                if campaign_recipient.campaign.status == 'PAUSED':
                    record.status = 'PENDING'
            if record.tenant and record.quota_reserved:
                record.tenant.finalize_monthly_message_reservation(succeeded=False)
                record.quota_reserved = False
            record.save(update_fields=['status', 'last_error', 'quota_reserved', 'updated_at'])
            return False

        payload = record.payload
        tenant = record.tenant
        try:
            if payload.get('template'):
                ok, provider_id = WhatsAppClient.send_template_message(record.recipient_phone, tenant=tenant, **payload['template'])
            elif payload.get('media'):
                media = payload['media']
                media_ref = media.get('meta_media_id') or media.get('link')
                if not media_ref and media.get('storage_key'):
                    from django.core.files.storage import default_storage
                    with default_storage.open(media['storage_key'], 'rb') as fh:
                        raw_bytes = fh.read()
                    up_ok, up_res = WhatsAppClient.upload_media(
                        raw_bytes,
                        media.get('mime_type', 'application/octet-stream'),
                        media.get('filename', 'attachment'),
                        tenant=tenant,
                    )
                    if not up_ok:
                        ok, provider_id = False, up_res
                        media_ref = None
                    else:
                        media_ref = up_res
                if media_ref:
                    ok, provider_id = WhatsAppClient.send_media_message(
                        record.recipient_phone,
                        media.get('media_type', 'document'),
                        media_ref,
                        filename=media.get('filename', ''),
                        caption=media.get('caption', ''),
                        tenant=tenant,
                    )
            elif payload.get('flow'):
                ok, provider_id = WhatsAppClient.send_flow_message(record.recipient_phone, payload['text'], tenant=tenant, **payload['flow'])
            elif payload.get('options'):
                ok, provider_id = WhatsAppClient.send_interactive_options(recipient_phone=record.recipient_phone,
                    body_text=payload['text'], options=payload['options'], tenant=tenant)
            else:
                ok, provider_id = WhatsAppClient.send_text_message(recipient_phone=record.recipient_phone,
                    message_text=payload['text'], tenant=tenant)
        except Exception as error:
            ok, provider_id = False, f'Uncertain delivery: {type(error).__name__}'
            logger.exception('Outbound delivery failed for record %s', record.pk)

        error = str(provider_id or '')
        state = 'SENT' if ok else ('UNKNOWN' if any(word in error.lower() for word in ('timeout', 'uncertain', 'connection')) else 'FAILED')

        # Atomically finalize or release the reservation based on conclusive outcome
        quota_reserved = getattr(record, 'quota_reserved', False)
        if tenant and quota_reserved:
            if ok:
                tenant.finalize_monthly_message_reservation(succeeded=True)
                quota_reserved = False
            elif state == 'FAILED':
                tenant.finalize_monthly_message_reservation(succeeded=False)
                quota_reserved = False
            # If 'UNKNOWN', preserve reservation to prevent quota bypass until manually inspected

        WhatsAppDelivery.objects.filter(pk=record.pk, status='SENDING').update(
            status=state,
            provider_message_id=provider_id if ok else '',
            quota_reserved=quota_reserved,
            last_error='' if ok else error,
            updated_at=timezone.now()
        )
        return ok
