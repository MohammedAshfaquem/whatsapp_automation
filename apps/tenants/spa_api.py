"""
RESTful JSON API endpoints supporting the Neoriz WhatsApp Automation React Single Page Application (SPA).
Enforces session authentication, CSRF validation, strict multi-tenant scoping, and authoritative capability checks.
"""

import json
import logging
from decimal import Decimal
from datetime import timedelta

from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from functools import wraps
from apps.tenants.meta_setup import meta_setup_state, verify_meta_connection, valid_whatsapp_number

def api_login_required(view_func):
    """Decorator ensuring request is authenticated, returning 401 JSON on failure."""
    @wraps(view_func)
    def _wrapped(request, *args, **kwargs):
        if not request.user or not request.user.is_authenticated:
            return JsonResponse({'error': 'Authentication required'}, status=401)
        return view_func(request, *args, **kwargs)
    return _wrapped

from django.contrib.auth.models import User
from django.utils import timezone
from django.utils.text import slugify
from django.db import transaction, IntegrityError
from django.db.models import Q, Sum, Count
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import ensure_csrf_cookie

from apps.tenants.models import (
    Tenant, TenantMembership, TenantInvitation, TenantAuditLog,
    TenantRole, MembershipRole, SubscriptionStatus, PlanTier,
    UserSecurityProfile, TenantFeatureOverride, AuditLogAction,
    StaffAccessRequest, StaffRequestStatus, AccountActivationToken
)
from apps.tenants.capabilities import (
    can_access_capability, can_perform_action, CAPABILITY_REGISTRY
)
from apps.tenants.context import set_current_tenant, clear_current_tenant, user_can_manage_tenant
from apps.chatbot.models import (
    Customer, Conversation, Message, ConversationStatus,
    ChannelChoice, MessageDirection, SenderType, ProcessingStatus
)
from apps.bookings.models import Booking, BookingStatus
from apps.services.models import Service, PriceType
from apps.business.models import BusinessProfile
from apps.knowledge_base.models import FAQ, KnowledgeDocument, DocumentCategory
from apps.whatsapp.models import WhatsAppConfig, WhatsAppDelivery, WhatsAppBusinessProfile
from apps.whatsapp.whatsapp_client import WhatsAppClient
from apps.whatsapp.delivery import dispatch
from apps.tenants.media_api import whatsapp_profile_media_url
from apps.crm.models import (
    Company, Pipeline, Deal, DealStage,
    Activity, ActivityType, ActivityStatus, ActivityPriority, ContactNote,
    WhatsAppTemplate
)
from apps.crm.services import (
    get_crm_metrics, get_customer_timeline, change_deal_stage, normalize_phone_number,
    merge_contacts, get_activities_for_tenant
)

logger = logging.getLogger(__name__)


def _parse_body(request):
    """Safely parse JSON request body or fall back to request.POST."""
    if request.body:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            pass
    return request.POST.dict()


# =====================================================================
# 1. SESSION & BOOTSTRAP API
# =====================================================================

@ensure_csrf_cookie
@api_login_required
@require_GET
def session_bootstrap_api(request):
    """
    Returns complete authentication context, active tenant, memberships,
    evaluated capabilities, and resource usage for the React application.
    """
    user = request.user
    tenant = getattr(request, 'tenant', None)
    membership = getattr(request, 'membership', None)
    is_inspecting = getattr(request, 'is_inspecting', False)

    # 1. User details
    from .platform_auth import get_platform_role
    sec_profile = UserSecurityProfile.get_or_create_for_user(user)
    platform_role = get_platform_role(user)
    user_data = {
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'first_name': user.first_name,
        'last_name': user.last_name,
        'full_name': user.get_full_name() or user.username,
        'is_staff': user.is_staff,
        'is_superuser': user.is_superuser,
        'platform_role': platform_role,
        'is_platform_operator': bool(platform_role),
        'email_verified': sec_profile.email_verified,
        'mailbox_gate_exempt': sec_profile.skip_mailbox_gate,
        'internal_identifier': sec_profile.internal_identifier or '',
        'is_synthetic_identifier': sec_profile.is_synthetic_identifier,
        'recovery_email': sec_profile.recovery_email,
        'recovery_email_verified': sec_profile.recovery_email_verified,
        'pending_recovery_email': sec_profile.pending_recovery_email,
    }

    # 2. Memberships / Workspaces available to user
    memberships = list(
        TenantMembership.objects.filter(user=user, is_active=True, tenant__is_active=True)
        .select_related('tenant')
        .order_by('tenant__name')
    )
    user_tenants = [
        {
            'id': m.tenant.id,
            'name': m.tenant.name,
            'slug': m.tenant.slug,
            'role': m.role,
            'role_display': m.get_role_display(),
        }
        for m in memberships
    ]

    # 3. Active Tenant details
    tenant_data = None
    if tenant:
        sub = getattr(tenant, 'subscription', None)
        plan = sub.effective_plan if sub else None
        tenant_data = {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo_url': tenant.effective_logo_url,
            'logo_source_url': '' if (tenant.logo_url or '').startswith('s3://') else (tenant.logo_url or ''),
            'timezone': tenant.timezone,
            'contact_email': tenant.contact_email,
            'contact_phone': tenant.contact_phone,
            'whatsapp_number': tenant.whatsapp_number,
            'meta_setup_required': meta_setup_state(tenant)['required'],
            'meta_setup_ready': meta_setup_state(tenant)['ready'],
            'meta_setup_reason': meta_setup_state(tenant)['reason'],
            'plan': plan.code if plan else tenant.plan,
            'plan_name': plan.name if plan else tenant.get_plan_display(),
            'subscription_status': sub.status if sub else 'ACTIVE',
            'grace_until': sub.grace_until.isoformat() if sub and sub.grace_until else None,
            'is_in_grace': bool(sub and sub.is_in_grace),
            'outbound_paused': tenant.outbound_paused,
            'outbound_pause_reason': tenant.outbound_pause_reason,
            'is_active': tenant.is_active,
        }

    # 4. Active Role
    membership_data = None
    if membership:
        membership_data = {
            'role': membership.role,
            'role_display': membership.get_role_display(),
            'is_admin': membership.is_owner_or_admin,
            'is_owner': membership.role == MembershipRole.OWNER,
        }
    elif user.is_superuser:
        membership_data = {
            'role': 'SUPERUSER',
            'role_display': 'Super Admin' if not is_inspecting else f'Super Admin (Inspecting {tenant.name if tenant else ""})',
            'is_admin': True,
            'is_owner': True,
        }

    # 5. Authoritative Capabilities Map
    capabilities = {}
    for cap_key in CAPABILITY_REGISTRY.keys():
        allowed, reason = can_access_capability(user, tenant, cap_key)
        capabilities[cap_key] = {
            'allowed': allowed,
            'reason': reason,
        }

    # 6. Usage Quotas & Allowances
    usage_data = None
    if tenant:
        now = timezone.now()
        monthly_usage = tenant.monthly_usages.filter(year=now.year, month=now.month).first()
        messages_sent = monthly_usage.outbound_messages_sent if monthly_usage else 0
        messages_allowance = tenant.effective_monthly_message_allowance

        active_docs = tenant.documents.filter(is_active=True).count()
        max_docs = tenant.effective_max_documents

        active_contacts = Customer.objects.filter(tenant=tenant).count()
        max_contacts = tenant.effective_max_contacts

        active_staff = tenant.memberships.filter(is_active=True).count()
        max_staff = tenant.effective_max_staff

        usage_data = {
            'messages': {
                'sent': messages_sent,
                'allowance': messages_allowance,
                'remaining': max(0, messages_allowance - messages_sent),
                'percent': min(100, int((messages_sent / messages_allowance * 100))) if messages_allowance > 0 else 0,
            },
            'documents': {
                'count': active_docs,
                'limit': max_docs,
                'remaining': max(0, max_docs - active_docs),
            },
            'contacts': {
                'count': active_contacts,
                'limit': max_contacts,
                'remaining': max(0, max_contacts - active_contacts),
            },
            'staff': {
                'count': active_staff,
                'limit': max_staff,
                'remaining': max(0, max_staff - active_staff),
            },
            'alerts': [
                {
                    'resource': label,
                    'used': used,
                    'limit': limit,
                    'percent': int(round((used / limit) * 100)) if limit else 0,
                    'level': 'EXCEEDED' if used >= limit else 'WARNING',
                    'message': f"{label} usage at {used}/{limit} ({int(round((used / limit) * 100))}%).",
                }
                for label, used, limit in (
                    ('Messages', messages_sent, messages_allowance),
                    ('Contacts', active_contacts, max_contacts),
                    ('Documents', active_docs, max_docs),
                    ('Staff seats', active_staff, max_staff),
                )
                if limit > 0 and (used * 100 >= limit * 80)
            ],
        }

    return JsonResponse({
        'user': user_data,
        'tenant': tenant_data,
        'membership': membership_data,
        'user_tenants': user_tenants,
        'is_super_admin': user.is_superuser,
        'is_inspecting': is_inspecting,
        'inspected_tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo_url': tenant.effective_logo_url
        } if is_inspecting and tenant else None,
        'capabilities': capabilities,
        'usage': usage_data,
        'setup_checklist': _evaluate_setup_checklist(user, tenant) if tenant else None,
    })


@api_login_required
@require_POST
def switch_tenant_api(request):
    """Switch active tenant context in session."""
    data = _parse_body(request)
    tenant_id = data.get('tenant_id')
    if not tenant_id:
        return JsonResponse({'error': 'tenant_id is required'}, status=400)

    try:
        tenant_id = int(tenant_id)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid tenant_id'}, status=400)

    tenant = get_object_or_404(Tenant, id=tenant_id, is_active=True)

    if not request.user.is_superuser:
        has_membership = TenantMembership.objects.filter(
            tenant=tenant, user=request.user, is_active=True
        ).exists()
        if not has_membership:
            return JsonResponse({'error': 'You do not have access to that workspace.'}, status=403)

    request.session['active_tenant_id'] = tenant.id
    request.session.pop('inspecting_tenant_id', None)
    set_current_tenant(tenant)

    return JsonResponse({'status': 'ok', 'active_tenant_id': tenant.id, 'name': tenant.name})


@api_login_required
@require_POST
def platform_inspect_api(request, tenant_id):
    """Superuser: Enter tenant inspection mode."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Superuser privileges required.'}, status=403)

    tenant = get_object_or_404(Tenant, id=tenant_id, is_active=True)
    request.session['inspecting_tenant_id'] = tenant.id
    set_current_tenant(tenant)

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_INSPECTED,
        summary=f"Superadmin @{request.user.username} entered inspection mode for '{tenant.name}'",
        details={'tenant_id': tenant.id, 'tenant_name': tenant.name}
    )

    return JsonResponse({'status': 'ok', 'inspecting_tenant_id': tenant.id, 'name': tenant.name})


@api_login_required
@require_POST
def platform_exit_inspect_api(request):
    """Superuser: Exit tenant inspection mode."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Superuser privileges required.'}, status=403)

    request.session.pop('inspecting_tenant_id', None)
    request.session.pop('active_tenant_id', None)
    clear_current_tenant()

    return JsonResponse({'status': 'ok', 'message': 'Exited inspection mode.'})


# =====================================================================
# 2. CRM APIS (Contacts, Companies, Deals, Activities, Timeline)
# =====================================================================

@api_login_required
@require_GET
def crm_overview_api(request):
    """Summary metrics for the CRM dashboard view."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    metrics = get_crm_metrics(tenant)
    recent_activities = (
        Activity.objects.filter(tenant=tenant)
        .select_related('contact', 'assigned_to')
        .order_by('-due_date')[:5]
    )
    activities_data = [
        {
            'id': a.id,
            'title': a.title,
            'activity_type': a.activity_type,
            'status': a.status,
            'priority': a.priority,
            'due_date': a.due_date.isoformat() if a.due_date else None,
            'customer_name': a.contact.name if a.contact else None,
            'assigned_to': a.assigned_to.get_full_name() or a.assigned_to.username if a.assigned_to else None,
        }
        for a in recent_activities
    ]

    return JsonResponse({
        'metrics': metrics,
        'recent_activities': activities_data,
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def crm_contacts_api(request):
    """List or create CRM contacts."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if request.method == 'GET':
        qs = Customer.objects.filter(tenant=tenant).select_related('company', 'user').order_by('-updated_at')
        query = request.GET.get('q', '').strip()
        if query:
            qs = qs.filter(
                Q(name__icontains=query) |
                Q(phone_number__icontains=query) |
                Q(email__icontains=query)
            )

        company_id = request.GET.get('company')
        if company_id:
            qs = qs.filter(company_id=company_id)

        tag_filter = request.GET.get('tag', '').strip()
        if tag_filter:
            from django.db import connection
            if connection.vendor == 'postgresql':
                qs = qs.filter(tags__contains=[tag_filter])
            else:
                tag_lower = tag_filter.casefold()
                matching_ids = [
                    cid for cid, c_tags in qs.values_list('pk', 'tags')
                    if isinstance(c_tags, list) and any(str(t).strip().casefold() == tag_lower for t in c_tags)
                ]
                qs = qs.filter(pk__in=matching_ids)

        contacts = [
            {
                'id': c.id,
                'name': c.name or 'Unnamed Contact',
                'phone_number': c.phone_number,
                'email': c.email or '',
                'company': {
                    'id': c.company.id,
                    'name': c.company.name,
                } if c.company else None,
                'lifecycle_stage': c.lifecycle_status,
                'lifecycle_status': c.lifecycle_status,
                'tags': c.tags if isinstance(c.tags, list) else [],
                'custom_fields': c.custom_fields if isinstance(c.custom_fields, dict) else {},
                'lead_score': getattr(getattr(c, 'lead_score', None), 'score', 0),
                'created_at': c.created_at.isoformat(),
                'updated_at': c.updated_at.isoformat(),
            }
            for c in qs[:100]
        ]
        return JsonResponse({'contacts': contacts, 'total': qs.count()})

    # POST: Create contact
    if tenant and not tenant.can_add_contact():
        return JsonResponse({
            'error': f"Contact limit reached ({tenant.effective_max_contacts} contacts). Please upgrade your plan."
        }, status=400)

    data = _parse_body(request)
    name = data.get('name', '').strip()
    phone = data.get('phone_number', '').strip()
    email = data.get('email', '').strip()
    company_id = data.get('company_id')

    if not phone:
        return JsonResponse({'error': 'Phone number is required.'}, status=400)

    clean_phone = normalize_phone_number(phone)

    # Check for existing contact with same phone in tenant
    existing = Customer.objects.filter(tenant=tenant, phone_number=clean_phone).first()
    if existing:
        return JsonResponse({'error': f"A contact with phone {clean_phone} already exists."}, status=409)

    company = None
    if company_id:
        company = get_object_or_404(Company, id=company_id, tenant=tenant)

    raw_tags = data.get('tags', [])
    if isinstance(raw_tags, str):
        clean_tags = list(dict.fromkeys([t.strip()[:40] for t in raw_tags.split(',') if t.strip()]))[:30]
    elif isinstance(raw_tags, list):
        clean_tags = list(dict.fromkeys([str(t).strip()[:40] for t in raw_tags if str(t).strip()]))[:30]
    else:
        clean_tags = []
    raw_cf = data.get('custom_fields', {})
    clean_cf = (
        {str(k).strip()[:50]: str(v)[:250] for k, v in raw_cf.items() if str(k).strip()}
        if isinstance(raw_cf, dict) else {}
    )

    contact = Customer.objects.create(
        tenant=tenant,
        name=name or clean_phone,
        phone_number=clean_phone,
        email=email,
        company=company,
        lifecycle_status=data.get('lifecycle_stage') or data.get('lifecycle_status', 'LEAD'),
        tags=clean_tags,
        custom_fields=clean_cf,
    )

    try:
        from apps.crm.automation_engine import record_business_event, process_pending_business_events
        record_business_event(
            tenant=tenant,
            event_type='lead.created',
            entity_type='contact',
            entity_id=contact.id,
            payload={
                'name': contact.name,
                'phone': contact.phone_number,
                'email': contact.email,
                'lifecycle_status': contact.lifecycle_status,
            },
            dedup_key=f"contact:{contact.id}:created"
        )
        transaction.on_commit(lambda: process_pending_business_events(tenant=tenant))
    except Exception:
        pass

    return JsonResponse({
        'status': 'created',
        'contact': {
            'id': contact.id,
            'name': contact.name,
            'phone_number': contact.phone_number,
            'email': contact.email,
        }
    }, status=201)


