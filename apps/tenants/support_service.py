"""
Service layer for Client-to-Platform SaaS Support (strictly separate from CRM SupportTicket)
and durable 10-minute SLA emergency escalation.
"""
import logging
import os
import secrets
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db import IntegrityError, connection, transaction
from django.utils import timezone

from .email_service import process_emails, queue_email, ready as smtp_ready
from .models import (
    AuditLogAction,
    PlatformServiceConfig,
    PlatformSupportEscalation,
    PlatformSupportMessage,
    PlatformSupportTicket,
    PlatformTicketCategory,
    PlatformTicketPriority,
    PlatformTicketSenderType,
    PlatformTicketStatus,
    Tenant,
    TenantAuditLog,
)

User = get_user_model()
logger = logging.getLogger(__name__)

MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024  # 5 MB
ALLOWED_ATTACHMENT_EXTS = {'.png', '.jpg', '.jpeg', '.webp', '.pdf', '.txt', '.csv', '.log'}


class SupportError(Exception):
    def __init__(self, message, *, code='support_error', status=400):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status


def get_support_sla_config() -> dict:
    cfg = PlatformServiceConfig.objects.filter(pk=1).first()
    return {
        'alert_email': (cfg.support_alert_email if cfg and cfg.support_alert_email else 'support@neorizsolutions.com'),
        'threshold_minutes': int(cfg.support_escalation_minutes if cfg and cfg.support_escalation_minutes else 10),
    }


def _generate_ticket_number() -> str:
    return f"SUP-{secrets.token_hex(3).upper()}"


def _save_attachment(uploaded_file, *, tenant_id: int, ticket_id) -> dict:
    if not uploaded_file:
        return {}
    if uploaded_file.size > MAX_ATTACHMENT_BYTES:
        raise SupportError("Attachment must be 5 MB or smaller.", code='file_too_large', status=400)
    raw_name = os.path.basename(getattr(uploaded_file, 'name', '') or 'attachment')
    ext = Path(raw_name).suffix.lower()
    if ext not in ALLOWED_ATTACHMENT_EXTS:
        raise SupportError(
            "Unsupported attachment type. Allowed: PNG, JPG, WEBP, PDF, TXT, CSV, LOG.",
            code='invalid_file_type',
            status=400,
        )
    safe_base = ''.join(c if c.isalnum() or c in ('-', '_', '.') else '_' for c in raw_name)[:120]
    storage_key = f"platform_support/{tenant_id}/{ticket_id}/{secrets.token_hex(6)}_{safe_base}"
    saved_key = default_storage.save(storage_key, uploaded_file)
    return {
        'attachment_name': safe_base,
        'attachment_key': saved_key,
        'attachment_mime': (getattr(uploaded_file, 'content_type', '') or 'application/octet-stream')[:80],
        'attachment_size': int(uploaded_file.size or 0),
    }


def create_platform_ticket(
    *,
    tenant: Tenant,
    user: User,
    subject: str,
    description: str,
    category: str = PlatformTicketCategory.META_SETUP,
    priority: str = PlatformTicketPriority.NORMAL,
    attachment=None,
) -> PlatformSupportTicket:
    clean_subject = (subject or '').strip()
    clean_body = (description or '').strip()
    if not clean_subject:
        raise SupportError("Please provide a ticket subject.", code='subject_required', status=400)
    if not clean_body:
        raise SupportError("Please describe your issue or question.", code='description_required', status=400)
    if category not in PlatformTicketCategory.values:
        category = PlatformTicketCategory.OTHER
    if priority not in PlatformTicketPriority.values:
        priority = PlatformTicketPriority.NORMAL

    now = timezone.now()
    with transaction.atomic():
        ticket_number = _generate_ticket_number()
        while PlatformSupportTicket.objects.filter(ticket_number=ticket_number).exists():
            ticket_number = _generate_ticket_number()

        ticket = PlatformSupportTicket.objects.create(
            ticket_number=ticket_number,
            tenant=tenant,
            created_by=user,
            subject=clean_subject[:200],
            category=category,
            priority=priority,
            status=PlatformTicketStatus.OPEN,
            sla_cycle_started_at=now,
            current_cycle_escalated=False,
            last_client_message_at=now,
        )
        att_meta = _save_attachment(attachment, tenant_id=tenant.pk, ticket_id=ticket.pk)
        PlatformSupportMessage.objects.create(
            ticket=ticket,
            sender=user,
            sender_type=PlatformTicketSenderType.CLIENT,
            is_internal_note=False,
            body=clean_body,
            **att_meta,
        )
        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=user,
            action=AuditLogAction.PLATFORM_TICKET_CREATED,
            summary=f"Opened platform support ticket {ticket.ticket_number}: {ticket.subject[:100]}",
            details={'ticket_id': str(ticket.pk), 'ticket_number': ticket.ticket_number, 'priority': priority, 'category': category},
        )
        return ticket


