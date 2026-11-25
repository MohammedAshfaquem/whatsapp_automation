"""
REST API endpoints for Release 2:
- Client-to-Platform Support (/api/support/tickets/...) strictly tenant-scoped, hiding internal notes
- Platform Operator Support Queue & Escalations (/api/platform/support/...) strictly platform-scoped
"""
import json
import logging
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.db.models import Q
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .capabilities import can_perform_action
from .models import (
    PlatformSupportMessage,
    PlatformSupportTicket,
    PlatformTicketCategory,
    PlatformTicketPriority,
    PlatformTicketStatus,
)
from .support_service import (
    SupportError,
    create_platform_ticket,
    get_support_sla_config,
    post_client_reply,
    post_platform_reply,
    update_client_ticket_status,
    update_platform_ticket,
)

User = get_user_model()
logger = logging.getLogger(__name__)


def _api_login_required(view_func):
    def _wrapped(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return view_func(request, *args, **kwargs)

    return _wrapped


def _parse_body(request):
    if request.content_type and 'multipart/form-data' in request.content_type:
        return request.POST.dict()
    if request.body:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            pass
    return request.POST.dict()


def _serialize_message(msg: PlatformSupportMessage, *, is_platform: bool) -> dict:
    att_url = None
    if msg.attachment_name and msg.attachment_key:
        if is_platform:
            att_url = f"/api/platform/support/tickets/{msg.ticket_id}/attachments/{msg.pk}/"
        else:
            att_url = f"/api/support/tickets/{msg.ticket_id}/attachments/{msg.pk}/"
    return {
        'id': str(msg.pk),
        'sender_name': (msg.sender.get_full_name() or msg.sender.username) if msg.sender else 'Neoriz System',
        'sender_username': msg.sender.username if msg.sender else 'system',
        'sender_type': msg.sender_type,
        'is_internal_note': msg.is_internal_note if is_platform else False,
        'body': msg.body,
        'attachment': (
            {
                'name': msg.attachment_name,
                'mime': msg.attachment_mime,
                'size': msg.attachment_size,
                'url': att_url,
            }
            if msg.attachment_name else None
        ),
        'created_at': msg.created_at.isoformat(),
    }


def _serialize_ticket(ticket: PlatformSupportTicket, *, include_internal: bool = False) -> dict:
    cfg = get_support_sla_config()
    now = timezone.now()
    sla_deadline = (
        ticket.sla_cycle_started_at + timedelta(minutes=cfg['threshold_minutes'])
        if ticket.sla_cycle_started_at else None
    )
    sla_breached = bool(
        ticket.sla_cycle_started_at
        and ticket.status in (PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM)
        and now >= sla_deadline
    )
    data = {
        'id': str(ticket.pk),
        'ticket_number': ticket.ticket_number,
        'tenant_id': ticket.tenant_id,
        'tenant_name': ticket.tenant.name,
        'subject': ticket.subject,
        'category': ticket.category,
        'category_display': ticket.get_category_display(),
        'priority': ticket.priority,
        'priority_display': ticket.get_priority_display(),
        'status': ticket.status,
        'status_display': ticket.get_status_display(),
        'created_by': ticket.created_by.username if ticket.created_by else None,
        'sla_cycle_started_at': ticket.sla_cycle_started_at.isoformat() if ticket.sla_cycle_started_at else None,
        'sla_deadline_at': sla_deadline.isoformat() if sla_deadline else None,
        'sla_breached': sla_breached,
        'sla_threshold_minutes': cfg['threshold_minutes'],
        'last_client_message_at': ticket.last_client_message_at.isoformat() if ticket.last_client_message_at else None,
        'first_platform_reply_at': ticket.first_platform_reply_at.isoformat() if ticket.first_platform_reply_at else None,
        'last_platform_reply_at': ticket.last_platform_reply_at.isoformat() if ticket.last_platform_reply_at else None,
        'resolved_at': ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        'closed_at': ticket.closed_at.isoformat() if ticket.closed_at else None,
        'created_at': ticket.created_at.isoformat(),
        'updated_at': ticket.updated_at.isoformat(),
    }
    if include_internal:
        data['assigned_to'] = (
            {'id': ticket.assigned_to.pk, 'username': ticket.assigned_to.username}
            if ticket.assigned_to else None
        )
        data['current_cycle_escalated'] = ticket.current_cycle_escalated
        data['escalations_count'] = ticket.escalations_count
        data['support_alert_email'] = cfg['alert_email']
    return data


# ---------------------------------------------------------------------------
# Client-Facing Help & Support Endpoints (/api/support/...)
# ---------------------------------------------------------------------------

@_api_login_required
@require_http_methods(['GET', 'POST'])
def client_support_tickets_api(request):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    action = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'help_support', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if request.method == 'GET':
        qs = PlatformSupportTicket.objects.filter(tenant=tenant).select_related('tenant', 'created_by')
        status_f = (request.GET.get('status') or '').strip().upper()
        if status_f:
            qs = qs.filter(status=status_f)
        q = (request.GET.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(ticket_number__icontains=q) | Q(subject__icontains=q))
        tickets = [_serialize_ticket(t, include_internal=False) for t in qs.order_by('-updated_at')[:100]]
        return JsonResponse({
            'tickets': tickets,
            'categories': [{'value': c.value, 'label': c.label} for c in PlatformTicketCategory],
            'priorities': [{'value': p.value, 'label': p.label} for p in PlatformTicketPriority],
            'sla_config': {'threshold_minutes': get_support_sla_config()['threshold_minutes']},
        })

    data = _parse_body(request)
    att = request.FILES.get('attachment')
    try:
        ticket = create_platform_ticket(
            tenant=tenant,
            user=request.user,
            subject=data.get('subject', ''),
            description=data.get('description') or data.get('message') or '',
            category=data.get('category', PlatformTicketCategory.META_SETUP),
            priority=data.get('priority', PlatformTicketPriority.NORMAL),
            attachment=att,
        )
    except SupportError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)

    return JsonResponse({
        'status': 'created',
        'ticket': _serialize_ticket(ticket, include_internal=False),
        'message': f"Support ticket {ticket.ticket_number} submitted. Unanswered inquiries trigger priority alert after 10 minutes.",
    }, status=201)