@api_login_required
@require_http_methods(['GET', 'PATCH', 'DELETE'])
def crm_contact_detail_api(request, contact_id):
    """Retrieve, update, or delete a single contact with timeline."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else ('edit' if request.method == 'PATCH' else 'delete')
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    contact = get_object_or_404(Customer.objects.select_related('company', 'owner'), id=contact_id, tenant=tenant)

    if request.method == 'GET':
        timeline_dict = get_customer_timeline(contact)
        timeline_items = timeline_dict.get('items', []) if isinstance(timeline_dict, dict) else (timeline_dict or [])
        notes = list(contact.internal_notes.select_related('author').order_by('-created_at').values(
            'id', 'content', 'created_at', 'author__username'
        ))
        deals = [
            {
                'id': d.id,
                'title': d.title,
                'amount': float(d.amount) if d.amount else 0.0,
                'value': float(d.amount) if d.amount else 0.0,
                'currency': d.currency,
                'stage_name': d.stage.name if d.stage else '',
                'is_won': d.stage.is_won if d.stage else False,
                'is_lost': d.stage.is_lost if d.stage else False,
                'status': 'WON' if (d.stage and d.stage.is_won) else ('LOST' if (d.stage and d.stage.is_lost) else 'OPEN'),
            }
            for d in contact.deals.select_related('stage').all()
        ]
        activities = [
            {
                'id': a.id,
                'title': a.title,
                'activity_type': a.activity_type,
                'activity_type_display': a.get_activity_type_display(),
                'status': a.status,
                'priority': a.priority,
                'due_date': a.due_date.isoformat() if a.due_date else None,
                'is_overdue': a.is_overdue,
                'assigned_to': a.assigned_to.get_full_name() or a.assigned_to.username if a.assigned_to else None,
            }
            for a in contact.activities.select_related('assigned_to').order_by('due_date')
        ]

        return JsonResponse({
            'contact': {
                'id': contact.id,
                'name': contact.name,
                'phone_number': contact.phone_number,
                'email': contact.email,
                'company': {
                    'id': contact.company.id,
                    'name': contact.company.name,
                } if contact.company else None,
                'owner': {
                    'id': contact.owner.id,
                    'name': contact.owner.get_full_name() or contact.owner.username,
                    'username': contact.owner.username,
                } if contact.owner else None,
                'lifecycle_stage': contact.lifecycle_status,
                'lifecycle_status': contact.lifecycle_status,
                'tags': contact.tags if isinstance(contact.tags, list) else [],
                'custom_fields': contact.custom_fields if isinstance(contact.custom_fields, dict) else {},
                'notes': contact.notes or '',
                'lead_score': getattr(getattr(contact, 'lead_score', None), 'score', 0),
                'created_at': contact.created_at.isoformat(),
            },
            'timeline': timeline_dict,
            'timeline_items': timeline_items,
            'notes': notes,
            'deals': deals,
            'activities': activities,
        })

    if request.method == 'PATCH':
        data = _parse_body(request)
        if 'name' in data:
            contact.name = str(data['name'] or '').strip()[:150]
        if 'email' in data:
            contact.email = str(data['email'] or '').strip()[:254]
        stage_val = data.get('lifecycle_status', data.get('lifecycle_stage'))
        if stage_val:
            contact.lifecycle_status = str(stage_val).strip()
        if 'notes' in data:
            contact.notes = str(data['notes'] or '')[:4000]
        if 'tags' in data:
            raw_t = data['tags']
            if isinstance(raw_t, str):
                contact.tags = list(dict.fromkeys([t.strip()[:40] for t in raw_t.split(',') if t.strip()]))[:30]
            elif isinstance(raw_t, list):
                contact.tags = list(dict.fromkeys([str(t).strip()[:40] for t in raw_t if str(t).strip()]))[:30]
        if 'custom_fields' in data and isinstance(data['custom_fields'], dict):
            cleaned = {str(k).strip()[:50]: str(v)[:250] for k, v in data['custom_fields'].items() if str(k).strip()}
            contact.custom_fields = dict(list(cleaned.items())[:30])
        if 'company_id' in data:
            cid = data['company_id']
            contact.company = get_object_or_404(Company, id=cid, tenant=tenant) if cid else None
        contact.save()
        return JsonResponse({
            'status': 'updated',
            'tags': contact.tags,
            'custom_fields': contact.custom_fields,
            'lifecycle_status': contact.lifecycle_status,
        })

    # DELETE
    contact.delete()
    return JsonResponse({'status': 'deleted'})


@api_login_required
@require_POST
def crm_contact_note_add_api(request, contact_id):
    """Add an internal staff note to a contact."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', 'edit')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    contact = get_object_or_404(Customer, id=contact_id, tenant=tenant)
    data = _parse_body(request)
    content = data.get('content', '').strip()
    if not content:
        return JsonResponse({'error': 'Note content is required.'}, status=400)

    note = ContactNote.objects.create(
        tenant=tenant,
        contact=contact,
        author=request.user,
        content=content
    )
    return JsonResponse({
        'status': 'created',
        'note': {
            'id': note.id,
            'content': note.content,
            'created_at': note.created_at.isoformat(),
            'author__username': request.user.username,
        }
    }, status=201)


@api_login_required
@require_POST
def crm_contact_merge_api(request):
    """Merge two duplicate contacts."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'contacts', 'delete')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    data = _parse_body(request)
    primary_id = data.get('primary_id')
    duplicate_id = data.get('duplicate_id')
    if not primary_id or not duplicate_id:
        return JsonResponse({'error': 'Both primary_id and duplicate_id are required.'}, status=400)
    if str(primary_id) == str(duplicate_id):
        return JsonResponse({'error': 'Cannot merge a contact into itself.'}, status=400)

    primary = get_object_or_404(Customer, id=primary_id, tenant=tenant)
    duplicate = get_object_or_404(Customer, id=duplicate_id, tenant=tenant)

    merged = merge_contacts(tenant, primary, duplicate, performed_by=request.user)
    return JsonResponse({
        'status': 'merged',
        'primary_id': merged.id,
        'message': f"Merged contact #{duplicate.id} into #{primary.id} with full history preserved."
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def crm_companies_api(request):
    """List or create companies."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'companies', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if request.method == 'GET':
        companies = list(Company.objects.filter(tenant=tenant).annotate(
            contact_count=Count('contacts'),
            deal_count=Count('deals')
        ).values('id', 'name', 'domain', 'industry', 'contact_count', 'deal_count'))
        return JsonResponse({'companies': companies})

    data = _parse_body(request)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Company name is required.'}, status=400)

    company = Company.objects.create(
        tenant=tenant,
        name=name,
        domain=data.get('domain', '').strip(),
        industry=data.get('industry', '').strip(),
        phone=data.get('phone', '').strip()
    )
    return JsonResponse({'status': 'created', 'company': {'id': company.id, 'name': company.name}}, status=201)


@api_login_required
@require_http_methods(['GET', 'POST'])
def crm_deals_api(request):
    """List deals (grouped by stage for Kanban) or create deal."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'deals', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    # Resolve default pipeline
    pipeline = Pipeline.objects.filter(tenant=tenant, is_default=True).first()
    if not pipeline:
        pipeline = Pipeline.objects.filter(tenant=tenant).first()
    if not pipeline and tenant:
        pipeline = Pipeline.objects.create(tenant=tenant, name='Standard Sales Pipeline', is_default=True)
        # Create default stages
        default_stages = [
            ('Lead Qualified', 1, 10, False, False),
            ('Consultation Scheduled', 2, 30, False, False),
            ('Proposal Sent', 3, 60, False, False),
            ('Negotiation', 4, 80, False, False),
            ('Closed Won', 5, 100, True, False),
            ('Closed Lost', 6, 0, False, True),
        ]
        for name, order, prob, won, lost in default_stages:
            DealStage.objects.create(
                pipeline=pipeline, name=name, order=order,
                probability=prob, is_won=won, is_lost=lost
            )

    if request.method == 'GET':
        stages = DealStage.objects.filter(pipeline=pipeline).order_by('order') if pipeline else []
        stages_data = []
        for stage in stages:
            deals = stage.deals.filter(tenant=tenant).select_related('contact', 'owner')
            deals_list = [
                {
                    'id': d.id,
                    'title': d.title,
                    'amount': float(d.amount or 0),
                    'value': str(d.amount or 0),
                    'currency': d.currency,
                    'customer_name': d.contact.name if d.contact else None,
                    'customer_phone': d.contact.phone_number if d.contact else None,
                    'contact_id': d.contact.id if d.contact else None,
                    'assigned_to': d.owner.get_full_name() or d.owner.username if d.owner else None,
                    'owner_id': d.owner.id if d.owner else None,
                    'expected_close_date': d.expected_close_date.isoformat() if d.expected_close_date else None,
                    'win_probability': d.probability or stage.probability,
                    'status': 'WON' if stage.is_won else ('LOST' if stage.is_lost else 'OPEN'),
                }
                for d in deals
            ]
            stage_total = deals.aggregate(total=Sum('amount'))['total'] or 0
            stages_data.append({
                'id': stage.id,
                'name': stage.name,
                'order': stage.order,
                'win_probability': stage.probability,
                'is_won': stage.is_won,
                'is_lost': stage.is_lost,
                'deals': deals_list,
                'deal_count': len(deals_list),
                'total_value': str(stage_total),
            })
        return JsonResponse({'pipeline': pipeline.name if pipeline else 'Default', 'stages': stages_data})

    # POST: Create deal
    data = _parse_body(request)
    title = data.get('title', '').strip()
    value = data.get('value') or data.get('amount') or '0'
    customer_id = data.get('customer_id') or data.get('contact_id')
    stage_id = data.get('stage_id')

    if not title:
        return JsonResponse({'error': 'Deal title is required.'}, status=400)

    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant) if customer_id else None
    if not customer:
        return JsonResponse({'error': 'A contact is required to create a deal.'}, status=400)

    stage = get_object_or_404(DealStage, id=stage_id, pipeline=pipeline) if stage_id else pipeline.stages.first()

    deal = Deal.objects.create(
        tenant=tenant,
        pipeline=pipeline,
        stage=stage,
        contact=customer,
        title=title,
        amount=Decimal(str(value)),
        owner=request.user
    )

    return JsonResponse({
        'status': 'created',
        'deal': {'id': deal.id, 'title': deal.title, 'value': str(deal.amount or 0)}
    }, status=201)


@api_login_required
@require_POST
def crm_deal_stage_api(request, deal_id):
    """Change the stage of a deal."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'deals', 'change_stage')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    deal = get_object_or_404(Deal, id=deal_id, tenant=tenant)
    data = _parse_body(request)
    target_stage_id = data.get('stage_id')
    notes = data.get('notes', '')

    target_stage = get_object_or_404(DealStage, id=target_stage_id, pipeline=deal.pipeline)
    lost_reason = data.get('lost_reason', '')
    deal = change_deal_stage(deal.id, target_stage.id, user=request.user, notes=notes, lost_reason=lost_reason)

    deal_status = 'WON' if target_stage.is_won else ('LOST' if target_stage.is_lost else 'OPEN')
    return JsonResponse({'status': 'ok', 'stage': target_stage.name, 'deal_status': deal_status})


@api_login_required
@require_http_methods(['GET', 'POST'])
def crm_activities_api(request):
    """List or create CRM activities."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'tasks', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if request.method == 'GET':
        filter_view = request.GET.get('filter') or request.GET.get('filter_view')
        if filter_view in ['my_tasks', 'today', 'upcoming', 'overdue', 'completed']:
            qs = get_activities_for_tenant(tenant, user=request.user, filter_view=filter_view)
        else:
            qs = Activity.objects.filter(tenant=tenant).select_related('contact', 'assigned_to')
            status_filter = request.GET.get('status')
            if status_filter:
                qs = qs.filter(status=status_filter)

        activities = [
            {
                'id': a.id,
                'title': a.title,
                'activity_type': a.activity_type,
                'activity_type_display': a.get_activity_type_display(),
                'status': a.status,
                'priority': a.priority,
                'due_date': a.due_date.isoformat() if a.due_date else None,
                'is_overdue': a.is_overdue,
                'customer_name': a.contact.name if a.contact else None,
                'customer_phone': a.contact.phone_number if a.contact else None,
                'assigned_to': a.assigned_to.get_full_name() or a.assigned_to.username if a.assigned_to else None,
            }
            for a in qs.order_by('due_date')[:100]
        ]
        return JsonResponse({'activities': activities})

    # POST: Create activity
    data = _parse_body(request)
    title = data.get('title', '').strip()
    customer_id = data.get('customer_id')

    if not title:
        return JsonResponse({'error': 'Activity title is required.'}, status=400)

    contact_id = data.get('contact_id') or customer_id
    contact = get_object_or_404(Customer, id=contact_id, tenant=tenant) if contact_id else None

    due_date_raw = data.get('due_date')
    due_date = None
    if due_date_raw:
        from django.utils.dateparse import parse_datetime, parse_date
        due_date = parse_datetime(due_date_raw)
        if not due_date:
            parsed_d = parse_date(due_date_raw)
            if parsed_d:
                import datetime
                due_date = timezone.make_aware(datetime.datetime.combine(parsed_d, datetime.time(23, 59, 59)))

    activity = Activity.objects.create(
        tenant=tenant,
        contact=contact,
        title=title,
        activity_type=data.get('activity_type', ActivityType.TASK),
        priority=data.get('priority', ActivityPriority.MEDIUM),
        assigned_to=request.user,
        due_date=due_date,
        notes=data.get('description', '') or data.get('notes', '')
    )
    return JsonResponse({'status': 'created', 'activity': {'id': activity.id, 'title': activity.title}}, status=201)


@api_login_required
@require_POST
def crm_activity_complete_api(request, activity_id):
    """Mark an activity as completed."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'tasks', 'complete')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    activity = get_object_or_404(Activity, id=activity_id, tenant=tenant)
    activity.mark_completed(user=request.user)
    return JsonResponse({'status': 'ok', 'completed_at': activity.completed_at.isoformat()})


# =====================================================================
# 3. LIVE CHAT & CONVERSATIONS APIS
# =====================================================================

