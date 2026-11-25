"""
Release 3 Business Hours evaluation, Away / Greeting automation helpers,
and No-Response Follow-Up SLA scanner for background worker execution.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.business.models import BusinessProfile
from apps.chatbot.models import Conversation, ConversationStatus
from apps.crm.models import Activity, ActivityPriority, ActivityStatus, ActivityType

DAY_KEYS = ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')
TIME_RE = re.compile(r'^(?:[01]\d|2[0-3]):[0-5]\d$')


def default_business_hours(tz_name: str = 'Asia/Kolkata') -> dict:
    return {
        'enabled': False,
        'timezone': tz_name or 'Asia/Kolkata',
        'days': {
            day: {'enabled': day != 'sun', 'start': '09:00', 'end': '18:00'}
            for day in DAY_KEYS
        },
    }


def normalize_business_hours(raw: dict | None, fallback_tz: str = 'Asia/Kolkata') -> dict:
    base = default_business_hours(fallback_tz)
    if not isinstance(raw, dict):
        return base
    tz_name = str(raw.get('timezone') or fallback_tz or 'Asia/Kolkata').strip()
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        raise ValueError(f'Invalid business-hours timezone: {tz_name}')
    base['timezone'] = tz_name
    base['enabled'] = bool(raw.get('enabled', False))
    days_in = raw.get('days') or {}
    if not isinstance(days_in, dict):
        raise ValueError('Business hours days must be an object.')
    for day in DAY_KEYS:
        d_cfg = days_in.get(day)
        if not isinstance(d_cfg, dict):
            continue
        enabled = bool(d_cfg.get('enabled', False))
        start = str(d_cfg.get('start') or '09:00').strip()
        end = str(d_cfg.get('end') or '18:00').strip()
        if not TIME_RE.match(start) or not TIME_RE.match(end):
            raise ValueError(f'Use HH:MM 24-hour times for {day}.')
        if enabled and start >= end:
            raise ValueError(f'Closing time must be after opening time for {day}.')
        base['days'][day] = {'enabled': enabled, 'start': start, 'end': end}
    return base


def is_within_business_hours(profile: BusinessProfile | None, at_dt: datetime | None = None) -> bool:
    """
    Returns True if business hours enforcement is disabled or `at_dt` falls within
    an active weekday window in the configured timezone.
    """
    if not profile or not isinstance(profile.business_hours, dict) or not profile.business_hours.get('enabled'):
        return True
    tz_name = profile.business_hours.get('timezone') or getattr(profile.tenant, 'timezone', None) or 'Asia/Kolkata'
    try:
        tz = ZoneInfo(tz_name)
    except ZoneInfoNotFoundError:
        tz = ZoneInfo('UTC')
    now_local = (at_dt or timezone.now()).astimezone(tz)
    day_key = DAY_KEYS[now_local.weekday()]
    day_cfg = (profile.business_hours.get('days') or {}).get(day_key) or {}
    if not day_cfg.get('enabled'):
        return False
    cur_hhmm = now_local.strftime('%H:%M')
    start = str(day_cfg.get('start') or '00:00')
    end = str(day_cfg.get('end') or '23:59')
    return start <= cur_hhmm < end


def process_no_response_followups(now: datetime | None = None, batch_size: int = 50) -> int:
    """
    Create follow-up tasks and record BusinessEvents when human-queued conversations wait
    longer than `no_response_followup_minutes` without a subsequent human reply.
    """
    from apps.crm.automation_engine import process_pending_business_events, record_business_event

    current = now or timezone.now()
    created_count = 0
    profiles = (
        BusinessProfile.objects.filter(
            is_active=True,
            tenant__isnull=False,
            tenant__is_active=True,
            no_response_followup_minutes__gt=0,
        )
        .select_related('tenant')
    )
    for profile in profiles:
        threshold = current - timedelta(minutes=int(profile.no_response_followup_minutes))
        candidates = (
            Conversation.objects.filter(
                tenant=profile.tenant,
                status__in=(ConversationStatus.HUMAN_HANDOVER, ConversationStatus.BOT_ACTIVE),
                last_inbound_at__isnull=False,
                last_inbound_at__lte=threshold,
            )
            .filter(
                Q(first_human_response_at__isnull=True)
                | Q(first_human_response_at__lt=models_F('last_inbound_at'))
            )
            .filter(
                Q(followup_alert_sent_at__isnull=True)
                | Q(followup_alert_sent_at__lt=models_F('last_inbound_at'))
            )
            .select_related('customer', 'assigned_staff')
            .order_by('last_inbound_at')[:batch_size]
        )
        for conv in candidates:
            with transaction.atomic():
                locked = Conversation.objects.select_for_update().filter(pk=conv.pk).first()
                if not locked or not locked.last_inbound_at or locked.last_inbound_at > threshold:
                    continue
                if locked.followup_alert_sent_at and locked.followup_alert_sent_at >= locked.last_inbound_at:
                    continue
                assignee = locked.assigned_staff or (locked.customer.owner if locked.customer else None)
                Activity.objects.create(
                    tenant=profile.tenant,
                    title=f"Follow up unanswered WhatsApp chat ({locked.customer.name or locked.customer.phone_number})",
                    activity_type=ActivityType.FOLLOW_UP,
                    priority=ActivityPriority.HIGH,
                    status=ActivityStatus.PENDING,
                    due_date=current + timedelta(minutes=15),
                    contact=locked.customer,
                    assigned_to=assignee,
                    notes=f"No human response within {profile.no_response_followup_minutes} minute(s).",
                )
                record_business_event(
                    tenant=profile.tenant,
                    event_type='conversation.no_response',
                    entity_type='conversation',
                    entity_id=locked.pk,
                    payload={
                        'conversation_id': locked.pk,
                        'customer_id': locked.customer_id,
                        'minutes_threshold': profile.no_response_followup_minutes,
                    },
                    dedup_key=f"no_response:{locked.pk}:{int(locked.last_inbound_at.timestamp())}",
                )
                locked.followup_alert_sent_at = current
                locked.save(update_fields=['followup_alert_sent_at', 'updated_at'])
                created_count += 1
        if created_count:
            process_pending_business_events(tenant=profile.tenant)
    return created_count


def models_F(field_name: str):
    from django.db.models import F
    return F(field_name)
