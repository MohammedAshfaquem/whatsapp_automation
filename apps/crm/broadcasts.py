"""Client broadcast orchestration. No provider I/O at draft/launch time."""
import re
from contextlib import contextmanager
from django.db import transaction
from django.db.models import Q, Count
from django.utils import timezone
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice, MessageDirection, SenderType, ProcessingStatus
from apps.crm.models import Campaign, CampaignRecipient, ContactConsent, WhatsAppTemplate
from apps.whatsapp.models import WhatsAppDelivery, WhatsAppConfig


def variables(body):
    positions = re.findall(r'\{\{(\d+)\}\}', body)
    nums = sorted(set(map(int, positions)))
    remainder = re.sub(r'\{\{\d+\}\}', '', body)
    if '{{' in remainder or '}}' in remainder or nums != list(range(1, len(nums)+1)) or any(str(int(p)) != p for p in positions):
        raise ValueError('Use sequential numeric body variables: {{1}}, {{2}}, ...')
    return nums


def validate_parameters(template, values):
    count = len(variables(template.body_text))
    if not isinstance(values, list) or len(values) != count or any(not isinstance(v, str) or not v.strip() or len(v)>1024 for v in values):
        raise ValueError(f'This template requires exactly {count} non-empty text variables (maximum 1024 characters each).')
    return [v.strip() for v in values]


def resolve_recipient_parameters(campaign, contact) -> list:
    """Resolve per-contact dynamic template variables with fallback values, or static parameters."""
    expected_count = len(variables(campaign.template.body_text))
    mapping = getattr(campaign, 'variable_mapping', None) or []
    static_params = list(campaign.template_parameters or [])
    if not mapping or len(mapping) != expected_count:
        return validate_parameters(campaign.template, static_params)

    resolved = []
    for idx, spec in enumerate(mapping):
        if isinstance(spec, str):
            spec = {'source': 'static', 'value': spec}
        elif not isinstance(spec, dict):
            spec = {}
        source = str(spec.get('source') or 'static').strip()
        fallback = str(spec.get('fallback') or (static_params[idx] if idx < len(static_params) else '') or '').strip()
        val = ''
        if source == 'static':
            val = str(spec.get('value') or fallback or '').strip()
        elif source == 'contact.name':
            val = (contact.name or '').strip()
        elif source == 'contact.phone_number':
            val = (contact.phone_number or '').strip()
        elif source == 'contact.email':
            val = (contact.email or '').strip()
        elif source == 'contact.lifecycle_status':
            val = (contact.lifecycle_status or '').strip()
        elif source == 'contact.company':
            val = (contact.company.name if contact.company else '').strip()
        elif source.startswith('custom.'):
            field_key = source[7:]
            val = str((contact.custom_fields or {}).get(field_key, '')).strip()
        final_val = (val or fallback)[:1024]
        if not final_val:
            raise ValueError(f'Missing value and fallback for template variable {idx + 1}.')
        resolved.append(final_val)
    return resolved


def eligible_audience(campaign):
    qs = Customer.objects.filter(tenant_id=campaign.tenant_id, consent_record__tenant_id=campaign.tenant_id,
        consent_record__has_consented=True, consent_record__is_opted_out=False, consent_record__evidence_text__regex=r'\S')
    field = 'marketing_allowed' if not campaign.template or campaign.template.category == 'MARKETING' else 'utility_allowed'
    qs = qs.filter(**{'consent_record__'+field: True})
    if campaign.target_lifecycle_status:
        qs = qs.filter(lifecycle_status=campaign.target_lifecycle_status)
    tags = [str(t).strip() for t in (getattr(campaign, 'target_tags', None) or []) if str(t).strip()]
    if tags:
        from django.db import connection
        if connection.vendor == 'postgresql':
            tag_q = Q()
            for tag in tags:
                tag_q |= Q(tags__contains=[tag])
            qs = qs.filter(tag_q)
        else:
            wanted = {t.casefold() for t in tags}
            matched_ids = [
                cid for cid, c_tags in qs.values_list('pk', 'tags')
                if isinstance(c_tags, list) and any(str(ct).strip().casefold() in wanted for ct in c_tags)
            ]
            qs = qs.filter(pk__in=matched_ids)
    return qs.filter(phone_number__regex=r'^\+[1-9][0-9]{7,14}$')