@api_login_required
@require_GET
def chat_conversations_list_api(request):
    """List conversations for the shared WhatsApp inbox."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    qs = (
        Conversation.objects.filter(tenant=tenant)
        .select_related('customer', 'service', 'assigned_staff')
        .prefetch_related('messages')
        .order_by('-last_message_at')
    )

    status_filter = request.GET.get('status')
    if status_filter:
        qs = qs.filter(status=status_filter)

    tab = request.GET.get('tab', '').strip().lower()
    if tab == 'mine':
        qs = qs.filter(assigned_staff=request.user)
    elif tab == 'unassigned':
        qs = qs.filter(assigned_staff__isnull=True)
    elif tab == 'bot':
        qs = qs.filter(status=ConversationStatus.BOT_ACTIVE)
    elif tab == 'human':
        qs = qs.filter(status=ConversationStatus.HUMAN_HANDOVER)

    query = request.GET.get('q', '').strip()
    if query:
        qs = qs.filter(
            Q(customer__name__icontains=query) |
            Q(customer__phone_number__icontains=query) |
            Q(messages__message_text__icontains=query)
        ).distinct()

    conversations = []
    for conv in qs[:60]:
        last_msg = conv.messages.order_by('-created_at').first()
        last_inbound = conv.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
        is_window_open = True
        if conv.channel == ChannelChoice.WHATSAPP:
            is_window_open = bool(last_inbound and last_inbound.created_at >= timezone.now() - timedelta(hours=24))

        conversations.append({
            'id': conv.id,
            'customer_id': conv.customer_id,
            'customer_name': conv.customer.name or 'Customer',
            'customer_phone': conv.customer.phone_number,
            'channel': conv.channel,
            'channel_display': conv.get_channel_display(),
            'service_name': conv.service.name if conv.service else 'General Inquiries',
            'status': conv.status,
            'status_display': conv.get_status_display(),
            'last_message_text': last_msg.message_text if last_msg else '',
            'last_message_direction': last_msg.direction if last_msg else None,
            'last_message_at': conv.last_message_at.isoformat() if conv.last_message_at else None,
            'assigned_staff': conv.assigned_staff.username if conv.assigned_staff else None,
            'assigned_staff_id': conv.assigned_staff_id,
            'assigned_staff_name': (conv.assigned_staff.get_full_name() or conv.assigned_staff.username) if conv.assigned_staff else None,
            'unread_count': conv.unread_count,
            'handover_required': conv.status == ConversationStatus.HUMAN_HANDOVER,
            'handoff_summary': conv.handoff_summary or '',
            'is_window_open': is_window_open,
        })

    return JsonResponse({'conversations': conversations})


@api_login_required
@require_POST
@transaction.atomic
def chat_start_conversation_api(request):
    """
    Start a new conversation with a contact in the WhatsApp business messaging workspace.
    Validates E.164 phone numbers.
    Respects Meta 24-hour customer service window rules:
    - If window is closed (or new outbound on WhatsApp channel): requires an approved template + variable values.
    - If window is open: allows free-form initial message.
    - Explicitly communicates that saving a contact does not imply messaging consent.
    """
    import re
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active tenant context required'}, status=400)

    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'send_message')
    if not allowed and not request.user.is_superuser:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    data = _parse_body(request)
    contact_id = data.get('contact_id')
    raw_phone = str(data.get('phone_number', '')).strip()
    name = str(data.get('name', '')).strip()
    channel = data.get('channel', ChannelChoice.WHATSAPP)
    template_name = data.get('template_name')
    template_variables = data.get('template_variables', [])
    message_text = str(data.get('message_text', '')).strip()

    # Resolve customer
    customer = None
    if contact_id:
        customer = Customer.objects.filter(id=contact_id, tenant=tenant).first()
        if not customer:
            return JsonResponse({'error': 'Contact not found'}, status=404)
        phone = customer.phone_number
    elif raw_phone:
        # Validate E.164
        phone = raw_phone.strip()
        if not phone.startswith('+'):
            phone = '+' + phone
        if not re.fullmatch(r'^\+[1-9]\d{7,14}$', phone):
            return JsonResponse({'error': 'Phone number must be in valid international E.164 format (e.g. +14155552671 or +919876543210).'}, status=400)
        
        customer, created = Customer.objects.get_or_create(
            tenant=tenant,
            phone_number=phone,
            defaults={'name': name or f'Customer {phone[-4:]}', 'owner': request.user}
        )
        if not created and name and not customer.name:
            customer.name = name
            customer.save(update_fields=['name'])
    else:
        return JsonResponse({'error': 'Provide either an existing contact_id or a valid international phone_number.'}, status=400)

    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    if channel not in ChannelChoice.values:
        return JsonResponse({'error': 'Unsupported channel.'}, status=400)

    # Resolve conversation without creating duplicates
    conversation = Conversation.objects.select_for_update().filter(
        tenant=tenant, customer=customer, channel=channel
    ).exclude(status=ConversationStatus.CLOSED).first()

    if conversation:
        # Check ownership conflict: if assigned to another staff member and user is not superuser
        if conversation.assigned_staff_id and conversation.assigned_staff_id != request.user.pk and not request.user.is_superuser:
            return JsonResponse({
                'error': f'This conversation is already assigned to @{conversation.assigned_staff.username}. Ask them to release it first.',
                'assigned_staff': conversation.assigned_staff.username,
                'conversation_id': conversation.id
            }, status=409)
    else:
        conversation = Conversation.objects.create(
            tenant=tenant,
            customer=customer,
            channel=channel,
            status=ConversationStatus.HUMAN_HANDOVER,
            assigned_staff=request.user,
            picked_up_at=timezone.now(),
            handoff_summary=f'Direct conversation initiated by @{request.user.username}',
        )

    if conversation.status == ConversationStatus.BOT_ACTIVE and (message_text or template_name):
        return JsonResponse({'error': 'Switch to Human mode explicitly before sending a manual message.'}, status=409)

    # Check 24-hour customer service window
    last_inbound = conversation.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
    is_window_open = True
    if conversation.channel == ChannelChoice.WHATSAPP:
        is_window_open = bool(last_inbound and last_inbound.created_at >= timezone.now() - timedelta(hours=24))

    # If window is closed on WhatsApp, template is strictly required
    if conversation.channel == ChannelChoice.WHATSAPP and not is_window_open:
        if not template_name:
            return JsonResponse({
                'error': 'The 24-hour customer service window is not open. You must select an approved Meta template to initiate a conversation.',
                'requires_template': True,
                'is_window_open': False,
                'conversation_id': conversation.id,
            }, status=400)

        template_qs = WhatsAppTemplate.objects.filter(tenant=tenant, name=template_name)
        if data.get('template_language'):
            template_qs = template_qs.filter(language=data['template_language'])
        if template_qs.count() > 1:
            return JsonResponse({'error': 'Select the exact template language.'}, status=400)
        template = template_qs.first()
        if not template:
            return JsonResponse({'error': 'Template not found.'}, status=404)
        if template.meta_status != 'APPROVED':
            return JsonResponse({'error': 'Template is not approved by Meta or its components are unsupported.'}, status=400)

        # Validate variables: count and non-empty
        placeholders = re.findall(r'\{\{(\d+)\}\}', template.body_text)
        required_count = len(set(placeholders))
        if not isinstance(template_variables, list) or len(template_variables) != required_count:
            return JsonResponse({'error': f'Template "{template_name}" requires exactly {required_count} variables.'}, status=400)
        for i, val in enumerate(template_variables, start=1):
            if not isinstance(val, str) or not val.strip():
                return JsonResponse({'error': f'Variable {i} for template "{template_name}" cannot be empty or whitespace.'}, status=400)

        # Render template body with variable replacements
        rendered_body = template.body_text
        for i, val in enumerate(template_variables, start=1):
            rendered_body = rendered_body.replace(f'{{{{{i}}}}}', str(val).strip())

        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.HUMAN,
                message_text=rendered_body,
                processing_status=ProcessingStatus.PROCESSED,
                response_data={
                    'template_name': template.name,
                    'template_variables': template_variables,
                    'author_username': request.user.username,
                    'author_name': request.user.get_full_name() or request.user.username,
                }
            )
            conversation.status = ConversationStatus.HUMAN_HANDOVER
            conversation.assigned_staff = request.user
            if not conversation.picked_up_at:
                conversation.picked_up_at = timezone.now()
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['status', 'assigned_staff', 'picked_up_at', 'last_message_at', 'updated_at'])

            delivery = WhatsAppDelivery.objects.create(
                tenant=tenant,
                dedup_key=f'staff:{message.pk}',
                recipient_phone=customer.phone_number,
                payload={
                    'template': {
                        'name': template.name,
                        'language': template.language,
                        'parameters': template_variables
                    },
                    'text': rendered_body,
                    'conversation_id': conversation.pk, 'message_id': message.pk, 'sender_type': 'HUMAN'
                }
            )
            transaction.on_commit(lambda: dispatch(delivery.pk))

        return JsonResponse({
            'message': 'Template message sent to start conversation.',
            'conversation_id': conversation.id,
            'message_id': message.id,
            'delivery_id': delivery.id,
            'is_window_open': False,
            'customer_name': customer.name,
            'customer_phone': customer.phone_number,
        })

    # Window is open (or simulated channel)
    if message_text:
        with transaction.atomic():
            message = Message.objects.create(
                conversation=conversation,
                direction=MessageDirection.OUTBOUND,
                sender_type=SenderType.HUMAN,
                message_text=message_text,
                processing_status=ProcessingStatus.PROCESSED,
                response_data={
                    'author_username': request.user.username,
                    'author_name': request.user.get_full_name() or request.user.username,
                }
            )
            conversation.status = ConversationStatus.HUMAN_HANDOVER
            conversation.assigned_staff = request.user
            if not conversation.picked_up_at:
                conversation.picked_up_at = timezone.now()
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['status', 'assigned_staff', 'picked_up_at', 'last_message_at', 'updated_at'])

            delivery_id = None
            if conversation.channel == ChannelChoice.WHATSAPP:
                delivery = WhatsAppDelivery.objects.create(
                    tenant=tenant,
                    dedup_key=f'staff:{message.pk}',
                    recipient_phone=customer.phone_number,
                    payload={'text': message_text, 'conversation_id': conversation.pk, 'message_id': message.pk, 'sender_type': 'HUMAN'}
                )
                delivery_id = delivery.id
                transaction.on_commit(lambda: dispatch(delivery.pk))

        return JsonResponse({
            'message': 'Conversation started.',
            'conversation_id': conversation.id,
            'message_id': message.id,
            'delivery_id': delivery_id,
            'is_window_open': True,
            'customer_name': customer.name,
            'customer_phone': customer.phone_number,
        })

    # No initial message sent, simply return existing conversation
    return JsonResponse({
        'message': 'Conversation ready.',
        'conversation_id': conversation.id,
        'is_window_open': is_window_open,
        'customer_name': customer.name,
        'customer_phone': customer.phone_number,
    })


@api_login_required
@require_POST
def delivery_retry_api(request, delivery_id):
    """
    Safely retry a failed or blocked WhatsApp message delivery without duplicate sends.
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active tenant context required'}, status=400)

    allowed, reason = can_perform_action(request.user, tenant, 'inbox', 'send_message')
    if not allowed and not request.user.is_superuser:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    from apps.whatsapp.delivery_context import locked_delivery, sender_kind
    if not WhatsAppDelivery.objects.filter(id=delivery_id, tenant=tenant).exists():
        return JsonResponse({'error': 'Delivery record not found.'}, status=404)
    with locked_delivery(delivery_id) as (delivery, conv):
        if delivery.status == 'SENDING':
            return JsonResponse({'error': 'Delivery is currently in-flight to Meta. Cannot retry an active send.'}, status=409)

        if delivery.status == 'UNKNOWN':
            return JsonResponse({'error': 'Delivery status is ambiguous (UNKNOWN). Meta may have accepted the message. Manual inspection required before retry to prevent duplicate sends.'}, status=400)

        if delivery.status in ('SENT', 'DELIVERED', 'READ'):
            return JsonResponse({'error': f'Message has already reached status {delivery.status}.'}, status=400)

        if delivery.status not in ('FAILED', 'BLOCKED'):
            return JsonResponse({'error': f'Only conclusively FAILED or BLOCKED deliveries can be retried (current status: {delivery.status}).'}, status=400)

        if delivery.attempts >= 3:
            return JsonResponse({'error': 'Retry attempt limit reached. Inspect delivery history; attempt counters cannot be reset.'}, status=400)
        if not conv:
            return JsonResponse({'error': 'Conversation origin is missing or ambiguous. Manual inspection required.'}, status=400)
        kind = sender_kind(delivery) or 'HUMAN'
        if kind == 'BOT':
            if conv.status != ConversationStatus.BOT_ACTIVE:
                return JsonResponse({'error': 'Bot delivery cannot be retried in Human mode.'}, status=409)
        elif conv.status != ConversationStatus.HUMAN_HANDOVER or conv.assigned_staff_id != request.user.pk:
            return JsonResponse({'error': 'Claim this conversation in Human mode before retrying its message.'}, status=409)
        payload = delivery.payload or {}
        if payload.get('template'):
            template_data = payload['template']
            if not WhatsAppTemplate.objects.filter(tenant=tenant, name=template_data.get('name'), language=template_data.get('language'), meta_status='APPROVED').exists():
                return JsonResponse({'error': 'Template approval is unavailable or revoked.'}, status=400)
        else:
            last_inbound = conv.messages.filter(direction=MessageDirection.INBOUND).order_by('-created_at').first()
            if not (last_inbound and last_inbound.created_at >= timezone.now() - timedelta(hours=24)):
                return JsonResponse({'error': 'The 24-hour customer service window has expired.', 'requires_template': True}, status=400)
        delivery.status = 'PENDING'
        delivery.last_error = ''
        if not isinstance(delivery.payload, dict):
            delivery.payload = {}
        delivery.payload['retried_at'] = timezone.now().isoformat()
        delivery.payload['retried_by'] = request.user.username
        delivery.save(update_fields=['status', 'attempts', 'last_error', 'payload', 'updated_at'])
        transaction.on_commit(lambda: dispatch(delivery.pk))

    return JsonResponse({
        'message': 'Delivery retry queued.',
        'delivery_id': delivery.id,
        'status': delivery.status,
    })


@api_login_required
@require_GET
def whatsapp_templates_api(request):
    """
    List Meta WhatsApp templates for the tenant.
    Auto-seeds starter utility templates as DRAFT if none exist.
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active tenant context required'}, status=400)

    # Auto-seed starter templates as DRAFT if tenant has none
    if not WhatsAppTemplate.objects.filter(tenant=tenant).exists():
        default_templates = [
            {
                'name': 'welcome_greeting',
                'category': 'UTILITY',
                'language': 'en',
                'body_text': 'Hello {{1}}, welcome to our WhatsApp support! How can our team help you today?',
                'variables': ['Customer Name'],
                'meta_status': 'DRAFT',
            },
            {
                'name': 'appointment_reminder',
                'category': 'UTILITY',
                'language': 'en',
                'body_text': 'Hi {{1}}, this is a friendly reminder for your upcoming appointment on {{2}}.',
                'variables': ['Customer Name', 'Date & Time'],
                'meta_status': 'DRAFT',
            },
            {
                'name': 'service_followup',
                'category': 'UTILITY',
                'language': 'en',
                'body_text': 'Hello {{1}}, following up on your request regarding {{2}}. Please let us know if you need any further assistance.',
                'variables': ['Customer Name', 'Service Name'],
                'meta_status': 'DRAFT',
            },
            {
                'name': 'account_update',
                'category': 'UTILITY',
                'language': 'en',
                'body_text': 'Hi {{1}}, here is an update on your request: {{2}}.',
                'variables': ['Customer Name', 'Update Details'],
                'meta_status': 'DRAFT',
            },
        ]
        for tpl_data in default_templates:
            WhatsAppTemplate.objects.get_or_create(
                tenant=tenant,
                name=tpl_data['name'],
                language=tpl_data['language'],
                defaults=tpl_data
            )

    # Only a complete successful provider snapshot may update approval state.
    if request.GET.get('sync') == 'true':
        from apps.whatsapp.template_sync import sync_templates
        membership = TenantMembership.objects.filter(tenant=tenant, user=request.user, is_active=True).first()
        if not request.user.is_superuser and (not membership or membership.role not in (MembershipRole.OWNER, MembershipRole.ADMIN)):
            return JsonResponse({'error': 'Owner or administrator access required to sync templates.'}, status=403)
        ok, error = sync_templates(tenant)
        if not ok:
            return JsonResponse({'error': error, 'templates': []}, status=502)

    templates_qs = WhatsAppTemplate.objects.filter(tenant=tenant).order_by('name')
    templates = [
        {
            'id': tpl.id,
            'name': tpl.name,
            'category': tpl.category,
            'language': tpl.language,
            'body_text': tpl.body_text,
            'variables': tpl.variables or [],
            'status': tpl.meta_status,
        }
        for tpl in templates_qs
    ]

    return JsonResponse({'templates': templates})


@api_login_required
@require_http_methods(['GET', 'POST'])
def whatsapp_business_profile_api(request):
    """
    Get or update official Meta WhatsApp Business Profile for the tenant.
    Enforces Meta constraints (about max 139, description max 512, address max 256,
    email max 128, websites max 2 URLs, vertical category enum).
    """
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active tenant context required'}, status=400)

    # Permission & role check: only owner or admin (or superuser)
    if not request.user.is_superuser:
        membership = TenantMembership.objects.filter(tenant=tenant, user=request.user, is_active=True).first()
        if not membership or membership.role not in (MembershipRole.OWNER, MembershipRole.ADMIN):
            return JsonResponse({'error': 'Forbidden: Owner or Administrator access required for WhatsApp Business Profile.'}, status=403)
        allowed, reason = can_perform_action(request.user, tenant, 'whatsapp_settings', 'view' if request.method == 'GET' else 'edit')
        if not allowed:
            return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    profile, _ = WhatsAppBusinessProfile.objects.get_or_create(tenant=tenant)
    cfg = WhatsAppConfig.objects.filter(tenant=tenant).first()

    if request.method == 'GET':
        if request.GET.get('sync') == 'true':
            if not (cfg and cfg.is_enabled and cfg.phone_number_id and cfg.access_token):
                return JsonResponse({'error': 'WhatsApp is not connected; live profile sync is unavailable.'}, status=400)
            live_data = WhatsAppClient.get_business_profile(tenant=tenant)
            if not live_data or not live_data.get('live') or live_data.get('error'):
                return JsonResponse({'error': 'Could not sync the live Meta profile. Cached values have not been changed.'}, status=502)
            if live_data.get('live'):
                for fld in ('about', 'description', 'address', 'email', 'websites', 'vertical', 'profile_picture_url'):
                    if fld in live_data:
                        setattr(profile, fld, live_data[fld])
                for fld in ('verified_name', 'display_phone_number', 'quality_rating', 'code_verification_status', 'messaging_limit_tier'):
                    if fld in live_data:
                        setattr(profile, fld, live_data[fld])
                profile.save()

        meta_info = {
            'verified_name': profile.verified_name or 'UNAVAILABLE',
            'display_phone_number': profile.display_phone_number or 'UNAVAILABLE',
            'quality_rating': profile.quality_rating or 'UNKNOWN',
            'messaging_limit_tier': profile.messaging_limit_tier or 'UNKNOWN',
            'code_verification_status': profile.code_verification_status or 'UNKNOWN',
            'is_live': bool(cfg and cfg.is_enabled and cfg.phone_number_id and cfg.access_token),
        }

        vertical_choices = [
            {'value': choice[0], 'label': choice[1]}
            for choice in WhatsAppBusinessProfile.VERTICAL_CHOICES
        ]

        return JsonResponse({
            'profile': {
                'about': profile.about,
                'description': profile.description,
                'address': profile.address,
                'email': profile.email,
                'websites': profile.websites or [],
                'vertical': profile.vertical,
                'profile_picture_url': whatsapp_profile_media_url(tenant, profile),
            },
            'meta_info': meta_info,
            'vertical_choices': vertical_choices,
            'profile_picture_upload_supported': True,
            'profile_picture_notice': 'Upload a photo in this workspace. Private S3 storage and a connected Meta app are required.',
        })

    # POST - update profile
    data = _parse_body(request)
    about = str(data.get('about', '')).strip()
    description = str(data.get('description', '')).strip()
    address = str(data.get('address', '')).strip()
    email = str(data.get('email', '')).strip()
    vertical = str(data.get('vertical', 'OTHER')).strip()
    websites_raw = data.get('websites', [])
    if isinstance(websites_raw, str):
        websites = [u.strip() for u in websites_raw.split(',') if u.strip()]
    elif isinstance(websites_raw, list):
        websites = [str(u).strip() for u in websites_raw if str(u).strip()]
    else:
        websites = []

    # Enforce Meta limits
    if len(about) > 139:
        return JsonResponse({'error': 'About section must not exceed 139 characters.'}, status=400)
    if len(description) > 512:
        return JsonResponse({'error': 'Description must not exceed 512 characters.'}, status=400)
    if len(address) > 256:
        return JsonResponse({'error': 'Address must not exceed 256 characters.'}, status=400)
    if len(email) > 128:
        return JsonResponse({'error': 'Email must not exceed 128 characters.'}, status=400)
    if len(websites) > 2:
        return JsonResponse({'error': 'A maximum of 2 website URLs are supported by Meta.'}, status=400)

    valid_verticals = [choice[0] for choice in WhatsAppBusinessProfile.VERTICAL_CHOICES]
    if vertical and vertical not in valid_verticals:
        return JsonResponse({'error': f'Invalid category. Choose from: {", ".join(valid_verticals)}'}, status=400)

    # Sync to Meta if live credentials exist
    meta_updated = False
    meta_error = None
    if cfg and cfg.is_enabled and cfg.phone_number_id and cfg.access_token:
        ok, err = WhatsAppClient.update_business_profile(
            {
                'about': about,
                'description': description,
                'address': address,
                'email': email,
                'websites': websites,
                'vertical': vertical
            },
            tenant=tenant
        )
        meta_updated = ok
        if not ok:
            meta_error = err

    profile.about = about
    profile.description = description
    profile.address = address
    profile.email = email
    profile.websites = websites
    profile.vertical = vertical
    profile.save()

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_STATUS_CHANGED,
        summary=f"WhatsApp Business Profile updated by @{request.user.username}",
        details={'about': about, 'vertical': vertical, 'meta_synced': meta_updated}
    )

    return JsonResponse({
        'message': 'WhatsApp Business Profile saved locally and synced to Meta.' if meta_updated else (
            f'Saved locally, but Meta sync failed: {meta_error}' if meta_error else 'Saved locally (Meta sync not configured).'
        ),
        'status': 'META_SYNCED' if meta_updated else 'LOCAL_SAVED',
        'profile': {
            'about': profile.about,
            'description': profile.description,
            'address': profile.address,
            'email': profile.email,
            'websites': profile.websites,
            'vertical': profile.vertical,
        },
        'meta_synced': meta_updated,
        'meta_warning': meta_error,
    })


# =====================================================================
# 4. BOOKINGS APIS
# =====================================================================

@api_login_required
@require_GET
def bookings_list_api(request):
    """List bookings."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'bookings', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    qs = Booking.objects.filter(tenant=tenant).select_related('customer', 'service').order_by('-created_at')
    bookings = [
        {
            'id': b.id,
            'customer_name': b.customer.name if b.customer else 'Unknown',
            'customer_phone': b.customer.phone_number if b.customer else '',
            'service_name': b.service.name if b.service else 'General Booking',
            'preferred_date': b.preferred_date.isoformat() if b.preferred_date else None,
            'preferred_time': b.preferred_time or '',
            'address': b.address or '',
            'status': b.status,
            'status_display': b.get_status_display(),
            'created_at': b.created_at.isoformat(),
        }
        for b in qs[:80]
    ]
    return JsonResponse({'bookings': bookings})


# =====================================================================
# 5. SERVICES & CATALOG APIS
# =====================================================================

@api_login_required
@require_http_methods(['GET', 'POST'])
def services_api(request):
    """List or create catalog services."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'services', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if request.method == 'GET':
        if tenant:
            qs = Service.objects.filter(tenant=tenant, is_active=True).order_by('id')
        else:
            if not Tenant.objects.exists():
                qs = Service.objects.filter(is_active=True).order_by('id')
            else:
                qs = Service.objects.none()

        services = [
            {
                'id': s.id,
                'name': s.name,
                'slug': getattr(s, 'slug', ''),
                'category': s.category,
                'price_type': s.price_type,
                'price_type_display': s.get_price_type_display(),
                'price_amount': str(s.price_amount) if s.price_amount else None,
                'formatted_price': s.formatted_price,
                'currency': s.currency,
                'contact_number': s.contact_number or '',
                'description': s.description or '',
                'is_active': s.is_active,
            }
            for s in qs
        ]
        return JsonResponse({'services': services, 'results': services, 'count': len(services)})

    # POST: Create service
    if tenant:
        current_count = Service.objects.filter(tenant=tenant, is_active=True).count()
        if current_count >= tenant.effective_max_services:
            return JsonResponse({
                'error': f"Service limit reached ({tenant.effective_max_services} services). Upgrade plan."
            }, status=400)

    data = _parse_body(request)
    name = data.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Service name is required.'}, status=400)

    price_amount = data.get('price_amount')
    service = Service.objects.create(
        tenant=tenant,
        name=name,
        category=data.get('category', 'Standard Service'),
        price_type=data.get('price_type', PriceType.FIXED),
        price_amount=Decimal(str(price_amount)) if price_amount else None,
        currency=data.get('currency', 'INR'),
        contact_number=data.get('contact_number', ''),
        description=data.get('description', ''),
        is_active=True
    )
    return JsonResponse({'status': 'created', 'service': {'id': service.id, 'name': service.name}}, status=201)


# =====================================================================
# 6. KNOWLEDGE BASE APIS
# =====================================================================

@api_login_required
@require_GET
def knowledge_overview_api(request):
    """Retrieve FAQs, Knowledge Documents, and sync status."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'knowledge', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    faqs = list(FAQ.objects.filter(tenant=tenant).values(
        'id', 'category', 'question', 'answer', 'is_active', 'created_at'
    ))
    documents = list(KnowledgeDocument.objects.filter(tenant=tenant).values(
        'id', 'category', 'title', 'content', 'is_active', 'created_at'
    ))

    return JsonResponse({
        'faqs': faqs,
        'documents': documents,
        'doc_allowance': {
            'count': KnowledgeDocument.objects.filter(tenant=tenant, is_active=True).count(),
            'limit': tenant.effective_max_documents if tenant else 20,
        }
    })