@_api_login_required
@require_GET
def client_support_ticket_detail_api(request, ticket_id):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    allowed, reason = can_perform_action(request.user, tenant, 'help_support', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    ticket = get_object_or_404(
        PlatformSupportTicket.objects.select_related('tenant', 'created_by'),
        pk=ticket_id,
        tenant=tenant,
    )
    # CRITICAL PRIVACY: exclude internal platform notes completely
    msgs = ticket.messages.filter(is_internal_note=False).select_related('sender').order_by('created_at')
    return JsonResponse({
        'ticket': _serialize_ticket(ticket, include_internal=False),
        'messages': [_serialize_message(m, is_platform=False) for m in msgs],
    })


@_api_login_required
@require_POST
def client_support_ticket_reply_api(request, ticket_id):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    allowed, reason = can_perform_action(request.user, tenant, 'help_support', 'edit')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    ticket = get_object_or_404(PlatformSupportTicket, pk=ticket_id, tenant=tenant)
    data = _parse_body(request)
    att = request.FILES.get('attachment')
    try:
        msg = post_client_reply(
            ticket=ticket,
            tenant=tenant,
            user=request.user,
            body=data.get('body') or data.get('message') or '',
            attachment=att,
        )
    except SupportError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    ticket.refresh_from_db()
    return JsonResponse({
        'status': 'replied',
        'message_item': _serialize_message(msg, is_platform=False),
        'ticket': _serialize_ticket(ticket, include_internal=False),
    }, status=201)


@_api_login_required
@require_POST
def client_support_ticket_status_api(request, ticket_id):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    allowed, reason = can_perform_action(request.user, tenant, 'help_support', 'resolve')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    ticket = get_object_or_404(PlatformSupportTicket, pk=ticket_id, tenant=tenant)
    data = _parse_body(request)
    try:
        updated = update_client_ticket_status(
            ticket=ticket,
            tenant=tenant,
            user=request.user,
            action=(data.get('action') or '').strip().lower(),
        )
    except SupportError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    return JsonResponse({'status': 'updated', 'ticket': _serialize_ticket(updated, include_internal=False)})


@_api_login_required
@require_GET
def client_support_attachment_api(request, ticket_id, message_id):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        raise Http404
    allowed, _ = can_perform_action(request.user, tenant, 'help_support', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied'}, status=403)
    msg = get_object_or_404(
        PlatformSupportMessage,
        pk=message_id,
        ticket_id=ticket_id,
        ticket__tenant=tenant,
        is_internal_note=False,
    )
    if not msg.attachment_key or not default_storage.exists(msg.attachment_key):
        raise Http404
    return FileResponse(
        default_storage.open(msg.attachment_key, 'rb'),
        as_attachment=True,
        filename=msg.attachment_name,
        content_type=msg.attachment_mime or 'application/octet-stream',
    )


# ---------------------------------------------------------------------------
# Platform Support Queue & SLA Endpoints (/api/platform/support/...)
# ---------------------------------------------------------------------------

@_api_login_required
@require_GET
def platform_support_tickets_api(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    cfg = get_support_sla_config()
    cutoff = timezone.now() - timedelta(minutes=cfg['threshold_minutes'])
    qs = PlatformSupportTicket.objects.select_related('tenant', 'created_by', 'assigned_to').order_by('-updated_at')

    status_f = (request.GET.get('status') or '').strip().upper()
    if status_f == 'BREACHED':
        qs = qs.filter(
            status__in=[PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM],
            sla_cycle_started_at__isnull=False,
            sla_cycle_started_at__lte=cutoff,
        )
    elif status_f == 'ESCALATED':
        qs = qs.filter(escalations_count__gt=0)
    elif status_f:
        qs = qs.filter(status=status_f)

    priority_f = (request.GET.get('priority') or '').strip().upper()
    if priority_f:
        qs = qs.filter(priority=priority_f)
    category_f = (request.GET.get('category') or '').strip().upper()
    if category_f:
        qs = qs.filter(category=category_f)
    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(Q(ticket_number__icontains=q) | Q(subject__icontains=q) | Q(tenant__name__icontains=q))

    all_rows = PlatformSupportTicket.objects.all()
    counts = {
        'total': all_rows.count(),
        'open': all_rows.filter(status__in=[PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM]).count(),
        'awaiting_client': all_rows.filter(status=PlatformTicketStatus.AWAITING_CLIENT).count(),
        'breached': all_rows.filter(
            status__in=[PlatformTicketStatus.OPEN, PlatformTicketStatus.AWAITING_PLATFORM],
            sla_cycle_started_at__isnull=False,
            sla_cycle_started_at__lte=cutoff,
        ).count(),
        'escalated': all_rows.filter(escalations_count__gt=0).count(),
        'resolved': all_rows.filter(status__in=[PlatformTicketStatus.RESOLVED, PlatformTicketStatus.CLOSED]).count(),
    }
    operators = [
        {'id': u.pk, 'username': u.username, 'full_name': u.get_full_name() or u.username}
        for u in User.objects.filter(is_superuser=True, is_active=True).order_by('username')
    ]
    return JsonResponse({
        'tickets': [_serialize_ticket(t, include_internal=True) for t in qs[:100]],
        'counts': counts,
        'operators': operators,
        'sla_config': cfg,
    })


@_api_login_required
@require_GET
def platform_support_ticket_detail_api(request, ticket_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    ticket = get_object_or_404(
        PlatformSupportTicket.objects.select_related('tenant', 'created_by', 'assigned_to'),
        pk=ticket_id,
    )
    msgs = ticket.messages.select_related('sender').order_by('created_at')
    escalations = [
        {
            'id': str(e.pk),
            'cycle_started_at': e.cycle_started_at.isoformat(),
            'escalated_to_email': e.escalated_to_email,
            'status': e.status,
            'reason': e.reason,
            'email_status': e.email_job.status if e.email_job else None,
            'sent_at': e.sent_at.isoformat() if e.sent_at else None,
            'created_at': e.created_at.isoformat(),
        }
        for e in ticket.escalations.select_related('email_job').order_by('-created_at')
    ]
    return JsonResponse({
        'ticket': _serialize_ticket(ticket, include_internal=True),
        'messages': [_serialize_message(m, is_platform=True) for m in msgs],
        'escalations': escalations,
    })


@_api_login_required
@require_POST
def platform_support_ticket_reply_api(request, ticket_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    ticket = get_object_or_404(PlatformSupportTicket, pk=ticket_id)
    data = _parse_body(request)
    is_internal = bool(data.get('is_internal_note') is True or str(data.get('is_internal_note')).lower() == 'true')
    try:
        msg = post_platform_reply(
            ticket=ticket,
            operator=request.user,
            body=data.get('body') or data.get('message') or '',
            is_internal_note=is_internal,
            new_status=data.get('status') or None,
        )
    except SupportError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    ticket.refresh_from_db()
    return JsonResponse({
        'status': 'replied',
        'message_item': _serialize_message(msg, is_platform=True),
        'ticket': _serialize_ticket(ticket, include_internal=True),
    }, status=201)


@_api_login_required
@require_http_methods(['PATCH', 'POST'])
def platform_support_ticket_update_api(request, ticket_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    ticket = get_object_or_404(PlatformSupportTicket, pk=ticket_id)
    data = _parse_body(request)
    try:
        updated = update_platform_ticket(
            ticket=ticket,
            operator=request.user,
            status=data.get('status') if 'status' in data else None,
            priority=data.get('priority') if 'priority' in data else None,
            assigned_to_id=data.get('assigned_to_id') if 'assigned_to_id' in data else None,
        )
    except SupportError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    return JsonResponse({'status': 'updated', 'ticket': _serialize_ticket(updated, include_internal=True)})


@_api_login_required
@require_GET
def platform_support_attachment_api(request, ticket_id, message_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    msg = get_object_or_404(PlatformSupportMessage, pk=message_id, ticket_id=ticket_id)
    if not msg.attachment_key or not default_storage.exists(msg.attachment_key):
        raise Http404
    return FileResponse(
        default_storage.open(msg.attachment_key, 'rb'),
        as_attachment=True,
        filename=msg.attachment_name,
        content_type=msg.attachment_mime or 'application/octet-stream',
    )