def campaign_ready(campaign):
    t = campaign.template
    if not t or t.tenant_id != campaign.tenant_id or t.meta_status != 'APPROVED' or t.category not in ('UTILITY','MARKETING'):
        raise ValueError('Select a Meta-approved utility or marketing body-text template. Sync templates before launching.')
    expected = len(variables(t.body_text))
    mapping = getattr(campaign, 'variable_mapping', None) or []
    if mapping and len(mapping) == expected:
        for idx, spec in enumerate(mapping):
            if not isinstance(spec, dict):
                raise ValueError(f'Variable mapping {idx + 1} is invalid.')
            src = str(spec.get('source') or 'static')
            if src == 'static' and not str(spec.get('value') or spec.get('fallback') or '').strip():
                raise ValueError(f'Variable {idx + 1} requires a static value.')
            if src != 'static' and not str(spec.get('fallback') or '').strip():
                raise ValueError(f'Variable {idx + 1} ({src}) requires a non-empty fallback value.')
    else:
        validate_parameters(t, campaign.template_parameters)
    cfg = WhatsAppConfig.get_settings(tenant=campaign.tenant)
    if not (cfg.get('enabled') and cfg.get('access_token') and cfg.get('phone_number_id')):
        raise ValueError('Connect and verify this client’s Meta account before launching broadcasts.')
    if not campaign.tenant.is_active or not campaign.tenant.is_subscription_active:
        raise ValueError('An active workspace subscription is required.')


def launch(campaign_id, tenant, scheduled_at=None):
    with transaction.atomic():
        c = Campaign.objects.select_for_update(of=('self',)).select_related('template','tenant').get(pk=campaign_id,tenant=tenant)
        if c.status != 'DRAFT':
            raise ValueError('This campaign has already been launched. Duplicate launch was prevented.')
        campaign_ready(c)
        ids = list(eligible_audience(c).values_list('pk',flat=True)[:10001])
        if not ids:
            raise ValueError('No eligible contacts. Record consent with evidence for the selected template category.')
        if len(ids)>10000:
            raise ValueError('Split audiences larger than 10,000 into smaller campaigns.')
        CampaignRecipient.objects.bulk_create([CampaignRecipient(campaign=c,contact_id=pk) for pk in ids])
        c.audience_count=len(ids);c.scheduled_at=scheduled_at;c.launched_at=timezone.now()
        c.status='SCHEDULED' if scheduled_at and scheduled_at>timezone.now() else 'RUNNING'
        c.save()
        return c


def totals(c):
    counts = dict(c.recipients.values('delivery__status').annotate(n=Count('id')).values_list('delivery__status','n'))
    skipped = c.recipients.filter(status='SKIPPED').count()
    return {'sent_count':sum(counts.get(k,0) for k in ('SENT','DELIVERED','READ')),
            'delivered_count':sum(counts.get(k,0) for k in ('DELIVERED','READ')),
            'read_count':counts.get('READ',0), 'failed_count':sum(counts.get(k,0) for k in ('FAILED','BLOCKED')),
            'unknown_count':sum(counts.get(k,0) for k in ('UNKNOWN','SENDING')), 'skipped_count':skipped,
            'pending_count':c.recipients.filter(Q(delivery__status='PENDING')|Q(delivery__isnull=True,status='PENDING')).count()}