@api_login_required
@require_POST
def knowledge_faq_create_api(request):
    """Create a new FAQ."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'knowledge', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    data = _parse_body(request)
    question = data.get('question', '').strip()
    answer = data.get('answer', '').strip()
    category = data.get('category', 'General').strip()

    if not question or not answer:
        return JsonResponse({'error': 'Question and answer are required.'}, status=400)

    faq, created = FAQ.objects.get_or_create(
        tenant=tenant,
        question=question,
        defaults={'answer': answer, 'category': category, 'is_active': True}
    )
    if not created:
        return JsonResponse({'error': 'An FAQ with this exact question already exists.'}, status=409)

    return JsonResponse({'status': 'created', 'faq': {'id': faq.id, 'question': faq.question}}, status=201)


@api_login_required
@require_http_methods(['DELETE'])
def knowledge_faq_delete_api(request, faq_id):
    """Delete an FAQ."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'knowledge', 'delete')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    faq = get_object_or_404(FAQ, id=faq_id, tenant=tenant)
    faq.delete()
    return JsonResponse({'status': 'deleted'})


@api_login_required
@require_POST
def knowledge_doc_create_api(request):
    """Upload or add a knowledge document."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'knowledge', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if tenant and not tenant.can_add_document():
        return JsonResponse({
            'error': f"Document limit reached ({tenant.effective_max_documents} uploaded documents). Please upgrade plan."
        }, status=400)

    data = _parse_body(request)
    title = data.get('title', '').strip()
    content = data.get('content', '').strip()
    category = data.get('category', DocumentCategory.POLICY)

    if not title or not content:
        return JsonResponse({'error': 'Title and content are required.'}, status=400)

    doc = KnowledgeDocument.objects.create(
        tenant=tenant,
        title=title,
        content=content,
        category=category,
        is_active=True
    )
    return JsonResponse({'status': 'created', 'document': {'id': doc.id, 'title': doc.title}}, status=201)


# =====================================================================
# 7. TEAM & SETTINGS APIS
# =====================================================================

@api_login_required
@require_GET
def team_api(request):
    """List team members, pending invitations, staff requests, and recent team security events."""
    from .onboarding_api import _serialize_member
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    actor_membership = getattr(request, 'membership', None) or (
        TenantMembership.objects.filter(tenant=tenant, user=request.user, is_active=True).first()
        if tenant else None
    )
    members = list(
        TenantMembership.objects.filter(tenant=tenant)
        .select_related('user')
        .order_by('-role', 'user__username')
    )
    members_data = [
        _serialize_member(m, actor_membership=actor_membership, actor_user=request.user)
        for m in members
    ]

    invitations = list(
        TenantInvitation.objects.filter(tenant=tenant, is_accepted=False)
        .order_by('-created_at')
    )
    invitations_data = [
        {
            'id': inv.id,
            'email': inv.email,
            'role': inv.role,
            'role_display': inv.get_role_display(),
            'is_expired': inv.is_expired,
            'created_at': inv.created_at.isoformat(),
        }
        for inv in invitations
    ]

    staff_requests = [
        {
            'id': str(r.id),
            'full_name': r.full_name,
            'email': r.email,
            'role': r.role,
            'role_display': r.get_role_display(),
            'status': r.status,
            'status_display': r.get_status_display(),
            'notes': r.notes,
            'review_notes': r.review_notes,
            'created_at': r.created_at.isoformat(),
        }
        for r in StaffAccessRequest.objects.filter(tenant=tenant).order_by('-created_at')
    ]

    audit_events = [
        {
            'id': a.id,
            'action': a.action,
            'summary': a.summary,
            'actor': a.actor.username if a.actor else 'System',
            'created_at': a.created_at.isoformat(),
        }
        for a in TenantAuditLog.objects.filter(
            tenant=tenant,
            action__in=[
                AuditLogAction.STAFF_CREATED,
                AuditLogAction.STAFF_UPDATED,
                AuditLogAction.STAFF_PASSWORD_RESET,
                AuditLogAction.MEMBERSHIP_REVOKED,
                AuditLogAction.INVITATION_SENT,
                AuditLogAction.WORK_REASSIGNED,
            ]
        ).select_related('actor').order_by('-created_at')[:20]
    ]

    return JsonResponse({
        'members': members_data,
        'invitations': invitations_data,
        'staff_requests': staff_requests,
        'audit_logs': audit_events,
        'actor_role': 'SUPERUSER' if request.user.is_superuser else (actor_membership.role if actor_membership else ''),
        'seat_summary': {
            'allocated': tenant.effective_max_staff if tenant else 5,
            'used': len([m for m in members_data if m['is_active']]) + len([i for i in invitations_data if not i['is_expired']]),
            'can_add': tenant.can_add_staff() if tenant else True,
        }
    })


@api_login_required
@require_POST
def team_request_staff_api(request):
    """
    Client administrator submits a staff access request to Super Admin.
    Does NOT create a User or Membership account.
    """
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if tenant and not tenant.can_add_staff():
        return JsonResponse({
            'error': f"Seat limit reached ({tenant.effective_max_staff} seats). Please request a plan upgrade."
        }, status=400)

    data = _parse_body(request)
    full_name = data.get('full_name', '').strip()
    email = data.get('email', '').strip().lower()
    role = data.get('role', TenantRole.STAFF)
    notes = data.get('notes', '').strip()

    if not full_name or not email:
        return JsonResponse({'error': 'Full name and email are required.'}, status=400)

    staff_req = StaffAccessRequest.objects.create(
        tenant=tenant,
        requested_by=request.user,
        full_name=full_name,
        email=email,
        role=role,
        notes=notes,
        status=StaffRequestStatus.PENDING
    )

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.STAFF_REQUEST_SUBMITTED,
        summary=f"Staff access requested for {full_name} ({email}) by @{request.user.username}",
        details={'role': role, 'request_id': str(staff_req.id)}
    )

    return JsonResponse({
        'status': 'submitted',
        'message': f"Access request for {full_name} submitted to Super Admin for approval.",
        'request_id': str(staff_req.id)
    }, status=201)


@api_login_required
@require_POST
def team_reassign_work_api(request):
    """Reassign all open deals, contacts, and tasks from one team member to another."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'edit')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    data = _parse_body(request)
    from_user_id = data.get('from_user_id')
    to_user_id = data.get('to_user_id')

    if not from_user_id or not to_user_id:
        return JsonResponse({'error': 'Both from_user_id and to_user_id are required.'}, status=400)

    if str(from_user_id) == str(to_user_id):
        return JsonResponse({'error': 'Cannot reassign work to the same user.'}, status=400)

    from_user = get_object_or_404(User, id=from_user_id)
    to_user = get_object_or_404(User, id=to_user_id)

    to_membership = TenantMembership.objects.filter(tenant=tenant, user=to_user, is_active=True).first()
    if not to_membership:
        return JsonResponse({'error': 'Target user is not an active member of this workspace.'}, status=400)

    with transaction.atomic():
        deals_updated = Deal.objects.filter(tenant=tenant, owner=from_user).update(owner=to_user)
        tasks_updated = Activity.objects.filter(tenant=tenant, assigned_to=from_user).update(assigned_to=to_user)
        convs_updated = Conversation.objects.filter(tenant=tenant, assigned_staff=from_user).update(assigned_staff=to_user)

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=request.user,
            action=AuditLogAction.WORK_REASSIGNED,
            summary=f"Reassigned work from @{from_user.username} to @{to_user.username}",
            details={'deals_count': deals_updated, 'tasks_count': tasks_updated, 'conversations_count': convs_updated}
        )

    return JsonResponse({
        'status': 'reassigned',
        'deals_reassigned': deals_updated,
        'tasks_reassigned': tasks_updated,
        'conversations_reassigned': convs_updated,
        'message': f"Reassigned {deals_updated} deal(s), {tasks_updated} task(s), and {convs_updated} conversation(s) to @{to_user.username}."
    })


@api_login_required
@require_POST
def team_remove_member_api(request, membership_id):
    """
    Revoke a tenant membership without deleting the global user identity.
    Guards last active owner and requires reassignment of open work.
    """
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'delete')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    membership = get_object_or_404(TenantMembership, id=membership_id, tenant=tenant)

    # Guard 1: Protect last active owner
    if membership.role == TenantRole.OWNER and membership.is_active:
        active_owners = TenantMembership.objects.filter(tenant=tenant, role=TenantRole.OWNER, is_active=True).count()
        if active_owners <= 1:
            return JsonResponse({'error': 'Cannot remove the last active Owner of this workspace.'}, status=400)

    # Guard 2: Open assigned work check
    open_deals = Deal.objects.filter(tenant=tenant, owner=membership.user, stage__is_won=False, stage__is_lost=False).count()
    open_tasks = Activity.objects.filter(tenant=tenant, assigned_to=membership.user, status__in=['TODO', 'IN_PROGRESS']).count()

    if open_deals > 0 or open_tasks > 0:
        return JsonResponse({
            'error': f"User has {open_deals} open deal(s) and {open_tasks} active task(s). Please reassign work before removing access.",
            'requires_reassign': True,
            'open_deals': open_deals,
            'open_tasks': open_tasks,
            'user_id': membership.user.id,
        }, status=400)

    with transaction.atomic():
        membership.is_active = False
        membership.save(update_fields=['is_active', 'updated_at'])

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=request.user,
            action=AuditLogAction.MEMBERSHIP_REVOKED,
            summary=f"Membership revoked for @{membership.user.username} ({membership.get_role_display()})",
            details={'user_id': membership.user.id, 'role': membership.role}
        )

    return JsonResponse({
        'status': 'revoked',
        'message': f"Access for @{membership.user.username} has been revoked."
    })


@api_login_required
@require_POST
def team_invite_api(request):
    """Send team member invitation."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if tenant and not tenant.can_add_staff():
        return JsonResponse({
            'error': f"Seat limit reached ({tenant.effective_max_staff} seats). Please upgrade your plan."
        }, status=400)

    data = _parse_body(request)
    email = data.get('email', '').strip().lower()
    role = data.get('role', MembershipRole.STAFF)

    if not email:
        return JsonResponse({'error': 'Email is required.'}, status=400)

    invitation = TenantInvitation.create_invitation(
        tenant=tenant,
        email=email,
        role=role,
        invited_by=request.user,
        valid_days=7
    )

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.INVITATION_SENT,
        summary=f"Invitation sent to {email} ({role})",
        details={'email': email, 'role': role}
    )

    return JsonResponse({
        'status': 'invited',
        'email': email,
        'role': role,
        'token': str(invitation.token)
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def whatsapp_settings_api(request):
    """Retrieve or update WhatsApp Meta Cloud API configuration."""
    tenant = getattr(request, 'tenant', None)
    action = 'view' if request.method == 'GET' else 'edit'
    allowed, reason = can_perform_action(request.user, tenant, 'whatsapp_settings', action)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    from apps.whatsapp.models import WhatsAppWebhookLog
    config = WhatsAppConfig.objects.filter(tenant=tenant).first()

    if request.method == 'GET':
        has_token = bool(config and config.access_token)
        token_masked = ('••••••••' + config.access_token[-4:]) if has_token else ''
        webhook_count = WhatsAppWebhookLog.objects.filter(tenant=tenant).count() if tenant else 0
        live_delivery_count = WhatsAppDelivery.objects.filter(tenant=tenant, status='DELIVERED').count() if tenant else 0

        return JsonResponse({
            **meta_setup_state(tenant),
            'connection_verified_at': config.connection_verified_at.isoformat() if config and config.connection_verified_at else None,
            'configured': config is not None and bool(config.phone_number_id),
            'credentials_present': bool(config and config.phone_number_id and config.access_token),
            'phone_number_id': config.phone_number_id if config else '',
            'app_id': config.app_id if config else '',
            'app_secret_present': bool(config and config.app_secret),
            'webhook_url': request.build_absolute_uri('/api/whatsapp/webhook/'),
            'business_account_id': config.business_account_id if config else '',
            'access_token_masked': token_masked,
            'webhook_verify_token': config.verify_token if config else '',
            'is_enabled': config.is_enabled if config else False,
            'webhook_verified': webhook_count > 0,
            'live_messaging_tested': live_delivery_count > 0,
        })

    data = _parse_body(request)
    phone_id = data.get('phone_number_id', '').strip()
    waba_id = data.get('business_account_id', '').strip()
    token = data.get('access_token', '').strip()
    verify_tok = data.get('webhook_verify_token', '').strip()
    app_id = data.get('app_id', '').strip()
    app_secret = data.get('app_secret', '').strip()
    enabled = data.get('is_enabled', True)
    if type(enabled) is not bool or (app_id and (not app_id.isdigit() or len(app_id)>60)) or len(app_secret)>120:
        return JsonResponse({'error': 'Enter a valid numeric Meta app ID, app secret and enable setting.'}, status=400)

    if not phone_id:
        return JsonResponse({'error': 'Phone number ID is required.'}, status=400)

    # Validate provider identifier ownership: prevent claiming another tenant's phone number or WABA ID
    existing_phone = WhatsAppConfig.objects.filter(phone_number_id=phone_id).exclude(tenant=tenant).select_related('tenant').first()
    if existing_phone and existing_phone.tenant:
        return JsonResponse({
            'error': f"Phone Number ID '{phone_id}' is already connected to another client workspace ({existing_phone.tenant.name}). Duplicate provider claims are not permitted."
        }, status=409)

    if waba_id:
        existing_waba = WhatsAppConfig.objects.filter(business_account_id=waba_id).exclude(tenant=tenant).select_related('tenant').first()
        if existing_waba and existing_waba.tenant:
            return JsonResponse({
                'error': f"Business Account ID '{waba_id}' is already registered to another client workspace ({existing_waba.tenant.name})."
            }, status=409)

    try:
        with transaction.atomic():
            if not config:
                config = WhatsAppConfig.objects.create(
                    tenant=tenant,
                    phone_number_id=phone_id,
                    business_account_id=waba_id,
                    access_token=token,
                    verify_token=verify_tok,
                    app_id=app_id,
                    app_secret=app_secret,
                    is_enabled=enabled
                )
            else:
                config.phone_number_id = phone_id
                if waba_id:
                    config.business_account_id = waba_id
                if token and not token.startswith('••'):
                    config.access_token = token
                if verify_tok:
                    config.verify_token = verify_tok
                if app_id:
                    config.app_id = app_id
                if app_secret:
                    config.app_secret = app_secret
                config.is_enabled = enabled
                config.save()

    except IntegrityError:
        return JsonResponse({'error': 'This Meta phone number or business account is already connected to another workspace.'}, status=409)

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_STATUS_CHANGED,
        summary=f"WhatsApp Cloud API configuration updated by @{request.user.username}",
        details={'phone_number_id': phone_id, 'business_account_id': waba_id}
    )

    return JsonResponse({'status': 'saved', 'message': 'WhatsApp credentials configured.'})


@api_login_required
@require_POST
def whatsapp_verify_api(request):
    """Safely verify Meta WhatsApp Cloud API connectivity without sending customer messages."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'whatsapp_settings', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    config = WhatsAppConfig.objects.filter(tenant=tenant).first()
    if not tenant or not config:
        return JsonResponse({'status': 'error', 'provider_status': 'FAILED', 'message': 'Configure Meta first.'}, status=400)
    try:
        state = verify_meta_connection(tenant, config)
    except ValueError as exc:
        return JsonResponse({'status': 'error', 'provider_status': 'FAILED', 'message': str(exc), **meta_setup_state(tenant)}, status=400)
    return JsonResponse({'status': 'ok', 'provider_status': 'VERIFIED', 'message': 'Meta verified your phone number and business account.', **state})


