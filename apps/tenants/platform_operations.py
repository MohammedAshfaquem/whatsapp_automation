"""Platform-only diagnostics. Explicit schemas intentionally exclude content and credentials."""
import json
import re
from functools import wraps
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from apps.whatsapp.models import WhatsAppDelivery, WhatsAppWebhookLog, WhatsAppConfig
from apps.chatbot.models import Customer, Conversation
from apps.bookings.models import Booking
from apps.services.models import Service
from apps.business.models import Product
from apps.crm.models import WhatsAppTemplate
from .models import AuditLogAction, PlatformOperatorRole, TenantAuditLog, UserSecurityProfile
from .onboarding_service import revoke_user_sessions
from .platform_auth import can_platform_access, get_platform_role, is_platform_operator

User = get_user_model()
# model, response fields, searchable fields, status field
RESOURCES = {
    'deliveries': (WhatsAppDelivery, ('id','recipient_phone','status','provider_message_id','attempts','created_at','updated_at'), ('recipient_phone','provider_message_id'), 'status'),
    'webhooks': (WhatsAppWebhookLog, ('id','event_type','whatsapp_message_id','sender_phone','is_processed','created_at'), ('whatsapp_message_id','sender_phone','event_type'), 'is_processed'),
    'contacts': (Customer, ('id','name','email','phone_number','lifecycle_status','source','owner_id','created_at'), ('name','email','phone_number'), 'lifecycle_status'),
    'conversations': (Conversation, ('id','customer_id','channel','status','assigned_staff_id','last_message_at','created_at'), ('customer__name','customer__phone_number'), 'status'),
    'bookings': (Booking, ('id','customer_id','service_id','product_id','request_type','status','preferred_date','created_at'), ('customer__name','customer__phone_number'), 'status'),
    'services': (Service, ('id','name','category','price_type','price_amount','currency','is_active','created_at'), ('name','category'), 'is_active'),
    'products': (Product, ('id','name','is_active','created_at'), ('name',), 'is_active'),
    'templates': (WhatsAppTemplate, ('id','name','category','language','meta_status','created_at'), ('name','category'), 'meta_status'),
    'configurations': (WhatsAppConfig, ('id','is_enabled','updated_at'), (), 'is_enabled'),
    'users': (User, ('id','username','email','is_active','is_superuser'), ('username','email','first_name','last_name'), 'is_active'),
}


def _error(message, status=400):
    return JsonResponse({'error': message}, status=status)