def run_campaigns(batch_size=50):
    Campaign.objects.filter(status='SCHEDULED',scheduled_at__lte=timezone.now()).update(status='RUNNING')
    pending = list(CampaignRecipient.objects.filter(campaign__status='RUNNING',status='PENDING',delivery__isnull=True).order_by('id').values_list('id',flat=True)[:batch_size])
    for pk in pending:
        seed = CampaignRecipient.objects.select_related('contact').get(pk=pk)
        # Same customer-first order as inbox creation and dispatch. Campaign pause/cancel
        # takes only the campaign lock, so it serializes with provider dispatch below.
        with transaction.atomic():
            contact=Customer.objects.select_for_update().get(pk=seed.contact_id)
            c=Campaign.objects.select_for_update(of=('self',)).select_related('template','tenant').get(pk=seed.campaign_id)
            r=CampaignRecipient.objects.select_for_update().get(pk=pk)
            if r.delivery_id or r.status!='PENDING' or c.status!='RUNNING':
                continue
            try:
                campaign_ready(c)
            except ValueError:
                c.status='PAUSED'; c.save(update_fields=['status','updated_at']);continue
            if not eligible_audience(c).filter(pk=contact.pk).exists():
                r.status='SKIPPED';r.reason='Consent revoked, suppressed, or no longer eligible';r.save();continue
            conversations=Conversation.objects.filter(tenant=c.tenant,customer=contact,channel=ChannelChoice.WHATSAPP)
            if conversations.count()>1:
                r.status='SKIPPED';r.reason='Multiple conversations require staff review';r.save();continue
            conv=conversations.first() or Conversation.objects.create(tenant=c.tenant,customer=contact,channel=ChannelChoice.WHATSAPP,status='HUMAN_HANDOVER')
            vals=resolve_recipient_parameters(c, contact)
            body=re.sub(r'\{\{(\d+)\}\}',lambda m:vals[int(m[1])-1],c.template.body_text)
            msg=Message.objects.create(conversation=conv,direction=MessageDirection.OUTBOUND,sender_type=SenderType.HUMAN,
                message_text=body,processing_status=ProcessingStatus.PROCESSED,
                response_data={'campaign_id':c.pk,'author_name':f'Broadcast: {c.name}','author_username':'','template_name':c.template.name})
            r.delivery=WhatsAppDelivery.objects.create(tenant=c.tenant,dedup_key=f'campaign:{c.pk}:{contact.pk}',recipient_phone=contact.phone_number,
                payload={'text':body,'conversation_id':conv.pk,'message_id':msg.pk,'sender_type':'CAMPAIGN','campaign_id':c.pk,
                    'campaign_recipient_id':r.pk,'template':{'name':c.template.name,'language':c.template.language,'parameters':vals}})
            r.status='QUEUED';r.save()
            conv.last_message_at=timezone.now();conv.save(update_fields=['last_message_at','updated_at'])
    # Counters derive from provider-backed delivery states, not optimistic UI counts.
    for c in Campaign.objects.filter(status='RUNNING'):
        with transaction.atomic():
            c=Campaign.objects.select_for_update().get(pk=c.pk)
            if c.status!='RUNNING':continue
            stats=totals(c)
            c.sent_count=stats['sent_count'];c.delivered_count=stats['delivered_count']
            retryable=c.recipients.filter(delivery__status='FAILED',delivery__attempts__lt=3).exists()
            if not stats['pending_count'] and not stats['unknown_count'] and not retryable:
                c.status='COMPLETED'
            c.save(update_fields=['sent_count','delivered_count','status','updated_at'])
    return len(pending)


@contextmanager
def dispatch_gate(record, conversation):
    """Held through transmission; pause/opt-out wins if committed before this gate."""
    if not str(record.dedup_key).startswith('campaign:') and record.payload.get('sender_type')!='CAMPAIGN':
        yield True, '';return
    with transaction.atomic():
        r=CampaignRecipient.objects.filter(delivery_id=record.pk,campaign__tenant_id=record.tenant_id).first()
        if not r:
            yield False,'Invalid campaign origin';return
        c=Campaign.objects.select_for_update(of=('self',)).select_related('tenant','template').get(pk=r.campaign_id)
        try:
            campaign_ready(c)
            expected={'name':c.template.name,'language':c.template.language,'parameters':validate_parameters(c.template,c.template_parameters)}
            if (not conversation or record.payload.get('template')!=expected
                or record.payload.get('campaign_id')!=c.pk or record.payload.get('campaign_recipient_id')!=r.pk
                or conversation.customer_id!=r.contact_id or not eligible_audience(c).filter(pk=r.contact_id,phone_number=record.recipient_phone).exists()):
                raise ValueError('Campaign consent, template, recipient or conversation no longer valid')
            result = (c.status=='RUNNING', 'Campaign paused, cancelled, or completed')
        except ValueError as e:
            result = (False, str(e))
        yield result