@api_login_required
@require_http_methods(['GET', 'POST'])
def workspace_settings_api(request):
    """Retrieve or update tenant workspace branding, timezone, and contact details."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    membership = getattr(request, 'membership', None) or getattr(request, 'tenant_membership', None)
    if not membership and tenant:
        membership = TenantMembership.objects.filter(tenant=tenant, user=request.user, is_active=True).first()

    is_client_admin = request.user.is_superuser or (membership and membership.role in [TenantRole.OWNER, TenantRole.ADMIN])
    if not is_client_admin:
        return JsonResponse({'error': 'Permission Denied. Only workspace administrators can manage workspace settings.'}, status=403)

    if request.method == 'GET':
        plan_name = 'Standard'
        sub_status = 'ACTIVE'
        if hasattr(tenant, 'subscription') and tenant.subscription:
            if tenant.subscription.effective_plan:
                plan_name = tenant.subscription.effective_plan.name
            sub_status = tenant.subscription.status

        return JsonResponse({
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo_url': tenant.effective_logo_url,
            'logo_source_url': '' if (tenant.logo_url or '').startswith('s3://') else (tenant.logo_url or ''),
            'timezone': tenant.timezone or 'Asia/Kolkata',
            'contact_email': tenant.contact_email or '',
            'contact_phone': tenant.contact_phone or '',
            'plan_name': plan_name,
            'subscription_status': sub_status,
            'is_active': tenant.is_active,
        })

    # POST: Update settings
    data = _parse_body(request)
    if 'name' in data and data['name'].strip():
        tenant.name = data['name'].strip()
    if 'logo_url' in data:
        logo_url = data['logo_url'].strip()
        if logo_url and (len(logo_url) > 500 or not logo_url.startswith('https://')):
            return JsonResponse({'error': 'Use an HTTPS image URL under 500 characters or upload a logo.'}, status=400)
        if logo_url or not (tenant.logo_url or '').startswith('s3://'):
            tenant.logo_url = logo_url
    if 'timezone' in data and data['timezone'].strip():
        tenant.timezone = data['timezone'].strip()
    if 'contact_email' in data:
        tenant.contact_email = data['contact_email'].strip()
    if 'contact_phone' in data:
        tenant.contact_phone = data['contact_phone'].strip()

    tenant.save()

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_STATUS_CHANGED,
        summary=f"Workspace settings updated by @{request.user.username}",
        details={
            'name': tenant.name,
            'logo_url': tenant.logo_url,
            'timezone': tenant.timezone,
            'contact_email': tenant.contact_email,
            'contact_phone': tenant.contact_phone,
        }
    )

    return JsonResponse({
        'status': 'updated',
        'tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo_url': tenant.effective_logo_url,
            'logo_source_url': '' if (tenant.logo_url or '').startswith('s3://') else (tenant.logo_url or ''),
            'timezone': tenant.timezone,
            'contact_email': tenant.contact_email,
            'contact_phone': tenant.contact_phone,
        }
    })


# =====================================================================
# 8. PLATFORM ADMINISTRATION APIS (SUPERADMIN ONLY)
# =====================================================================

@api_login_required
@require_GET
def platform_metrics_api(request):
    """Platform-wide system metrics for platform operators."""
    from .platform_auth import can_platform_access
    allowed, reason = can_platform_access(request.user, 'dashboard', write=False)
    if not allowed:
        return JsonResponse({'error': reason}, status=403)

    total_tenants = Tenant.objects.count()
    active_tenants = Tenant.objects.filter(is_active=True).count()
    total_users = User.objects.count()
    total_messages = Message.objects.count()
    total_bookings = Booking.objects.count()

    plans_breakdown = list(Tenant.objects.values('plan').annotate(count=Count('id')))

    return JsonResponse({
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'total_users': total_users,
        'total_messages': total_messages,
        'total_bookings': total_bookings,
        'plans_breakdown': plans_breakdown,
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def platform_tenants_api(request):
    """List all client workspaces or provision a new client workspace."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Super Admin access required.'}, status=403)

    if request.method == 'GET':
        tenants = []
        for t in Tenant.objects.all().order_by('-created_at'):
            owner_m = t.memberships.filter(role=TenantRole.OWNER, is_active=True).select_related('user').first()
            sub = getattr(t, 'subscription', None)
            plan_obj = sub.effective_plan if sub else None
            tenants.append({
                'id': t.id,
                'name': t.name,
                'slug': t.slug,
                'plan': plan_obj.code if plan_obj else t.plan,
                'plan_name': plan_obj.name if plan_obj else t.get_plan_display(),
                'is_active': t.is_active,
                'logo_url': t.effective_logo_url,
                'timezone': t.timezone,
                'contact_email': t.contact_email,
                'contact_phone': t.contact_phone,
                'whatsapp_number': t.whatsapp_number,
                'meta_setup_required': meta_setup_state(t)['required'],
                'meta_setup_ready': meta_setup_state(t)['ready'],
                'meta_setup_reason': meta_setup_state(t)['reason'],
                'outbound_paused': t.outbound_paused,
                'outbound_pause_reason': t.outbound_pause_reason,
                'subscription_status': sub.status if sub else 'ACTIVE',
                'grace_until': sub.grace_until.isoformat() if sub and sub.grace_until else None,
                'grace_notes': sub.grace_notes if sub else '',
                'last_reminder_sent_at': sub.last_reminder_sent_at.isoformat() if sub and sub.last_reminder_sent_at else None,
                'staff_count': t.active_staff_count,
                'max_staff': t.effective_max_staff,
                'owner_username': owner_m.user.username if owner_m else 'None',
                'owner_email': owner_m.user.email if owner_m else '',
                'owner_activation_pending': bool(owner_m and not owner_m.user.has_usable_password()),
                'created_at': t.created_at.isoformat(),
            })
        return JsonResponse({'tenants': tenants})

    # POST: Super Admin Guided Provisioning
    data = _parse_body(request)
    whatsapp_number = data.get('whatsapp_number', '')
    if not valid_whatsapp_number(whatsapp_number):
        return JsonResponse({'error': 'A valid WhatsApp number in E.164 format (for example +919876543210) is required.'}, status=400)
    if Tenant.objects.filter(whatsapp_number=whatsapp_number).exists():
        return JsonResponse({'error': 'This WhatsApp number is already assigned to a client.'}, status=409)

    name = data.get('name', '').strip()
    contact_email = data.get('contact_email', '').strip().lower()
    contact_phone = data.get('contact_phone', '').strip()
    timezone_str = data.get('timezone', 'Asia/Kolkata').strip()
    logo_url = data.get('logo_url', '').strip()
    plan_code = str(data.get('plan_code') or data.get('plan') or 'basic').strip()
    if plan_code.upper() == 'STARTER':
        plan_code = 'basic'
    admin_mode = data.get('admin_mode', 'new')
    existing_user_id = data.get('existing_user_id')
    admin_username = data.get('admin_username', '').strip()
    admin_email = data.get('admin_email', '').strip().lower() or contact_email
    admin_name = data.get('admin_name', '').strip()
    contact_email = contact_email or admin_email

    if not name:
        return JsonResponse({'error': 'Client business name is required.'}, status=400)
    if Tenant.objects.filter(name=name).exists():
        return JsonResponse({'error': 'A workspace with this name already exists.'}, status=400)
    if not admin_email and not (admin_mode == 'existing' and existing_user_id):
        return JsonResponse({'error': 'Administrator email is required.'}, status=400)

    base_slug = slugify(data.get('slug') or name)[:150] or 'workspace'
    slug = base_slug
    counter = 1
    while Tenant.objects.filter(slug=slug).exists():
        slug = f"{base_slug}-{counter}"
        counter += 1

    plan_tier = PlanTier.objects.filter(code__iexact=plan_code).first()
    if not plan_tier:
        return JsonResponse({'error': 'Select a valid subscription plan.'}, status=400)
    legacy_plan = plan_tier.code.upper() if plan_tier.code.upper() in ('PRO', 'ENTERPRISE') else 'STARTER'

    try:
        with transaction.atomic():
            tenant = Tenant.objects.create(
                name=name,
                slug=slug,
                requires_meta_setup=True,
                whatsapp_number=whatsapp_number,
                plan=legacy_plan,
                logo_url=logo_url,
                timezone=timezone_str,
                contact_email=contact_email,
                contact_phone=contact_phone,
                max_staff=plan_tier.max_staff if plan_tier else 5,
                max_services=plan_tier.max_services if plan_tier else 25,
                is_active=True
            )

            activation_url = None
            if admin_mode == 'existing' and existing_user_id:
                owner_user = get_object_or_404(User, id=existing_user_id)
            elif User.objects.filter(email__iexact=admin_email).exists():
                matches = User.objects.filter(email__iexact=admin_email)
                if matches.count() != 1:
                    transaction.set_rollback(True)
                    return JsonResponse({'error': 'Email matches multiple accounts; select an existing account explicitly.'}, status=400)
                owner_user = matches.get()
            else:
                if not admin_username:
                    admin_username = admin_email.split('@')[0] if admin_email else f"admin_{slug[:20]}"
                base_un = admin_username
                un_counter = 1
                while User.objects.filter(username=admin_username).exists():
                    admin_username = f"{base_un}_{un_counter}"
                    un_counter += 1

                owner_user = User.objects.create_user(
                    username=admin_username,
                    email=admin_email,
                    first_name=admin_name or name,
                    is_staff=True
                )
                owner_user.set_unusable_password()
                owner_user.save()
                token_obj = AccountActivationToken.create_for_user(owner_user)
                from django.urls import reverse
                activation_url = request.build_absolute_uri(reverse('activate-account', args=[token_obj.token]))
                from .email_service import queue_activation
                queue_activation(request, token_obj, tenant)

            if owner_user.is_superuser:
                transaction.set_rollback(True)
                return JsonResponse({'error': 'A platform Super Admin cannot be a client workspace owner.'}, status=400)

            TenantMembership.objects.create(
                tenant=tenant,
                user=owner_user,
                role=TenantRole.OWNER,
                is_active=True
            )

            from apps.tenants.models import TenantSubscription, OnboardingProgress, OnboardingStep
            TenantSubscription.objects.create(
                tenant=tenant,
                requested_plan=plan_tier,
                effective_plan=plan_tier,
                status=SubscriptionStatus.ACTIVE,
                approved_by=request.user,
                approved_at=timezone.now(),
                start_date=timezone.now().date(),
                notes="Provisioned via Super Admin Console"
            )

            OnboardingProgress.objects.create(
                tenant=tenant,
                current_step=OnboardingStep.PROFILE
            )

            from apps.tenants.models import (
                ClientOnboarding, OnboardingSource, OnboardingApprovalStatus, OnboardingRegistrationStatus
            )
            ClientOnboarding.objects.get_or_create(
                tenant=tenant,
                defaults={
                    'source': OnboardingSource.SUPERADMIN_INVITE,
                    'business_name': tenant.name,
                    'owner_full_name': owner_user.get_full_name() or owner_user.username,
                    'owner_email': admin_email or owner_user.email or tenant.contact_email or f"{owner_user.username}@workspace.local",
                    'desired_username': owner_user.username,
                    'whatsapp_number': tenant.whatsapp_number,
                    'requested_plan': plan_tier,
                    'assigned_plan': plan_tier,
                    'registration_status': (
                        OnboardingRegistrationStatus.ACTIVE
                        if owner_user.has_usable_password()
                        else OnboardingRegistrationStatus.APPROVED
                    ),
                    'email_verified': bool(UserSecurityProfile.get_or_create_for_user(owner_user).email_verified),
                    'approval_status': OnboardingApprovalStatus.APPROVED,
                    'approved_by': request.user,
                    'approved_at': timezone.now(),
                    'decision_reason': 'Provisioned via Platform Admin workspace API',
                    'password_set': owner_user.has_usable_password(),
                    'owner_user': owner_user,
                },
            )

            TenantAuditLog.objects.create(
                tenant=tenant,
                actor=request.user,
                action=AuditLogAction.TENANT_CREATED,
                summary=f"Client workspace '{name}' provisioned with owner @{owner_user.username}",
                details={'slug': slug, 'plan': plan_code, 'logo_url': logo_url}
            )

    except IntegrityError:
        return JsonResponse({'error': 'This WhatsApp number or workspace identity was claimed concurrently. Use a unique client number and retry.'}, status=409)

    return JsonResponse({
        'status': 'provisioned',
        'tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo_url': tenant.effective_logo_url,
            'logo_source_url': '' if (tenant.logo_url or '').startswith('s3://') else (tenant.logo_url or ''),
            'owner_username': owner_user.username,
            'whatsapp_number': tenant.whatsapp_number,
            'meta_setup_required': True,
            'meta_setup_ready': False,
        },
        'activation_url': activation_url,
        'message': f"Client workspace '{tenant.name}' provisioned successfully."
    }, status=201)


@api_login_required
@require_POST
def platform_tenant_update_api(request, tenant_id):
    """Update client workspace business details, logo, timezone, or plan."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Super Admin access required.'}, status=403)

    tenant = get_object_or_404(Tenant, id=tenant_id)
    data = _parse_body(request)

    if 'name' in data and data['name'].strip():
        tenant.name = data['name'].strip()
    if 'logo_url' in data:
        logo_url = data['logo_url'].strip()
        if logo_url and (len(logo_url) > 500 or not logo_url.startswith('https://')):
            return JsonResponse({'error': 'Use an HTTPS image URL under 500 characters or upload a logo.'}, status=400)
        if logo_url or not (tenant.logo_url or '').startswith('s3://'):
            tenant.logo_url = logo_url
    if 'timezone' in data and data['timezone'].strip():
        tenant.timezone = data['timezone'].strip()
    if 'contact_email' in data:
        tenant.contact_email = data['contact_email'].strip().lower()
    if 'contact_phone' in data:
        tenant.contact_phone = data['contact_phone'].strip()
    if 'is_active' in data:
        tenant.is_active = bool(data['is_active'])

    tenant.save()
    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_STATUS_CHANGED,
        summary=f"Client workspace '{tenant.name}' updated by Super Admin",
        details={'is_active': tenant.is_active, 'logo_url': tenant.logo_url}
    )

    return JsonResponse({
        'status': 'updated',
        'tenant': {
            'id': tenant.id,
            'name': tenant.name,
            'slug': tenant.slug,
            'logo_url': tenant.effective_logo_url,
            'logo_source_url': '' if (tenant.logo_url or '').startswith('s3://') else (tenant.logo_url or ''),
            'timezone': tenant.timezone,
            'is_active': tenant.is_active,
        }
    })


@api_login_required
@require_GET
def platform_staff_requests_api(request):
    """List all staff access requests submitted by client administrators."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Super Admin access required.'}, status=403)

    requests = list(
        StaffAccessRequest.objects.all().select_related('tenant', 'requested_by', 'reviewed_by').order_by('-created_at')
    )
    data = [
        {
            'id': str(r.id),
            'tenant_id': r.tenant.id,
            'tenant_name': r.tenant.name,
            'full_name': r.full_name,
            'email': r.email,
            'role': r.role,
            'role_display': r.get_role_display(),
            'notes': r.notes,
            'status': r.status,
            'status_display': r.get_status_display(),
            'requested_by': r.requested_by.username,
            'reviewed_by': r.reviewed_by.username if r.reviewed_by else None,
            'review_notes': r.review_notes,
            'created_at': r.created_at.isoformat(),
        }
        for r in requests
    ]
    return JsonResponse({'staff_requests': data})


@api_login_required
@require_POST
def platform_staff_request_action_api(request, request_id, action):
    """Approve or reject a client staff access request."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Super Admin access required.'}, status=403)

    staff_req = get_object_or_404(StaffAccessRequest, id=request_id)
    if staff_req.status != StaffRequestStatus.PENDING:
        return JsonResponse({'error': f"Request has already been {staff_req.status.lower()}."}, status=400)

    data = _parse_body(request)
    review_notes = data.get('review_notes', '').strip()

    if action == 'approve':
        if not staff_req.tenant.can_add_staff():
            return JsonResponse({
                'error': f"Seat limit reached ({staff_req.tenant.effective_max_staff} seats). Upgrade tenant plan before approving additional staff."
            }, status=400)

        # Role boundary guard: Staff requests cannot grant global superuser or platform roles
        if staff_req.role not in [TenantRole.STAFF, TenantRole.ADMIN, TenantRole.OWNER]:
            return JsonResponse({'error': 'Invalid role requested.'}, status=400)

        with transaction.atomic():
            email = staff_req.email.strip().lower()
            user = User.objects.filter(email__iexact=email).first()
            activation_url = None

            if not user:
                base_username = email.split('@')[0]
                un = base_username
                counter = 1
                while User.objects.filter(username=un).exists():
                    un = f"{base_username}_{counter}"
                    counter += 1

                user = User.objects.create_user(
                    username=un,
                    email=email,
                    first_name=staff_req.full_name,
                    is_staff=True
                )
                user.set_unusable_password()
                user.save()
                token_obj = AccountActivationToken.create_for_user(user)
                from django.urls import reverse
                activation_url = request.build_absolute_uri(reverse('activate-account', args=[token_obj.token]))
                from .email_service import queue_activation
                queue_activation(request, token_obj, staff_req.tenant)

            membership, _ = TenantMembership.objects.get_or_create(
                tenant=staff_req.tenant,
                user=user,
                defaults={'role': staff_req.role, 'is_active': True}
            )
            membership.role = staff_req.role
            membership.is_active = True
            membership.save(update_fields=['role', 'is_active', 'updated_at'])

            staff_req.status = StaffRequestStatus.APPROVED
            staff_req.reviewed_by = request.user
            staff_req.reviewed_at = timezone.now()
            staff_req.review_notes = review_notes
            staff_req.save()

            TenantAuditLog.objects.create(
                tenant=staff_req.tenant,
                actor=request.user,
                action=AuditLogAction.STAFF_REQUEST_APPROVED,
                summary=f"Super Admin approved staff request for {staff_req.full_name} ({staff_req.email})",
                details={'role': staff_req.role, 'user_id': user.id}
            )

        return JsonResponse({
            'status': 'approved',
            'activation_url': activation_url,
            'message': f"Staff access for {staff_req.full_name} approved and provisioned."
        })

    elif action == 'reject':
        staff_req.status = StaffRequestStatus.REJECTED
        staff_req.reviewed_by = request.user
        staff_req.reviewed_at = timezone.now()
        staff_req.review_notes = review_notes
        staff_req.save()

        TenantAuditLog.objects.create(
            tenant=staff_req.tenant,
            actor=request.user,
            action=AuditLogAction.STAFF_REQUEST_REJECTED,
            summary=f"Super Admin rejected staff request for {staff_req.full_name}",
            details={'reason': review_notes}
        )

        return JsonResponse({'status': 'rejected', 'message': 'Staff request rejected.'})

    return JsonResponse({'error': f"Unknown action '{action}'."}, status=400)


@api_login_required
@require_POST
def platform_tenant_toggle_api(request, tenant_id):
    """Activate or suspend tenant."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant.is_active = not tenant.is_active
    tenant.save(update_fields=['is_active', 'updated_at'])

    status_str = "activated" if tenant.is_active else "suspended"
    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_STATUS_CHANGED,
        summary=f"Tenant '{tenant.name}' marked {status_str}",
        details={'is_active': tenant.is_active}
    )

    return JsonResponse({'status': 'ok', 'is_active': tenant.is_active, 'status_str': status_str})


@api_login_required
@require_GET
def platform_audit_api(request):
    """List recent security audit trail events."""
    from .platform_auth import can_platform_access
    allowed, reason = can_platform_access(request.user, 'audit', write=False)
    if not allowed:
        return JsonResponse({'error': reason}, status=403)

    logs = list(
        TenantAuditLog.objects.select_related('tenant', 'actor')
        .order_by('-created_at')[:50]
        .values('id', 'action', 'summary', 'details', 'created_at', 'tenant__name', 'actor__username')
    )
    return JsonResponse({'logs': logs})


# =====================================================================
# 9. ONBOARDING, REPORTS & USAGE APIS
# =====================================================================