def post_client_reply(
    *,
    ticket: PlatformSupportTicket,
    tenant: Tenant,
    user: User,
    body: str,
    attachment=None,
) -> PlatformSupportMessage:
    clean_body = (body or '').strip()
    if not clean_body and not attachment:
        raise SupportError("Reply message cannot be empty.", code='empty_reply', status=400)

    now = timezone.now()
    with transaction.atomic():
        locked = PlatformSupportTicket.objects.select_for_update().get(pk=ticket.pk)
        if locked.tenant_id != tenant.pk:
            raise SupportError("Support ticket not found.", code='not_found', status=404)

        att_meta = _save_attachment(attachment, tenant_id=tenant.pk, ticket_id=locked.pk)
        msg = PlatformSupportMessage.objects.create(
            ticket=locked,
            sender=user,
            sender_type=PlatformTicketSenderType.CLIENT,
            is_internal_note=False,
            body=clean_body or f"Uploaded attachment: {att_meta.get('attachment_name', 'file')}",
            **att_meta,
        )
        # IMPORTANT: Only start a new SLA wait cycle if no unanswered cycle is currently active!
        # Additional follow-up messages MUST NOT reset or delay an existing 10-minute timer.
        if locked.sla_cycle_started_at is None:
            locked.sla_cycle_started_at = now
            locked.current_cycle_escalated = False

        locked.last_client_message_at = now
        locked.status = PlatformTicketStatus.AWAITING_PLATFORM
        locked.save(
            update_fields=[
                'sla_cycle_started_at',
                'current_cycle_escalated',
                'last_client_message_at',
                'status',
                'updated_at',
            ]
        )
        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=user,
            action=AuditLogAction.PLATFORM_TICKET_REPLIED,
            summary=f"Client replied on platform ticket {locked.ticket_number}",
            details={'ticket_id': str(locked.pk), 'message_id': str(msg.pk)},
        )
        return msg


def update_client_ticket_status(*, ticket: PlatformSupportTicket, tenant: Tenant, user: User, action: str) -> PlatformSupportTicket:
    now = timezone.now()
    with transaction.atomic():
        locked = PlatformSupportTicket.objects.select_for_update().get(pk=ticket.pk)
        if locked.tenant_id != tenant.pk:
            raise SupportError("Support ticket not found.", code='not_found', status=404)

        if action == 'resolve':
            locked.status = PlatformTicketStatus.RESOLVED
            locked.resolved_at = now
            locked.sla_cycle_started_at = None
            locked.current_cycle_escalated = False
            locked.save()
            PlatformSupportEscalation.objects.filter(ticket=locked, status='PENDING').update(
                status='CANCELLED',
                reason='Resolved by client before alert dispatch',
            )
            PlatformSupportMessage.objects.create(
                ticket=locked,
                sender=user,
                sender_type=PlatformTicketSenderType.SYSTEM,
                is_internal_note=False,
                body=f"Marked resolved by {user.get_full_name() or user.username}.",
            )
        elif action == 'reopen':
            locked.status = PlatformTicketStatus.OPEN
            locked.resolved_at = None
            locked.closed_at = None
            if locked.sla_cycle_started_at is None:
                locked.sla_cycle_started_at = now
                locked.current_cycle_escalated = False
            locked.save()
            PlatformSupportMessage.objects.create(
                ticket=locked,
                sender=user,
                sender_type=PlatformTicketSenderType.SYSTEM,
                is_internal_note=False,
                body=f"Ticket reopened by {user.get_full_name() or user.username}.",
            )
        else:
            raise SupportError("Action must be 'resolve' or 'reopen'.", code='invalid_action', status=400)

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=user,
            action=AuditLogAction.PLATFORM_TICKET_STATUS_CHANGED,
            summary=f"Client set platform ticket {locked.ticket_number} to {locked.status}",
            details={'ticket_id': str(locked.pk), 'status': locked.status},
        )
        return locked