def _platform_only(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_active or not is_platform_operator(request.user):
            return _error('Platform administrator access required.', 403)
        return view(request, *args, **kwargs)
    return wrapped


def sanitize_error(value):
    """Remove credential assignments, bearer tokens and URLs from provider diagnostics."""
    value = str(value or '')[:4000]
    value = re.sub(r"""(?ix)(["']?(?:access_token|refresh_token|verify_token|app_secret|client_secret|api_key|authorization|password|token)["']?\s*[:=]\s*)(["'])(?:\\.|(?!\2).)*?\2""", r'\1[redacted]', value)
    value = re.sub(r'(?i)bearer\s+[^\s,;\"\']+', 'Bearer [redacted]', value)
    value = re.sub(r'''(?ix)(["']?(?:access_token|refresh_token|verify_token|app_secret|client_secret|api_key|authorization|password|token)["']?\s*[:=]\s*)["']?[^\s,;}"']+["']?''', r'\1[redacted]', value)
    value = re.sub(r'https?://[^\s]+', '[url redacted]', value)
    value = re.sub(r'\bEAA[A-Za-z0-9_-]{12,}\b', '[redacted]', value)
    return value


def _serialize(obj, resource, detail=False):
    fields = RESOURCES[resource][1]
    item = {field: getattr(obj, field) for field in fields}
    if resource == 'users':
        p_role = get_platform_role(obj)
        item.update(full_name=obj.get_full_name(), role='PLATFORM_ADMIN' if (obj.is_superuser or p_role) else 'USER', platform_role=p_role, workspaces=[{
            'tenant_id': m.tenant_id, 'tenant_name': m.tenant.name, 'role': m.role, 'is_active': m.is_active,
        } for m in obj.tenant_memberships.all()])
    else:
        item.update(tenant_id=obj.tenant_id, tenant_name=obj.tenant.name if obj.tenant_id else None,
                    tenant_url=f'/platform/tenants/{obj.tenant_id}' if obj.tenant_id else None)
    if resource == 'configurations':
        item.update(phone_number_id_masked=('***'+obj.phone_number_id[-4:]) if obj.phone_number_id else '',
                    business_account_id_masked=('***'+obj.business_account_id[-4:]) if obj.business_account_id else '',
                    has_access_token=bool(obj.access_token), has_app_secret=bool(obj.app_secret), has_verify_token=bool(obj.verify_token))
    if detail and resource == 'deliveries':
        payload_type = obj.payload.get('type') if isinstance(obj.payload, dict) else None
        item.update(last_error=sanitize_error(obj.last_error), quota_reserved=obj.quota_reserved,
                    payload_type=payload_type if payload_type in ('text','template','image','audio','video','document','interactive','reaction','location','contacts','sticker') else 'unknown')
    if detail and resource == 'webhooks':
        item['error_message'] = sanitize_error(obj.error_message)
    return item


def _query(resource):
    model = RESOURCES[resource][0]
    query = model.objects.all()
    return query.prefetch_related('tenant_memberships__tenant') if resource == 'users' else query.select_related('tenant')


@_platform_only
def platform_operations(request, resource):
    if request.method != 'GET':
        return _error('Method not allowed.', 405)
    if resource not in RESOURCES:
        return _error('Unknown resource.', 404)
    if resource != 'users':
        return _error('WhatsApp and business operations are managed inside the client workspace.', 403)
    try:
        page = int(request.GET.get('page', 1))
        page_size = min(int(request.GET.get('page_size', 25)), 100)
        if page < 1 or page_size < 1:
            raise ValueError
        tenant = request.GET.get('tenant') or request.GET.get('tenant_id') or None
        if tenant is not None:
            tenant = int(tenant)
            if tenant < 1:
                raise ValueError
    except (ValueError, TypeError):
        return _error('Invalid pagination or tenant filter.')
    query = _query(resource)
    if tenant is not None:
        query = query.filter(**({'tenant_memberships__tenant_id':tenant} if resource == 'users' else {'tenant_id':tenant})).distinct()
    status = request.GET.get('status', '').strip()
    status_field = RESOURCES[resource][3]
    if status:
        if status_field in ('is_active','is_processed','is_enabled'):
            if status.lower() not in ('true','false','1','0','active','inactive','processed','pending'):
                return _error('Invalid status filter.')
            status = status.lower() in ('true','1','active','processed')
        query = query.filter(**{status_field:status})
    search = request.GET.get('q', '').strip()[:200]
    if search:
        clause = Q(pk=int(search)) if search.isdecimal() else Q(pk__in=[])
        for field in RESOURCES[resource][2]:
            clause |= Q(**{field+'__icontains':search})
        query = query.filter(clause)
    total = query.count()
    rows = query.order_by('-pk')[(page-1)*page_size:page*page_size]
    return JsonResponse({'resource':resource, 'items':[_serialize(obj,resource) for obj in rows], 'total':total, 'page':page, 'page_size':page_size})


@_platform_only
def platform_operation_detail(request, resource, pk):
    if resource not in RESOURCES:
        return _error('Unknown resource.', 404)
    if resource != 'users':
        return _error('WhatsApp and business operations are managed inside the client workspace.', 403)
    if request.method not in ('GET','PATCH') or (request.method == 'PATCH' and resource != 'users'):
        return _error('Method not allowed.', 405)
    try:
        pk = int(pk)
    except (ValueError, TypeError):
        return _error('Resource not found.', 404)
    if request.method == 'GET':
        obj = _query(resource).filter(pk=pk).first()
        return JsonResponse({'item':_serialize(obj,resource,True)}) if obj else _error('Resource not found.',404)
    try:
        data = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return _error('Invalid JSON.')
    allowed = {'username', 'full_name', 'email', 'is_active', 'platform_role'}
    if not isinstance(data, dict) or not data or set(data)-allowed:
        return _error('Only username, full_name, email, is_active and platform_role may be updated.')
    can_edit_users, edit_reason = can_platform_access(request.user, 'users', write=True)
    if not can_edit_users:
        return _error(edit_reason, 403)
    if 'platform_role' in data:
        can_roles, role_reason = can_platform_access(request.user, 'operator_roles', write=True)
        if not can_roles:
            return _error(role_reason, 403)
        if not isinstance(data['platform_role'], str) or (data['platform_role'] and data['platform_role'] not in PlatformOperatorRole.values):
            return _error('Invalid platform_role. Choose SUPER_ADMIN, SUPPORT, BILLING, READ_ONLY, or blank.')
    for field in ('username','full_name','email'):
        if field in data and not isinstance(data[field], str):
            return _error('Identity fields must be strings.')
    if 'is_active' in data and type(data['is_active']) is not bool:
        return _error('is_active must be a boolean.')
    try:
        with transaction.atomic():
            # Lock active platform identities as well as the target before disabling an account.
            list(User.objects.select_for_update().filter(is_superuser=True, is_active=True).order_by('pk'))
            obj = User.objects.select_for_update().filter(pk=pk).first()
            if not obj:
                return _error('Resource not found.',404)
            if data.get('is_active') is False:
                if obj.pk == request.user.pk:
                    return _error('You cannot disable your own account.')
                if obj.is_superuser and not User.objects.filter(is_superuser=True,is_active=True).exclude(pk=obj.pk).exists():
                    return _error('The last active platform administrator cannot be disabled.')
            if 'platform_role' in data:
                new_role = data['platform_role']
                if obj.pk == request.user.pk and new_role != PlatformOperatorRole.SUPER_ADMIN:
                    return _error('You cannot remove your own SUPER_ADMIN platform role.')
                if obj.is_superuser and new_role not in ('', PlatformOperatorRole.SUPER_ADMIN):
                    if not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=obj.pk).exists():
                        return _error('The last active SUPER_ADMIN cannot be demoted.')
            if 'username' in data:
                obj.username = data['username'].strip()
                if not obj.username:
                    return _error('Username is required.')
            if 'full_name' in data:
                parts = data['full_name'].strip().split(' ',1)
                obj.first_name, obj.last_name = parts[0], parts[1] if len(parts)>1 else ''
            if 'email' in data:
                obj.email = data['email'].strip()
                if obj.email:
                    validate_email(obj.email)
            if 'is_active' in data:
                obj.is_active = data['is_active']
                if not obj.is_active:
                    revoke_user_sessions(obj)
            if 'platform_role' in data:
                new_role = data['platform_role']
                sec = UserSecurityProfile.get_or_create_for_user(obj)
                sec.platform_role = new_role
                sec.save(update_fields=['platform_role', 'updated_at'])
                if new_role and not obj.is_staff:
                    obj.is_staff = True
            obj.full_clean(exclude=['password'])
            obj.save()
            TenantAuditLog.objects.create(
                actor=request.user,
                action=AuditLogAction.OPERATOR_ROLE_CHANGED if 'platform_role' in data else 'USER_UPDATED',
                summary='Platform administrator updated user identity or operator role.',
                details={'user_id': obj.pk, 'fields': sorted(data)},
            )
    except (ValidationError, IntegrityError):
        return _error('Invalid identity fields or username already in use.')
    return JsonResponse({'item':_serialize(_query('users').get(pk=pk),'users')})


@_platform_only
def platform_user_revoke_sessions(request, pk):
    """Super Admin: immediately revoke all active DB-backed sessions for an operator or user."""
    if request.method != 'POST':
        return _error('Method not allowed.', 405)
    allowed, reason = can_platform_access(request.user, 'session_revoke', write=True)
    if not allowed:
        return _error(reason, 403)
    try:
        pk = int(pk)
    except (ValueError, TypeError):
        return _error('Resource not found.', 404)
    obj = User.objects.filter(pk=pk).first()
    if not obj:
        return _error('Resource not found.', 404)
    keep_key = request.session.session_key if obj.pk == request.user.pk else None
    revoked_count = revoke_user_sessions(obj, keep_session_key=keep_key)
    TenantAuditLog.objects.create(
        actor=request.user,
        action='USER_UPDATED',
        summary=f"Revoked {revoked_count} active session(s) for @{obj.username}",
        details={'user_id': obj.pk, 'revoked_sessions': revoked_count},
    )
    return JsonResponse({'status': 'revoked', 'user_id': obj.pk, 'revoked_sessions': revoked_count})