def _evaluate_setup_checklist(user, tenant):
    """Evaluate the 8 live Client Setup Checklist items without inventing fake readiness."""
    if not tenant:
        return None
    sec = UserSecurityProfile.get_or_create_for_user(user)
    owner_m = tenant.memberships.filter(role=TenantRole.OWNER, is_active=True).select_related('user').first()
    owner_user = owner_m.user if owner_m else user
    owner_sec = UserSecurityProfile.get_or_create_for_user(owner_user)
    bp = BusinessProfile.objects.filter(tenant=tenant).first()
    sub = getattr(tenant, 'subscription', None)
    meta = meta_setup_state(tenant)
    has_services = Service.objects.filter(tenant=tenant).exists()
    has_knowledge = FAQ.objects.filter(tenant=tenant).exists() or KnowledgeDocument.objects.filter(tenant=tenant).exists()
    has_staff = tenant.memberships.filter(is_active=True).count() > 1

    items = [
        {
            'key': 'email_verified',
            'title': 'Email verified',
            'completed': bool(owner_sec.email_verified or owner_sec.skip_mailbox_gate),
            'optional': False,
            'href': '/app/account',
        },
        {
            'key': 'password_set',
            'title': 'Password set',
            'completed': bool(owner_user.has_usable_password()),
            'optional': False,
            'href': '/app/account',
        },
        {
            'key': 'business_profile',
            'title': 'Business profile complete',
            'completed': bool(bp and (bp.shop_name or '').strip() and (bp.contact_phone or '').strip()),
            'optional': False,
            'href': '/app/settings',
        },
        {
            'key': 'plan_active',
            'title': 'Plan active',
            'completed': bool(sub and sub.status == SubscriptionStatus.ACTIVE and sub.effective_plan_id),
            'optional': False,
            'href': '/app/subscription',
        },
        {
            'key': 'whatsapp_meta_configured',
            'title': 'WhatsApp Meta API configured and tested',
            'completed': bool(meta.get('ready')),
            'optional': False,
            'href': '/app/settings?tab=whatsapp',
        },
        {
            'key': 'services_and_knowledge',
            'title': 'Services / FAQs / Knowledge Base added',
            'completed': bool(has_services or has_knowledge),
            'optional': False,
            'href': '/app/services',
        },
        {
            'key': 'team_staff_added',
            'title': 'Team staff added',
            'completed': bool(has_staff),
            'optional': True,
            'href': '/app/team',
        },
        {
            'key': 'recovery_email_verified',
            'title': 'Recovery email verified',
            'completed': bool(sec.recovery_email_verified and sec.recovery_email),
            'optional': False,
            'href': '/app/account',
        },
    ]
    required_items = [i for i in items if not i['optional']]
    completed_required = sum(1 for i in required_items if i['completed'])
    return {
        'items': items,
        'completed_count': sum(1 for i in items if i['completed']),
        'total_count': len(items),
        'required_completed_count': completed_required,
        'required_total_count': len(required_items),
        'all_required_done': completed_required == len(required_items),
    }


@api_login_required
@require_http_methods(['GET', 'POST'])
def onboarding_status_api(request):
    """Onboarding status, 8-step simulation progress, and live 8-item Client Setup Checklist."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'onboarding', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    from apps.tenants.models import OnboardingProgress, OnboardingStep
    progress, _ = OnboardingProgress.objects.get_or_create(tenant=tenant)
    done_steps = set(progress.completed_steps or [])

    if request.method == 'GET':
        steps = [
            {'id': 'profile', 'title': 'Business Profile', 'completed': 'profile' in done_steps},
            {'id': 'plan', 'title': 'Plan & Access', 'completed': 'plan' in done_steps},
            {'id': 'whatsapp', 'title': 'WhatsApp API', 'completed': 'whatsapp' in done_steps},
            {'id': 'knowledge', 'title': 'Knowledge & Catalog', 'completed': 'knowledge' in done_steps},
            {'id': 'team', 'title': 'Team Setup', 'completed': 'team' in done_steps},
            {'id': 'workspace', 'title': 'Sales Workspace', 'completed': 'workspace' in done_steps},
            {'id': 'test', 'title': 'Assistant Test', 'completed': 'test' in done_steps},
            {'id': 'readiness', 'title': 'Readiness Review', 'completed': 'readiness' in done_steps},
        ]
        return JsonResponse({
            'current_step': progress.current_step,
            'is_completed': progress.is_completed,
            'completed_steps_count': len(done_steps),
            'steps': steps,
            'checklist': _evaluate_setup_checklist(request.user, tenant),
        })

    data = _parse_body(request)
    step = data.get('step')
    if step:
        progress.current_step = step
        progress.save(update_fields=['current_step'])
    return JsonResponse({'status': 'ok', 'current_step': progress.current_step})


@api_login_required
@require_POST
def onboarding_test_assistant_api(request):
    """Run real synthetic assistant simulation grounded in tenant profile without sending live messages."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'onboarding', 'edit')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    from apps.tenants.onboarding_views import run_synthetic_assistant_test
    from apps.tenants.models import OnboardingProgress, OnboardingStep

    data = _parse_body(request)
    query = data.get('query', 'What services do you provide?')
    result = run_synthetic_assistant_test(tenant, query)

    progress, _ = OnboardingProgress.objects.get_or_create(tenant=tenant)
    progress.mark_step_done(OnboardingStep.TEST)

    return JsonResponse({'status': 'ok', 'result': result})


@api_login_required
@require_GET
def reports_overview_api(request):
    """Operational reports and analytics overview for tenant."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'reports', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    total_convs = Conversation.objects.filter(tenant=tenant).count()
    active_convs = Conversation.objects.filter(tenant=tenant, status=ConversationStatus.BOT_ACTIVE).count()
    human_convs = Conversation.objects.filter(tenant=tenant, status=ConversationStatus.HUMAN_HANDOVER).count()

    deals_won = Deal.objects.filter(tenant=tenant, stage__is_won=True).count()
    deals_lost = Deal.objects.filter(tenant=tenant, stage__is_lost=True).count()
    deals_open = Deal.objects.filter(tenant=tenant, stage__is_won=False, stage__is_lost=False).count()
    pipeline_val = Deal.objects.filter(tenant=tenant, stage__is_won=False, stage__is_lost=False).aggregate(val=Sum('amount'))['val'] or 0

    pending_tasks = Activity.objects.filter(tenant=tenant, status=ActivityStatus.PENDING).count()
    overdue_tasks = Activity.objects.filter(
        tenant=tenant, status=ActivityStatus.PENDING, due_date__lt=timezone.now()
    ).count()
    completed_tasks = Activity.objects.filter(tenant=tenant, status=ActivityStatus.COMPLETED).count()

    bookings_total = Booking.objects.filter(tenant=tenant).count()
    bookings_confirmed = Booking.objects.filter(tenant=tenant, status=BookingStatus.CONFIRMED).count()

    # Release 3 Enhanced Metrics: Unanswered inbound, unread count, response times, agent workload & campaign outcomes
    from django.db.models import F
    convs_qs = Conversation.objects.filter(tenant=tenant)
    unanswered_inbound = convs_qs.exclude(status=ConversationStatus.CLOSED).filter(
        Q(unread_count__gt=0) |
        Q(last_inbound_at__isnull=False, first_human_response_at__isnull=True, status=ConversationStatus.HUMAN_HANDOVER) |
        Q(last_inbound_at__gt=F('first_human_response_at'))
    ).count()
    total_unread_messages = convs_qs.aggregate(total=Sum('unread_count'))['total'] or 0

    response_samples = []
    for conv_obj in convs_qs.filter(first_human_response_at__isnull=False).only('created_at', 'first_human_response_at', 'last_inbound_at')[:200]:
        anchor = conv_obj.last_inbound_at if (conv_obj.last_inbound_at and conv_obj.last_inbound_at <= conv_obj.first_human_response_at) else conv_obj.created_at
        if anchor and conv_obj.first_human_response_at >= anchor:
            response_samples.append((conv_obj.first_human_response_at - anchor).total_seconds() / 60.0)
    avg_first_response_minutes = round(sum(response_samples) / len(response_samples), 1) if response_samples else None

    agents_workload = []
    for m in TenantMembership.objects.filter(tenant=tenant, is_active=True).select_related('user').order_by('user__username')[:50]:
        open_chats = convs_qs.filter(assigned_staff=m.user).exclude(status=ConversationStatus.CLOSED).count()
        replies_sent = Message.objects.filter(
            conversation__tenant=tenant,
            direction=MessageDirection.OUTBOUND,
            sender_type=SenderType.HUMAN,
            response_data__author_username=m.user.username,
        ).count()
        agents_workload.append({
            'user_id': m.user_id,
            'username': m.user.username,
            'full_name': m.user.get_full_name() or m.user.username,
            'role': m.role,
            'open_chats': open_chats,
            'replies_sent': replies_sent,
        })

    from apps.crm.models import Campaign
    from apps.crm.broadcasts import totals as campaign_totals
    campaigns_qs = Campaign.objects.filter(tenant=tenant)
    camp_sent = camp_delivered = camp_read = camp_failed = 0
    for c_obj in campaigns_qs[:100]:
        c_stats = campaign_totals(c_obj)
        camp_sent += c_stats['sent_count']
        camp_delivered += c_stats['delivered_count']
        camp_read += c_stats['read_count']
        camp_failed += c_stats['failed_count']

    return JsonResponse({
        'conversations': {
            'total': total_convs,
            'active': active_convs,
            'human_takeover': human_convs,
            'unanswered_inbound': unanswered_inbound,
            'unread_messages': total_unread_messages,
            'avg_first_response_minutes': avg_first_response_minutes,
        },
        'deals': {
            'open': deals_open,
            'won': deals_won,
            'lost': deals_lost,
            'pipeline_value': str(pipeline_val),
        },
        'activities': {
            'pending': pending_tasks,
            'overdue': overdue_tasks,
            'completed': completed_tasks,
        },
        'bookings': {
            'total': bookings_total,
            'confirmed': bookings_confirmed,
        },
        'agents': agents_workload,
        'campaigns': {
            'total': campaigns_qs.count(),
            'completed': campaigns_qs.filter(status='COMPLETED').count(),
            'sent': camp_sent,
            'delivered': camp_delivered,
            'read': camp_read,
            'failed': camp_failed,
        },
    })


@api_login_required
@require_GET
def usage_overview_api(request):
    """Detailed monthly usage and quota allocations for tenant."""
    tenant = getattr(request, 'tenant', None)
    allowed, reason = can_perform_action(request.user, tenant, 'dashboard', 'view')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    now = timezone.now()
    monthly_usage = tenant.monthly_usages.filter(year=now.year, month=now.month).first() if tenant else None
    sent = monthly_usage.outbound_messages_sent if monthly_usage else 0
    reserved = getattr(monthly_usage, 'outbound_messages_reserved', 0) if monthly_usage else 0
    allowance = tenant.effective_monthly_message_allowance if tenant else 500

    docs_count = tenant.documents.filter(is_active=True).count() if tenant else 0
    docs_limit = tenant.effective_max_documents if tenant else 5

    contacts_count = Customer.objects.filter(tenant=tenant).count() if tenant else 0
    contacts_limit = tenant.effective_max_contacts if tenant else 1000

    staff_count = tenant.memberships.filter(is_active=True).count() if tenant else 0
    staff_limit = tenant.effective_max_staff if tenant else 2

    deliveries_recent = list(
        WhatsAppDelivery.objects.filter(tenant=tenant)
        .order_by('-created_at')[:10]
        .values('id', 'recipient_phone', 'status', 'attempts', 'last_error', 'created_at')
    ) if tenant else []

    return JsonResponse({
        'billing_period': f"{now.strftime('%B %Y')}",
        'messages': {
            'sent': sent,
            'reserved': reserved,
            'allowance': allowance,
            'remaining': max(0, allowance - sent - reserved),
            'percent': min(100, int(((sent + reserved) / allowance * 100))) if allowance > 0 else 0,
        },
        'documents': {
            'count': docs_count,
            'limit': docs_limit,
            'remaining': max(0, docs_limit - docs_count),
        },
        'contacts': {
            'count': contacts_count,
            'limit': contacts_limit,
            'remaining': max(0, contacts_limit - contacts_count),
        },
        'staff': {
            'count': staff_count,
            'limit': staff_limit,
            'remaining': max(0, staff_limit - staff_count),
        },
        'alerts': [
            {
                'resource': label,
                'used': used,
                'limit': limit,
                'percent': int(round((used / limit) * 100)) if limit else 0,
                'level': 'EXCEEDED' if used >= limit else 'WARNING',
                'message': f"{label} usage at {used}/{limit} ({int(round((used / limit) * 100))}%).",
            }
            for label, used, limit in (
                ('Messages', sent + reserved, allowance),
                ('Contacts', contacts_count, contacts_limit),
                ('Documents', docs_count, docs_limit),
                ('Staff seats', staff_count, staff_limit),
            )
            if limit > 0 and (used * 100 >= limit * 80)
        ],
        'recent_deliveries': deliveries_recent,
    })


# =====================================================================
# 10. PLATFORM MATRIX, OVERRIDES & BULK ASSIGN APIS
# =====================================================================

@api_login_required
@require_GET
def platform_matrix_api(request):
    """Platform Matrix: real PlanTier list, capabilities, modules, and tenants."""
    from .platform_auth import can_platform_access
    allowed, reason = can_platform_access(request.user, 'plans', write=False)
    if not allowed:
        return JsonResponse({'error': reason}, status=403)

    from apps.tenants.modules import MODULE_CATALOG

    plans = list(PlanTier.objects.order_by('ordering', 'name').values(
        'id', 'code', 'name', 'badge', 'monthly_price', 'currency',
        'max_staff', 'max_contacts', 'max_services', 'max_documents',
        'monthly_message_allowance', 'crm_enabled', 'ai_assistant_enabled',
        'enabled_modules', 'is_published'
    ))

    tenant_caps = [
        {
            'key': c['key'],
            'name': c['name'],
            'category': c['category'],
            'required_module': c.get('required_module'),
            'min_role': c.get('min_role'),
            'description': c.get('description', '')
        }
        for c in CAPABILITY_REGISTRY.values()
        if c.get('scope') == 'tenant'
    ]

    modules = [
        {
            'key': k,
            'name': v['name'],
            'category': v['category'],
            'status': v['status'],
            'description': v.get('description', '')
        }
        for k, v in MODULE_CATALOG.items()
    ]

    tenants = []
    for t in Tenant.objects.order_by('name'):
        sub = getattr(t, 'subscription', None)
        plan = sub.effective_plan if sub else None
        tenants.append({
            'id': t.id,
            'name': t.name,
            'slug': t.slug,
            'current_plan_code': plan.code if plan else t.plan,
            'current_plan_name': plan.name if plan else t.get_plan_display(),
            'subscription_status': sub.status if sub else 'ACTIVE',
            'is_active': t.is_active,
            'max_staff': t.max_staff,
            'max_services': t.max_services,
        })

    return JsonResponse({
        'plans': plans,
        'capabilities': tenant_caps,
        'modules': modules,
        'tenants': tenants,
    })


@api_login_required
@require_POST
def platform_plan_bundle_api(request, plan_code):
    """Superadmin/Billing: update plan tier entitlements, bounded limits, and module bundles."""
    from .platform_auth import can_platform_access
    allowed, reason = can_platform_access(request.user, 'plans', write=True)
    if not allowed:
        return JsonResponse({'error': reason}, status=403)

    plan = get_object_or_404(PlanTier, code=plan_code)
    data = _parse_body(request)

    enabled_modules = data.get('enabled_modules')
    if enabled_modules is not None and isinstance(enabled_modules, list):
        plan.enabled_modules = enabled_modules

    try:
        if 'max_staff' in data:
            v = int(data['max_staff'])
            if not 1 <= v <= 10000:
                raise ValueError('max_staff must be between 1 and 10000')
            plan.max_staff = v
        if 'max_contacts' in data:
            v = int(data['max_contacts'])
            if not 1 <= v <= 10000000:
                raise ValueError('max_contacts must be between 1 and 10000000')
            plan.max_contacts = v
        if 'max_services' in data:
            v = int(data['max_services'])
            if not 1 <= v <= 10000:
                raise ValueError('max_services must be between 1 and 10000')
            plan.max_services = v
        if 'max_documents' in data:
            v = int(data['max_documents'])
            if not 1 <= v <= 10000:
                raise ValueError('max_documents must be between 1 and 10000')
            plan.max_documents = v
        if 'monthly_message_allowance' in data:
            v = int(data['monthly_message_allowance'])
            if not 0 <= v <= 100000000:
                raise ValueError('monthly_message_allowance must be between 0 and 100000000')
            plan.monthly_message_allowance = v
        if 'monthly_price' in data and data['monthly_price'] not in ('', None):
            from decimal import Decimal
            price = Decimal(str(data['monthly_price']))
            if price < 0 or not price.is_finite():
                raise ValueError('monthly_price must be non-negative')
            plan.monthly_price = price
        if 'badge' in data:
            plan.badge = str(data['badge'] or '')[:50]
        if 'is_published' in data:
            plan.is_published = bool(data['is_published'])
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc) or 'Invalid limit value.'}, status=400)
    if 'crm_enabled' in data:
        plan.crm_enabled = bool(data['crm_enabled'])
    if 'ai_assistant_enabled' in data:
        plan.ai_assistant_enabled = bool(data['ai_assistant_enabled'])

    plan.save()

    TenantAuditLog.objects.create(
        actor=request.user,
        action=AuditLogAction.PLAN_LIMITS_UPDATED,
        summary=f"Plan '{plan.name}' ({plan.code}) bundle updated by @{request.user.username}",
        details={
            'plan': plan.code,
            'max_staff': plan.max_staff,
            'max_contacts': plan.max_contacts,
            'max_services': plan.max_services,
            'max_documents': plan.max_documents,
            'monthly_message_allowance': plan.monthly_message_allowance,
            'enabled_modules': plan.enabled_modules,
        }
    )

    return JsonResponse({'status': 'ok', 'plan_code': plan.code, 'name': plan.name})


@api_login_required
@require_POST
def platform_copy_bundle_api(request):
    """Superadmin: safely copy bundle entitlements from one plan to another."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    data = _parse_body(request)
    src_code = data.get('source_plan_code')
    tgt_code = data.get('target_plan_code')

    if not src_code or not tgt_code:
        return JsonResponse({'error': 'source_plan_code and target_plan_code required.'}, status=400)

    src_plan = get_object_or_404(PlanTier, code=src_code)
    tgt_plan = get_object_or_404(PlanTier, code=tgt_code)

    tgt_plan.enabled_modules = list(src_plan.enabled_modules)
    tgt_plan.max_staff = src_plan.max_staff
    tgt_plan.max_contacts = src_plan.max_contacts
    tgt_plan.max_services = src_plan.max_services
    tgt_plan.max_documents = src_plan.max_documents
    tgt_plan.monthly_message_allowance = src_plan.monthly_message_allowance
    tgt_plan.crm_enabled = src_plan.crm_enabled
    tgt_plan.ai_assistant_enabled = src_plan.ai_assistant_enabled
    tgt_plan.save()

    TenantAuditLog.objects.create(
        actor=request.user,
        action=AuditLogAction.FEATURE_OVERRIDE_CHANGED,
        summary=f"Copied bundle entitlements from '{src_plan.name}' to '{tgt_plan.name}'",
        details={'source': src_plan.code, 'target': tgt_plan.code}
    )

    return JsonResponse({'status': 'ok', 'message': f"Copied bundle from {src_plan.name} to {tgt_plan.name}."})