def post_platform_reply(
    *,
    ticket: PlatformSupportTicket,
    operator: User,
    body: str,
    is_internal_note: bool = False,
    new_status: str | None = None,
) -> PlatformSupportMessage:
    clean_body = (body or '').strip()
    if not clean_body:
        raise SupportError("Message body cannot be empty.", code='empty_reply', status=400)
    if new_status and new_status not in PlatformTicketStatus.values:
        raise SupportError("Invalid ticket status.", code='invalid_status', status=400)

    now = timezone.now()
    with transaction.atomic():
        locked = PlatformSupportTicket.objects.select_for_update().get(pk=ticket.pk)
        msg = PlatformSupportMessage.objects.create(
            ticket=locked,
            sender=operator,
            sender_type=PlatformTicketSenderType.PLATFORM,
            is_internal_note=bool(is_internal_note),
            body=clean_body,
        )
        if not is_internal_note:
            # Actual public reply clears the SLA wait timer and cancels pending escalations
            locked.sla_cycle_started_at = None
            locked.current_cycle_escalated = False
            if locked.first_platform_reply_at is None:
                locked.first_platform_reply_at = now
            locked.last_platform_reply_at = now
            target_status = new_status or PlatformTicketStatus.AWAITING_CLIENT
            locked.status = target_status
            if target_status == PlatformTicketStatus.RESOLVED:
                locked.resolved_at = now
            elif target_status == PlatformTicketStatus.CLOSED:
                locked.closed_at = now
            locked.save()
            PlatformSupportEscalation.objects.filter(ticket=locked, status='PENDING').update(
                status='CANCELLED',
                reason='Platform team replied before dispatch',
            )
        else:
            # Internal notes MUST NEVER clear or satisfy the client response SLA!
            locked.save(update_fields=['updated_at'])

        TenantAuditLog.objects.create(
            tenant=locked.tenant,
            actor=operator,
            action=AuditLogAction.PLATFORM_TICKET_REPLIED,
            summary=f"Platform {'internal note' if is_internal_note else 'reply'} on {locked.ticket_number}",
            details={'ticket_id': str(locked.pk), 'is_internal_note': bool(is_internal_note), 'status': locked.status},
        )
        return msg


def update_platform_ticket(
    *,
    ticket: PlatformSupportTicket,
    operator: User,
    status: str | None = None,
    priority: str | None = None,
    assigned_to_id: int | None = None,
) -> PlatformSupportTicket:
    now = timezone.now()
    with transaction.atomic():
        locked = PlatformSupportTicket.objects.select_for_update().get(pk=ticket.pk)
        if status is not None:
            if status not in PlatformTicketStatus.values:
                raise SupportError("Invalid ticket status.", code='invalid_status', status=400)
            locked.status = status
            if status in (PlatformTicketStatus.RESOLVED, PlatformTicketStatus.CLOSED):
                locked.sla_cycle_started_at = None
                locked.current_cycle_escalated = False
                if status == PlatformTicketStatus.RESOLVED:
                    locked.resolved_at = now
                else:
                    locked.closed_at = now
                PlatformSupportEscalation.objects.filter(ticket=locked, status='PENDING').update(
                    status='CANCELLED',
                    reason=f'Ticket marked {status} before dispatch',
                )
            elif status in (PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM) and locked.sla_cycle_started_at is None:
                locked.sla_cycle_started_at = now
                locked.current_cycle_escalated = False

        if priority is not None:
            if priority not in PlatformTicketPriority.values:
                raise SupportError("Invalid ticket priority.", code='invalid_priority', status=400)
            locked.priority = priority

        if assigned_to_id is not None:
            if assigned_to_id == 0 or assigned_to_id == '':
                locked.assigned_to = None
            else:
                assignee = User.objects.filter(pk=assigned_to_id, is_superuser=True, is_active=True).first()
                if not assignee:
                    raise SupportError("Assignee must be an active platform operator.", code='invalid_assignee', status=400)
                locked.assigned_to = assignee

        locked.save()
        TenantAuditLog.objects.create(
            tenant=locked.tenant,
            actor=operator,
            action=AuditLogAction.PLATFORM_TICKET_STATUS_CHANGED,
            summary=f"Platform updated {locked.ticket_number} [{locked.status}/{locked.priority}]",
            details={'ticket_id': str(locked.pk), 'status': locked.status, 'priority': locked.priority, 'assigned_to': locked.assigned_to_id},
        )
        return locked


def _lock_candidates(qs):
    if connection.features.has_select_for_update_skip_locked:
        return qs.select_for_update(skip_locked=True)
    return qs.select_for_update()