@api_login_required
@require_http_methods(['GET', 'POST'])
def platform_tenant_overrides_api(request, tenant_id):
    """Superadmin: manage tenant-specific capability overrides (INHERIT/ALLOW/DENY)."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant_caps = [c for c in CAPABILITY_REGISTRY.values() if c.get('scope') == 'tenant']

    if request.method == 'GET':
        overrides = []
        for cap in tenant_caps:
            key = cap['key']
            current_override = tenant.get_feature_override(key)
            override_obj = tenant.feature_overrides.filter(feature_key=key).first()
            allowed, reason = can_access_capability(request.user, tenant, key)
            overrides.append({
                'feature_key': key,
                'name': cap['name'],
                'category': cap['category'],
                'override': current_override,
                'reason': override_obj.reason if override_obj else '',
                'effective_allowed': allowed,
                'explanation': reason,
            })
        return JsonResponse({'tenant_id': tenant.id, 'tenant_name': tenant.name, 'overrides': overrides})

    data = _parse_body(request)
    overrides_input = data.get('overrides', {})
    if isinstance(overrides_input, list):
        overrides_input = {item.get('feature_key'): item for item in overrides_input if item.get('feature_key')}

    with transaction.atomic():
        for cap in tenant_caps:
            key = cap['key']
            if key in overrides_input:
                item = overrides_input[key]
                val = item.get('override', 'INHERIT') if isinstance(item, dict) else str(item)
                reason = item.get('reason', '').strip() if isinstance(item, dict) else ''

                if val in ('ALLOW', 'DENY'):
                    override_obj, _ = TenantFeatureOverride.objects.get_or_create(
                        tenant=tenant,
                        feature_key=key,
                        defaults={'override': val, 'reason': reason, 'created_by': request.user}
                    )
                    override_obj.override = val
                    override_obj.reason = reason
                    override_obj.save()
                else:
                    TenantFeatureOverride.objects.filter(tenant=tenant, feature_key=key).delete()

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=request.user,
            action=AuditLogAction.FEATURE_OVERRIDE_CHANGED,
            summary=f"Updated capability overrides for '{tenant.name}' by @{request.user.username}",
            details={'tenant_id': tenant.id, 'overrides': overrides_input}
        )

    return JsonResponse({'status': 'ok', 'message': f"Updated capability overrides for {tenant.name}."})


@api_login_required
@require_POST
def platform_bulk_assign_preview_api(request):
    """Superadmin: preview impact of bulk plan assignment."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    data = _parse_body(request)
    target_plan_code = data.get('target_plan_code')
    tenant_ids = data.get('tenant_ids', [])

    if not target_plan_code or not tenant_ids:
        return JsonResponse({'error': 'target_plan_code and tenant_ids required.'}, status=400)

    target_plan = get_object_or_404(PlanTier, code=target_plan_code)
    tenants = Tenant.objects.filter(id__in=tenant_ids).select_related('subscription', 'subscription__effective_plan')

    impact_list = []
    for t in tenants:
        sub = getattr(t, 'subscription', None)
        curr_plan = sub.effective_plan if sub else None
        curr_staff = t.memberships.filter(is_active=True).count()
        curr_contacts = Customer.objects.filter(tenant=t).count()
        curr_docs = t.documents.filter(is_active=True).count()

        impact_list.append({
            'tenant_id': t.id,
            'name': t.name,
            'current_plan': curr_plan.name if curr_plan else t.get_plan_display(),
            'target_plan': target_plan.name,
            'staff_used': curr_staff,
            'staff_limit_new': target_plan.max_staff,
            'staff_overflow': max(0, curr_staff - target_plan.max_staff),
            'contacts_used': curr_contacts,
            'contacts_limit_new': target_plan.max_contacts,
            'contacts_overflow': max(0, curr_contacts - target_plan.max_contacts),
            'docs_used': curr_docs,
            'docs_limit_new': target_plan.max_documents,
            'message_allowance_new': target_plan.monthly_message_allowance,
        })

    return JsonResponse({
        'target_plan': {'code': target_plan.code, 'name': target_plan.name},
        'impact': impact_list,
        'total_tenants': len(impact_list),
    })


@api_login_required
@require_POST
def platform_bulk_assign_api(request):
    """Superadmin: execute bulk plan assignment with audit logging."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    data = _parse_body(request)
    target_plan_code = data.get('target_plan_code')
    tenant_ids = data.get('tenant_ids', [])
    confirm = data.get('confirm', False)

    if not target_plan_code or not tenant_ids:
        return JsonResponse({'error': 'target_plan_code and tenant_ids required.'}, status=400)
    if not confirm:
        return JsonResponse({'error': 'Explicit confirmation required.'}, status=400)

    target_plan = get_object_or_404(PlanTier, code=target_plan_code)
    tenants = Tenant.objects.filter(id__in=tenant_ids)

    with transaction.atomic():
        updated_count = 0
        for t in tenants:
            if hasattr(t, 'subscription'):
                t.subscription.effective_plan = target_plan
                t.subscription.save(update_fields=['effective_plan', 'updated_at'])
            t.max_staff = target_plan.max_staff
            t.max_services = target_plan.max_services
            t.save(update_fields=['max_staff', 'max_services', 'updated_at'])
            updated_count += 1

        TenantAuditLog.objects.create(
            actor=request.user,
            action=AuditLogAction.BULK_PLAN_ASSIGNED,
            summary=f"Bulk assigned plan '{target_plan.name}' to {updated_count} tenants by @{request.user.username}",
            details={'plan': target_plan.code, 'tenant_ids': tenant_ids}
        )

    return JsonResponse({
        'status': 'ok',
        'updated_count': updated_count,
        'plan': target_plan.name
    })


# ============================================================================
# ROADMAP EXTENSION APIS
# ============================================================================
import secrets
from django.http import HttpResponse
from apps.crm.models import (
    Quote, QuoteStatus,
    QualificationQuestion, LeadQualificationAnswer, LeadScore, LeadScorePriority,
    AutomationRule, AutomationRunLog, AutomationTrigger, AutomationActionType,
    SupportTicket, TicketNote, TicketPriority, TicketStatus,
    OnboardingChecklist, OnboardingTask,
    ContactConsent, Campaign,
    WebhookEndpoint, WebhookDeliveryLog, TenantIntegration
)
from apps.crm.assignment_service import get_sales_work_queue
from apps.crm.quote_service import create_or_version_quote, update_quote_status, get_quote_pdf_bytes
from apps.crm.automation_engine import dry_run_rule
from apps.crm.webhook_service import is_ssrf_safe_url


@api_login_required
@require_http_methods(['GET'])
def sales_work_queue_api(request):
    """Returns prioritized sales work queue items for tenant."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)
    data = get_sales_work_queue(tenant, request.user)
    return JsonResponse(data)


@api_login_required
@require_http_methods(['GET', 'POST'])
def qualification_api(request):
    """Retrieve qualification questions or submit progressive answers."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    if request.method == 'GET':
        contact_id = request.GET.get('contact_id')
        questions = QualificationQuestion.objects.filter(tenant=tenant)
        answers_map = {}
        if contact_id:
            for ans in LeadQualificationAnswer.objects.filter(tenant=tenant, contact_id=contact_id):
                answers_map[ans.question_id] = {
                    'answer_text': ans.answer_text,
                    'source_message': ans.source_message,
                    'is_verified': ans.is_verified_by_human
                }
        return JsonResponse({
            'questions': [
                {
                    'id': q.id,
                    'field_key': q.field_key,
                    'question_text': q.question_text,
                    'is_required': q.is_required,
                    'order': q.order,
                    'answer': answers_map.get(q.id)
                }
                for q in questions
            ]
        })

    data = _parse_body(request)
    contact_id = data.get('contact_id')
    question_id = data.get('question_id')
    answer_text = data.get('answer_text', '')
    source_msg = data.get('source_message', '')

    if not contact_id or not question_id:
        return JsonResponse({'error': 'contact_id and question_id required.'}, status=400)

    contact = get_object_or_404(Customer, tenant=tenant, id=contact_id)
    question = get_object_or_404(QualificationQuestion, tenant=tenant, id=question_id)

    ans, _ = LeadQualificationAnswer.objects.update_or_create(
        tenant=tenant,
        contact=contact,
        question=question,
        defaults={
            'answer_text': answer_text,
            'source_message': source_msg,
            'is_verified_by_human': True
        }
    )

    # Recalculate explainable score
    lead_score, _ = LeadScore.objects.get_or_create(tenant=tenant, contact=contact)
    lead_score.calculate_score()
    lead_score.save()

    try:
        from apps.crm.automation_engine import record_business_event, process_pending_business_events
        record_business_event(
            tenant=tenant,
            event_type='qualification.completed',
            entity_type='contact',
            entity_id=contact.id,
            payload={
                'score': lead_score.score,
                'priority': lead_score.priority,
                'contact_name': contact.name,
                'phone': contact.phone_number,
            },
            dedup_key=f"contact:{contact.id}:qualified:{int(timezone.now().timestamp())}"
        )
        transaction.on_commit(lambda: process_pending_business_events(tenant=tenant))
    except Exception:
        pass

    return JsonResponse({
        'status': 'saved',
        'score': lead_score.score,
        'priority': lead_score.priority,
        'breakdown': lead_score.score_breakdown
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def scoring_api(request, contact_id):
    """Retrieve explainable lead score or apply manual override."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    contact = get_object_or_404(Customer, tenant=tenant, id=contact_id)
    lead_score, _ = LeadScore.objects.get_or_create(tenant=tenant, contact=contact)

    if request.method == 'GET':
        lead_score.calculate_score()
        lead_score.save()
        return JsonResponse({
            'contact_id': contact.id,
            'score': lead_score.score,
            'priority': lead_score.priority,
            'breakdown': lead_score.score_breakdown,
            'rule_version': lead_score.rule_version,
            'is_manual_override': lead_score.is_manual_override,
            'override_reason': lead_score.override_reason
        })

    # Manual override
    data = _parse_body(request)
    override_score = int(data.get('score', lead_score.score))
    reason = data.get('reason', '')
    if not reason:
        return JsonResponse({'error': 'Reason required for manual score override.'}, status=400)

    lead_score.is_manual_override = True
    lead_score.score = max(0, min(100, override_score))
    lead_score.override_reason = reason
    lead_score.updated_by = request.user
    if lead_score.score >= 75:
        lead_score.priority = LeadScorePriority.URGENT
    elif lead_score.score >= 50:
        lead_score.priority = LeadScorePriority.HIGH
    elif lead_score.score >= 25:
        lead_score.priority = LeadScorePriority.MEDIUM
    else:
        lead_score.priority = LeadScorePriority.LOW
    lead_score.save()

    return JsonResponse({
        'status': 'overridden',
        'score': lead_score.score,
        'priority': lead_score.priority,
        'override_reason': lead_score.override_reason
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def deal_quotes_api(request, deal_id):
    """List or create versioned quotations for a deal."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    deal = get_object_or_404(Deal, tenant=tenant, id=deal_id)

    if request.method == 'GET':
        quotes = Quote.objects.filter(deal=deal).prefetch_related('items')
        return JsonResponse({
            'deal_id': deal.id,
            'deal_title': deal.title,
            'quotes': [
                {
                    'id': q.id,
                    'quote_number': q.quote_number,
                    'version': q.version,
                    'title': q.title,
                    'subtotal': str(q.subtotal),
                    'discount_amount': str(q.discount_amount),
                    'tax_percent': str(q.tax_percent),
                    'tax_amount': str(q.tax_amount),
                    'total_amount': str(q.total_amount),
                    'currency': q.currency,
                    'status': q.status,
                    'valid_until': q.valid_until.isoformat() if q.valid_until else None,
                    'created_at': q.created_at.isoformat(),
                    'items_count': q.items.count(),
                    'items': [
                        {
                            'id': item.id,
                            'description': item.description,
                            'quantity': str(item.quantity),
                            'unit_price': str(item.unit_price),
                            'discount_percent': str(item.discount_percent),
                            'total_price': str(item.total_price),
                        }
                        for item in q.items.all()
                    ]
                }
                for q in quotes
            ]
        })

    # Create or version quote
    data = _parse_body(request)
    title = data.get('title', f"Quotation for {deal.title}")
    items_data = data.get('items', [])
    discount = data.get('discount', 0)
    tax_percent = data.get('tax_percent', 18.0)
    terms = data.get('terms', '')

    if not items_data:
        return JsonResponse({'error': 'At least one line item is required.'}, status=400)

    quote = create_or_version_quote(
        deal=deal,
        title=title,
        items_data=items_data,
        user=request.user,
        discount=discount,
        tax_percent=tax_percent,
        terms=terms
    )

    return JsonResponse({
        'status': 'created',
        'quote_id': quote.id,
        'quote_number': quote.quote_number,
        'version': quote.version,
        'total_amount': str(quote.total_amount)
    }, status=201)


@api_login_required
@require_http_methods(['GET'])
def quote_pdf_api(request, quote_id):
    """Downloads generated quotation PDF."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    quote = get_object_or_404(Quote, tenant=tenant, id=quote_id)
    pdf_bytes = get_quote_pdf_bytes(quote)

    resp = HttpResponse(pdf_bytes, content_type='application/pdf')
    resp['Content-Disposition'] = f'attachment; filename="Quote_{quote.quote_number}_v{quote.version}.pdf"'
    return resp


@api_login_required
@require_http_methods(['POST'])
def quote_status_api(request, quote_id):
    """Transitions quotation status (DRAFT -> SENT -> APPROVED -> REJECTED)."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    quote = get_object_or_404(Quote, tenant=tenant, id=quote_id)
    data = _parse_body(request)
    new_status = data.get('status')
    if new_status not in QuoteStatus.values:
        return JsonResponse({'error': f"Invalid status: {new_status}"}, status=400)

    update_quote_status(quote, new_status, user=request.user)
    return JsonResponse({
        'status': 'updated',
        'quote_id': quote.id,
        'new_status': quote.status
    })


@api_login_required
@require_http_methods(['GET', 'POST'])
def automations_api(request):
    """List or create tenant workflow automation rules."""
    from apps.crm.models import AutomationTrigger, AutomationActionType
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)
    action_perm = 'view' if request.method == 'GET' else 'create'
    allowed, reason = can_perform_action(request.user, tenant, 'automations', action_perm)
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    if request.method == 'GET':
        rules = AutomationRule.objects.filter(tenant=tenant)
        recent_logs = AutomationRunLog.objects.filter(tenant=tenant)[:15]
        return JsonResponse({
            'rules': [
                {
                    'id': r.id,
                    'name': r.name,
                    'description': r.description,
                    'trigger_type': r.trigger_type,
                    'trigger_display': r.get_trigger_type_display(),
                    'conditions': r.conditions,
                    'action_type': r.action_type,
                    'action_display': r.get_action_type_display(),
                    'action_config': r.action_config,
                    'is_active': r.is_active,
                    'execution_count': r.execution_count,
                    'created_at': r.created_at.isoformat()
                }
                for r in rules
            ],
            'recent_logs': [
                {
                    'id': l.id,
                    'rule_id': l.rule_id,
                    'event': l.trigger_event,
                    'status': l.status,
                    'details': l.details,
                    'executed_at': l.executed_at.isoformat()
                }
                for l in recent_logs
            ],
            'triggers': [{'value': v, 'label': lbl} for v, lbl in AutomationTrigger.choices],
            'actions': [{'value': v, 'label': lbl} for v, lbl in AutomationActionType.choices],
        })

    data = _parse_body(request)
    name = str(data.get('name') or '').strip()[:150]
    trigger_type = data.get('trigger_type')
    action_type = data.get('action_type')
    conditions = data.get('conditions', {})
    action_config = data.get('action_config', {})

    if not name or not trigger_type or not action_type:
        return JsonResponse({'error': 'name, trigger_type, and action_type required.'}, status=400)
    if trigger_type not in AutomationTrigger.values or action_type not in AutomationActionType.values:
        return JsonResponse({'error': 'Invalid automation trigger or action type.'}, status=400)
    if not isinstance(conditions, dict) or not isinstance(action_config, dict):
        return JsonResponse({'error': 'conditions and action_config must be JSON objects.'}, status=400)

    rule = AutomationRule.objects.create(
        tenant=tenant,
        name=name,
        description=str(data.get('description', '') or '')[:500],
        trigger_type=trigger_type,
        conditions=conditions,
        action_type=action_type,
        action_config=action_config,
        is_active=bool(data.get('is_active', True))
    )

    return JsonResponse({'status': 'created', 'rule_id': rule.id}, status=201)


@api_login_required
@require_http_methods(['GET', 'POST'])
def automation_settings_api(request):
    """Get or update tenant business hours, away auto-reply, greeting, auto-assignment, and follow-up timer."""
    from apps.business.models import BusinessProfile
    from apps.crm.business_hours import default_business_hours, is_within_business_hours, normalize_business_hours

    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)
    allowed, reason = can_perform_action(
        request.user, tenant, 'automations', 'view' if request.method == 'GET' else 'create'
    )
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    profile = BusinessProfile.objects.filter(tenant=tenant, is_active=True).first()
    if request.method == 'GET':
        bh = normalize_business_hours(profile.business_hours if profile else None, tenant.timezone or 'Asia/Kolkata')
        return JsonResponse({
            'business_hours': bh,
            'currently_open': is_within_business_hours(profile),
            'after_hours_auto_reply': profile.after_hours_auto_reply if profile else '',
            'greeting_auto_reply': profile.greeting_auto_reply if profile else '',
            'auto_assign_inbound': bool(profile and profile.auto_assign_inbound),
            'no_response_followup_minutes': int(profile.no_response_followup_minutes) if profile else 0,
        })

    if not user_can_manage_tenant(request.user, tenant):
        return JsonResponse({'error': 'Owner or Administrator access required.'}, status=403)
    if not profile:
        profile = BusinessProfile.objects.create(tenant=tenant, shop_name=tenant.name)

    data = _parse_body(request)
    try:
        if 'business_hours' in data:
            profile.business_hours = normalize_business_hours(data['business_hours'], tenant.timezone or 'Asia/Kolkata')
        elif not profile.business_hours:
            profile.business_hours = default_business_hours(tenant.timezone or 'Asia/Kolkata')
        if 'after_hours_auto_reply' in data:
            profile.after_hours_auto_reply = str(data['after_hours_auto_reply'] or '').strip()[:1000]
        if 'greeting_auto_reply' in data:
            profile.greeting_auto_reply = str(data['greeting_auto_reply'] or '').strip()[:1000]
        if 'auto_assign_inbound' in data:
            profile.auto_assign_inbound = bool(data['auto_assign_inbound'])
        if 'no_response_followup_minutes' in data:
            mins = int(data['no_response_followup_minutes'])
            if not 0 <= mins <= 10080:
                raise ValueError('Follow-up timer must be between 0 and 10080 minutes.')
            profile.no_response_followup_minutes = mins
    except (ValueError, TypeError) as exc:
        return JsonResponse({'error': str(exc) or 'Invalid automation settings.'}, status=400)

    profile.save()
    return JsonResponse({
        'status': 'saved',
        'business_hours': profile.business_hours,
        'currently_open': is_within_business_hours(profile),
        'after_hours_auto_reply': profile.after_hours_auto_reply,
        'greeting_auto_reply': profile.greeting_auto_reply,
        'auto_assign_inbound': profile.auto_assign_inbound,
        'no_response_followup_minutes': profile.no_response_followup_minutes,
    })


@api_login_required
@require_http_methods(['POST'])
def automation_toggle_api(request, rule_id):
    """Enables or disables an automation rule."""
    tenant = getattr(request, 'tenant', None)
    rule = get_object_or_404(AutomationRule, tenant=tenant, id=rule_id)
    rule.is_active = not rule.is_active
    rule.save(update_fields=['is_active', 'updated_at'])
    return JsonResponse({'status': 'ok', 'is_active': rule.is_active})


@api_login_required
@require_http_methods(['POST'])
def automation_dry_run_api(request, rule_id):
    """Executes a dry-run preview of an automation rule."""
    tenant = getattr(request, 'tenant', None)
    rule = get_object_or_404(AutomationRule, tenant=tenant, id=rule_id)
    data = _parse_body(request)
    sample_context = data.get('sample_context', {})
    preview = dry_run_rule(rule, sample_context)
    return JsonResponse(preview)


@api_login_required
@require_http_methods(['GET', 'POST'])
def support_tickets_api(request):
    """List or create customer support tickets."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    if request.method == 'GET':
        tickets = SupportTicket.objects.filter(tenant=tenant).select_related('contact', 'assigned_to')
        status_filter = request.GET.get('status')
        if status_filter:
            tickets = tickets.filter(status=status_filter)
        return JsonResponse({
            'tickets': [
                {
                    'id': t.id,
                    'ticket_number': t.ticket_number,
                    'contact_id': t.contact_id,
                    'contact_name': t.contact.name or t.contact.phone_number,
                    'contact_phone': t.contact.phone_number,
                    'subject': t.subject,
                    'description': t.description,
                    'category': t.category,
                    'priority': t.priority,
                    'status': t.status,
                    'assigned_to': t.assigned_to.username if t.assigned_to else 'Unassigned',
                    'response_target_hours': t.response_target_hours,
                    'resolution_reason': t.resolution_reason,
                    'created_at': t.created_at.isoformat()
                }
                for t in tickets[:50]
            ]
        })

    data = _parse_body(request)
    contact_id = data.get('contact_id')
    subject = data.get('subject')
    description = data.get('description', '')
    category = data.get('category', 'GENERAL')
    priority = data.get('priority', TicketPriority.MEDIUM)

    if not contact_id or not subject:
        return JsonResponse({'error': 'contact_id and subject required.'}, status=400)

    contact = get_object_or_404(Customer, tenant=tenant, id=contact_id)
    count = SupportTicket.objects.filter(tenant=tenant).count() + 1
    ticket_num = f"TICK-{count:04d}"

    target_hours = 4 if priority == TicketPriority.URGENT else (8 if priority == TicketPriority.HIGH else 24)

    ticket = SupportTicket.objects.create(
        tenant=tenant,
        ticket_number=ticket_num,
        contact=contact,
        subject=subject,
        description=description,
        category=category,
        priority=priority,
        status=TicketStatus.OPEN,
        assigned_to=request.user,
        response_target_hours=target_hours
    )

    try:
        from apps.crm.automation_engine import record_business_event, process_pending_business_events
        record_business_event(
            tenant=tenant,
            event_type='ticket.created',
            entity_type='ticket',
            entity_id=ticket.id,
            payload={
                'ticket_number': ticket.ticket_number,
                'priority': ticket.priority,
                'subject': ticket.subject,
                'contact_id': contact.id,
            },
            dedup_key=f"ticket:{ticket.id}:created"
        )
        transaction.on_commit(lambda: process_pending_business_events(tenant=tenant))
    except Exception:
        pass

    return JsonResponse({'status': 'created', 'ticket_id': ticket.id, 'ticket_number': ticket.ticket_number}, status=201)


@api_login_required
@require_http_methods(['POST'])
def ticket_status_api(request, ticket_id):
    """Updates ticket status, reassignment, or records resolution reason."""
    tenant = getattr(request, 'tenant', None)
    ticket = get_object_or_404(SupportTicket, tenant=tenant, id=ticket_id)
    data = _parse_body(request)
    new_status = data.get('status')
    resolution = data.get('resolution_reason', '')

    if new_status in TicketStatus.values:
        ticket.status = new_status
        if new_status == TicketStatus.RESOLVED:
            ticket.resolved_at = timezone.now()
            ticket.resolution_reason = resolution or "Resolved by staff"
        ticket.save(update_fields=['status', 'resolved_at', 'resolution_reason', 'updated_at'])

        try:
            from apps.crm.automation_engine import record_business_event, process_pending_business_events
            record_business_event(
                tenant=tenant,
                event_type='ticket.status_changed',
                entity_type='ticket',
                entity_id=ticket.id,
                payload={
                    'ticket_number': ticket.ticket_number,
                    'status': ticket.status,
                    'resolution_reason': ticket.resolution_reason,
                },
                dedup_key=f"ticket:{ticket.id}:status:{new_status}:{int(timezone.now().timestamp())}"
            )
            transaction.on_commit(lambda: process_pending_business_events(tenant=tenant))
        except Exception:
            pass

    return JsonResponse({'status': 'updated', 'ticket_status': ticket.status})


@api_login_required
@require_http_methods(['GET', 'POST'])
def ticket_notes_api(request, ticket_id):
    """Internal notes for a support ticket."""
    tenant = getattr(request, 'tenant', None)
    ticket = get_object_or_404(SupportTicket, tenant=tenant, id=ticket_id)

    if request.method == 'GET':
        notes = ticket.notes.all().select_related('author')
        return JsonResponse({
            'notes': [
                {
                    'id': n.id,
                    'author': n.author.username if n.author else 'System',
                    'content': n.content,
                    'created_at': n.created_at.isoformat()
                }
                for n in notes
            ]
        })

    data = _parse_body(request)
    content = data.get('content')
    if not content:
        return JsonResponse({'error': 'content required.'}, status=400)

    note = TicketNote.objects.create(
        ticket=ticket,
        author=request.user,
        content=content,
        is_internal=True
    )
    return JsonResponse({'status': 'created', 'note_id': note.id}, status=201)


@api_login_required
@require_http_methods(['GET'])
def onboarding_checklists_api(request):
    """List post-sale customer onboarding checklists and actionable tasks."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    checklists = OnboardingChecklist.objects.filter(tenant=tenant).prefetch_related('tasks').select_related('deal', 'contact')
    return JsonResponse({
        'checklists': [
            {
                'id': c.id,
                'title': c.title,
                'deal_id': c.deal_id,
                'deal_title': c.deal.title if c.deal else None,
                'contact_name': c.contact.name or c.contact.phone_number if c.contact else None,
                'is_completed': c.is_completed,
                'target_date': c.target_completion_date.isoformat() if c.target_completion_date else None,
                'tasks': [
                    {
                        'id': t.id,
                        'title': t.title,
                        'order': t.order,
                        'is_done': t.is_done,
                        'completed_at': t.completed_at.isoformat() if t.completed_at else None
                    }
                    for t in c.tasks.all()
                ]
            }
            for c in checklists
        ]
    })


@api_login_required
@require_http_methods(['POST'])
def onboarding_task_toggle_api(request, task_id):
    """Toggle completion status of an onboarding task."""
    tenant = getattr(request, 'tenant', None)
    task = get_object_or_404(OnboardingTask, checklist__tenant=tenant, id=task_id)
    task.is_done = not task.is_done
    task.completed_at = timezone.now() if task.is_done else None
    task.completed_by = request.user if task.is_done else None
    task.save(update_fields=['is_done', 'completed_at', 'completed_by'])

    # Update checklist completed state if all tasks done
    checklist = task.checklist
    all_done = not checklist.tasks.filter(is_done=False).exists()
    checklist.is_completed = all_done
    checklist.save(update_fields=['is_completed', 'updated_at'])

    return JsonResponse({'status': 'ok', 'is_done': task.is_done, 'checklist_completed': checklist.is_completed})


@api_login_required
@require_http_methods(['GET', 'POST'])
def contact_consent_api(request, contact_id):
    """Retrieve or update outbound messaging consent & opt-out suppression."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    contact = get_object_or_404(Customer, tenant=tenant, id=contact_id)
    consent, _ = ContactConsent.objects.get_or_create(tenant=tenant, contact=contact)

    if request.method == 'GET':
        return JsonResponse({
            'contact_id': contact.id,
            'phone': contact.phone_number,
            'has_consented': consent.has_consented,
            'source': consent.source,
            'purpose': consent.purpose,
            'evidence_text': consent.evidence_text,
            'is_opted_out': consent.is_opted_out,
            'opted_out_at': consent.opted_out_at.isoformat() if consent.opted_out_at else None
        })

    data = _parse_body(request)
    if 'is_opted_out' in data:
        consent.is_opted_out = bool(data['is_opted_out'])
        consent.opted_out_at = timezone.now() if consent.is_opted_out else None
    if 'source' in data:
        consent.source = data['source']
    if 'evidence_text' in data:
        consent.evidence_text = data['evidence_text']
    consent.save()

    return JsonResponse({'status': 'saved', 'is_opted_out': consent.is_opted_out})


@api_login_required
@require_http_methods(['GET', 'POST'])
def campaigns_api(request):
    """List or draft outbound campaigns with WhatsApp template selection."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    if request.method == 'GET':
        campaigns = Campaign.objects.filter(tenant=tenant)
        templates = WhatsAppTemplate.objects.filter(tenant=tenant)
        return JsonResponse({
            'campaigns': [
                {
                    'id': c.id,
                    'name': c.name,
                    'status': c.status,
                    'template_name': c.template.name if c.template else None,
                    'audience_count': c.audience_count,
                    'sent_count': c.sent_count,
                    'delivered_count': c.delivered_count,
                    'created_at': c.created_at.isoformat()
                }
                for c in campaigns
            ],
            'templates': [
                {
                    'id': t.id,
                    'name': t.name,
                    'category': t.category,
                    'language': t.language,
                    'body_text': t.body_text,
                    'meta_status': t.meta_status
                }
                for t in templates
            ]
        })

    data = _parse_body(request)
    name = data.get('name')
    template_id = data.get('template_id')
    lifecycle = data.get('target_lifecycle_status', '')

    if not name:
        return JsonResponse({'error': 'name required.'}, status=400)

    template = WhatsAppTemplate.objects.filter(tenant=tenant, id=template_id).first() if template_id else None

    # Calculate eligible audience: strictly excluding opted-out contacts
    audience_qs = Customer.objects.filter(tenant=tenant)
    if lifecycle:
        audience_qs = audience_qs.filter(lifecycle_status=lifecycle)
    audience_count = audience_qs.exclude(consent_record__is_opted_out=True).count()

    campaign = Campaign.objects.create(
        tenant=tenant,
        name=name,
        template=template,
        status='DRAFT',
        target_lifecycle_status=lifecycle,
        audience_count=audience_count,
        created_by=request.user
    )

    return JsonResponse({'status': 'created', 'campaign_id': campaign.id, 'audience_count': audience_count}, status=201)


@api_login_required
@require_http_methods(['GET'])
def integrations_api(request):
    """List external connector statuses (Calendar, CRM, E-Commerce)."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    connectors = [
        {'type': 'CALENDAR', 'name': 'Google Calendar / Outlook Sync', 'status': 'UNCONFIGURED', 'doc': 'Two-way consultation availability sync.'},
        {'type': 'CRM_CONNECTOR', 'name': 'External CRM (HubSpot / Zoho)', 'status': 'UNCONFIGURED', 'doc': 'Lead & opportunity record mirror.'},
        {'type': 'COMMERCE', 'name': 'E-Commerce (Shopify / WooCommerce)', 'status': 'UNCONFIGURED', 'doc': 'Live catalog and order sync.'},
    ]

    saved_ints = {i.integration_type: i for i in TenantIntegration.objects.filter(tenant=tenant)}
    for c in connectors:
        if c['type'] in saved_ints:
            c['status'] = saved_ints[c['type']].status

    return JsonResponse({'connectors': connectors})


@api_login_required
@require_http_methods(['GET', 'POST'])
def webhooks_api(request):
    """List and manage tenant signed outbound webhook endpoints."""
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'No active workspace.'}, status=400)

    if request.method == 'GET':
        endpoints = WebhookEndpoint.objects.filter(tenant=tenant)
        logs = WebhookDeliveryLog.objects.filter(endpoint__tenant=tenant)[:20]
        return JsonResponse({
            'endpoints': [
                {
                    'id': ep.id,
                    'target_url': ep.target_url,
                    'subscribed_events': ep.subscribed_events,
                    'is_active': ep.is_active,
                    'created_at': ep.created_at.isoformat()
                }
                for ep in endpoints
            ],
            'recent_deliveries': [
                {
                    'id': l.id,
                    'event_type': l.event_type,
                    'status_code': l.status_code,
                    'is_success': l.is_success,
                    'attempts': l.attempts,
                    'response': l.response_body[:100],
                    'created_at': l.created_at.isoformat()
                }
                for l in logs
            ]
        })

    data = _parse_body(request)
    target_url = data.get('target_url')
    subscribed = data.get('subscribed_events', ['*'])
    if not target_url:
        return JsonResponse({'error': 'target_url required.'}, status=400)

    if not is_ssrf_safe_url(target_url):
        return JsonResponse({'error': 'Target URL violates SSRF security rules.'}, status=400)

    endpoint = WebhookEndpoint.objects.create(
        tenant=tenant,
        target_url=target_url,
        signing_secret=secrets.token_hex(24),
        subscribed_events=subscribed,
        is_active=True
    )
    return JsonResponse({'status': 'created', 'endpoint_id': endpoint.id}, status=201)


@api_login_required
@require_http_methods(['POST'])
def platform_tenant_outbound_pause_api(request, tenant_id):
    """Super Admin: toggle or set per-client outbound WhatsApp delivery pause."""
    from .platform_auth import can_platform_access
    allowed, reason = can_platform_access(request.user, 'outbound_pause', write=True)
    if not allowed:
        return JsonResponse({'error': reason}, status=403)

    tenant = get_object_or_404(Tenant, id=tenant_id)
    data = _parse_body(request)
    paused = bool(data['paused']) if 'paused' in data else (not tenant.outbound_paused)
    pause_reason = str(data.get('reason') or '').strip()[:255] if paused else ''
    tenant.outbound_paused = paused
    tenant.outbound_pause_reason = pause_reason
    tenant.save(update_fields=['outbound_paused', 'outbound_pause_reason', 'updated_at'])

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.OUTBOUND_PAUSE_CHANGED,
        summary=f"Client outbound WhatsApp {'paused' if paused else 'resumed'} for '{tenant.name}'",
        details={'outbound_paused': paused, 'reason': pause_reason},
    )
    return JsonResponse({
        'status': 'ok',
        'tenant_id': tenant.id,
        'outbound_paused': tenant.outbound_paused,
        'outbound_pause_reason': tenant.outbound_pause_reason,
    })


@api_login_required
@require_http_methods(['GET'])
def platform_monitoring_api(request):
    """Platform Operator: operational health monitoring across webhooks, delivery, and expired leases."""
    from datetime import timedelta
    from .platform_auth import can_platform_access
    from .models import PlatformServiceConfig
    from apps.whatsapp.models import WhatsAppDelivery
    from apps.chatbot.models import Customer
    from apps.crm.models import BusinessEvent

    allowed, reason = can_platform_access(request.user, 'health', write=False)
    if not allowed:
        return JsonResponse({'error': reason}, status=403)

    now = timezone.now()
    expired_customer_leases = Customer.objects.filter(processing_until__lt=now).exclude(processing_token='').count()
    active_customer_leases = Customer.objects.filter(processing_until__gt=now).exclude(processing_token='').count()
    expired_event_leases = BusinessEvent.objects.filter(status='PROCESSING', lease_expires_at__lt=now).count()
    expired_webhook_leases = WebhookDeliveryLog.objects.filter(state='PROCESSING', lease_expires_at__lt=now).count()
    expired_delivery_leases = WhatsAppDelivery.objects.filter(status='SENDING', updated_at__lt=now - timedelta(minutes=10)).count()

    stalled_leases_count = expired_customer_leases + expired_event_leases + expired_webhook_leases + expired_delivery_leases
    failed_webhooks_count = WebhookDeliveryLog.objects.filter(is_success=False).count()
    failed_automations_count = AutomationRunLog.objects.filter(status='FAILED').count()
    failed_deliveries_count = WhatsAppDelivery.objects.filter(status='FAILED').count()
    cfg = PlatformServiceConfig.objects.filter(pk=1).first()

    return JsonResponse({
        'stalled_leases_count': stalled_leases_count,
        'active_leases_count': active_customer_leases,
        'expired_customer_leases': expired_customer_leases,
        'expired_event_leases': expired_event_leases,
        'expired_webhook_leases': expired_webhook_leases,
        'expired_delivery_leases': expired_delivery_leases,
        'failed_webhooks_count': failed_webhooks_count,
        'failed_automations_count': failed_automations_count,
        'failed_deliveries_count': failed_deliveries_count,
        'global_outbound_paused': bool(cfg and cfg.global_outbound_paused),
        'maintenance_mode': bool(cfg and cfg.maintenance_mode),
        'overall_health': 'HEALTHY' if (failed_deliveries_count == 0 and stalled_leases_count == 0 and not (cfg and cfg.global_outbound_paused)) else 'ATTENTION_NEEDED'
    })


@api_login_required
@require_http_methods(['POST'])
def platform_client_create_api(request):
    """Super Admin provisioning wizard: create new client workspace and provision admin."""
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    # Both public Super Admin routes share the same provisioning invariants.
    response = platform_tenants_api(request)
    if response.status_code != 201:
        return response
    result = json.loads(response.content)
    tenant = result['tenant']
    result.update(
        tenant_id=tenant['id'],
        tenant_name=tenant['name'],
        admin_username=tenant['owner_username'],
    )
    if result.get('activation_url'):
        from urllib.parse import urlsplit
        result['activation_url'] = urlsplit(result['activation_url']).path
    return JsonResponse(result, status=201)