def process_support_escalations(*, batch_size: int = 25, now=None) -> int:
    """
    Durable SLA worker sweep:
    Finds client-to-platform tickets where a client message cycle has remained unanswered
    by any public platform reply for >= support_escalation_minutes (default 10).
    Fires AT MOST ONE alert per unanswered cycle using a DB UniqueConstraint + row locks,
    and re-checks right before queueing/sending.
    """
    cfg = get_support_sla_config()
    now = now or timezone.now()
    threshold_minutes = cfg['threshold_minutes']
    alert_email = cfg['alert_email']
    cutoff = now - timedelta(minutes=threshold_minutes)

    candidate_ids = list(
        PlatformSupportTicket.objects.filter(
            status__in=[PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM],
            sla_cycle_started_at__isnull=False,
            sla_cycle_started_at__lte=cutoff,
            current_cycle_escalated=False,
        )
        .order_by('sla_cycle_started_at')
        .values_list('pk', flat=True)[:batch_size]
    )

    escalated_count = 0
    queued_email_ids = []

    for ticket_pk in candidate_ids:
        try:
            with transaction.atomic():
                ticket = (
                    _lock_candidates(PlatformSupportTicket.objects.filter(pk=ticket_pk))
                    .first()
                )
                if not ticket:
                    continue
                # Re-verify SLA eligibility inside lock
                if ticket.status not in (PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM):
                    continue
                if ticket.sla_cycle_started_at is None or ticket.sla_cycle_started_at > cutoff:
                    continue
                if ticket.current_cycle_escalated:
                    continue
                # Confirm NO public platform reply occurred since cycle_started_at
                if PlatformSupportMessage.objects.filter(
                    ticket=ticket,
                    sender_type=PlatformTicketSenderType.PLATFORM,
                    is_internal_note=False,
                    created_at__gte=ticket.sla_cycle_started_at,
                ).exists():
                    ticket.sla_cycle_started_at = None
                    ticket.current_cycle_escalated = False
                    ticket.save(update_fields=['sla_cycle_started_at', 'current_cycle_escalated', 'updated_at'])
                    continue

                cycle_ts = ticket.sla_cycle_started_at
                try:
                    escalation, created = PlatformSupportEscalation.objects.get_or_create(
                        ticket=ticket,
                        cycle_started_at=cycle_ts,
                        defaults={
                            'escalated_to_email': alert_email,
                            'status': 'PENDING',
                            'reason': f"No public platform response within {threshold_minutes} minutes",
                        },
                    )
                except IntegrityError:
                    # Another concurrent worker inserted this cycle first
                    ticket.current_cycle_escalated = True
                    ticket.save(update_fields=['current_cycle_escalated', 'updated_at'])
                    continue

                if not created and escalation.status in ('SENT', 'CANCELLED'):
                    ticket.current_cycle_escalated = True
                    ticket.save(update_fields=['current_cycle_escalated', 'updated_at'])
                    continue

                wait_mins = max(threshold_minutes, int((now - cycle_ts).total_seconds() // 60))
                subject = f"[URGENT SLA] Support Ticket {ticket.ticket_number} Unanswered ({wait_mins}m) - {ticket.tenant.name}"
                body = (
                    f"Urgent Client Support Escalation ({threshold_minutes}-minute SLA exceeded)\n\n"
                    f"Ticket: {ticket.ticket_number}\n"
                    f"Tenant Workspace: {ticket.tenant.name}\n"
                    f"Category: {ticket.get_category_display()} | Priority: {ticket.get_priority_display()}\n"
                    f"Subject: {ticket.subject}\n"
                    f"Unanswered Since: {cycle_ts.isoformat()} ({wait_mins} minutes elapsed)\n\n"
                    f"Please reply in the Platform Support Console: https://wapp.neorizsolutions.com/app/platform/support\n"
                )
                email_job = queue_email(
                    None,
                    'SUPPORT_ESCALATION',
                    f"support-esc:{escalation.pk}",
                    {
                        'subject': subject,
                        'body': body,
                        'ticket_id': str(ticket.pk),
                        'escalation_id': str(escalation.pk),
                    },
                    tenant=ticket.tenant,
                    recipient=alert_email,
                )
                escalation.email_job = email_job
                escalation.save(update_fields=['email_job'])

                ticket.current_cycle_escalated = True
                ticket.escalations_count += 1
                ticket.save(update_fields=['current_cycle_escalated', 'escalations_count', 'updated_at'])

                TenantAuditLog.objects.create(
                    tenant=ticket.tenant,
                    actor=None,
                    action=AuditLogAction.PLATFORM_TICKET_ESCALATED,
                    summary=f"Escalated unanswered ticket {ticket.ticket_number} to {alert_email} ({wait_mins}m elapsed)",
                    details={
                        'ticket_id': str(ticket.pk),
                        'escalation_id': str(escalation.pk),
                        'cycle_started_at': cycle_ts.isoformat(),
                    },
                )
                if email_job:
                    queued_email_ids.append(email_job.pk)
                escalated_count += 1
        except Exception:
            logger.exception("Error processing support escalation for ticket %s", ticket_pk)

    if smtp_ready() and queued_email_ids:
        process_emails(limit=max(20, len(queued_email_ids)))

    return escalated_count
