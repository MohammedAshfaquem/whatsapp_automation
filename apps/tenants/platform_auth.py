"""
Platform Operator RBAC, least-privilege guards, lease reclamation, and system settings helpers.
"""
from datetime import timedelta
from functools import wraps

from django.http import JsonResponse
from django.utils import timezone

from .models import PlatformOperatorRole, PlatformServiceConfig, UserSecurityProfile


PLATFORM_ROLE_MATRIX = {
    PlatformOperatorRole.SUPER_ADMIN: {
        'read': {
            'dashboard', 'tenants', 'onboarding', 'plans', 'billing',
            'operations', 'health', 'emails', 'smtp', 'users', 'support',
            'audit', 'system_settings', 'staff_requests', 'outbound_pause',
        },
        'write': {
            'dashboard', 'tenants', 'onboarding', 'plans', 'billing',
            'operations', 'health', 'health_leases', 'emails', 'smtp',
            'users', 'support', 'audit', 'system_settings', 'staff_requests',
            'outbound_pause', 'inspect', 'operator_roles', 'session_revoke',
        },
    },
    PlatformOperatorRole.SUPPORT: {
        'read': {
            'dashboard', 'tenants', 'onboarding', 'support', 'health',
            'emails', 'users', 'audit', 'staff_requests', 'operations',
        },
        'write': {'onboarding', 'support', 'health_leases', 'inspect', 'staff_requests'},
    },
    PlatformOperatorRole.BILLING: {
        'read': {
            'dashboard', 'tenants', 'plans', 'billing', 'users', 'audit', 'operations',
        },
        'write': {'plans', 'billing'},
    },
    PlatformOperatorRole.READ_ONLY: {
        'read': {
            'dashboard', 'tenants', 'onboarding', 'plans', 'billing',
            'operations', 'health', 'emails', 'users', 'support', 'audit',
            'system_settings', 'staff_requests',
        },
        'write': set(),
    },
}


def get_platform_role(user) -> str:
    """Resolve effective platform operator role without widening client tenant users."""
    if not user or not getattr(user, 'is_authenticated', False) or not getattr(user, 'is_active', False):
        return ''
    profile = UserSecurityProfile.objects.filter(user_id=user.pk).only('platform_role').first()
    if profile and profile.platform_role in PlatformOperatorRole.values:
        return profile.platform_role
    if getattr(user, 'is_superuser', False):
        return PlatformOperatorRole.SUPER_ADMIN
    return ''


def is_platform_operator(user) -> bool:
    return bool(get_platform_role(user))


def can_platform_access(user, area: str, *, write: bool = False) -> tuple[bool, str]:
    role = get_platform_role(user)
    if not role:
        return False, 'Platform operator access required.'
    perms = PLATFORM_ROLE_MATRIX.get(role, {'read': set(), 'write': set()})
    bucket = 'write' if write else 'read'
    if area in perms[bucket]:
        return True, ''
    mode_label = 'modify' if write else 'view'
    return False, f'Role {role} is not permitted to {mode_label} {area.replace("_", " ")}.'


def require_platform_area(area: str, *, write_methods=('POST', 'PUT', 'PATCH', 'DELETE')):
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if not getattr(request, 'user', None) or not request.user.is_authenticated:
                return JsonResponse({'error': 'Authentication required'}, status=401)
            is_write = request.method in write_methods
            allowed, reason = can_platform_access(request.user, area, write=is_write)
            if not allowed:
                return JsonResponse({'error': reason}, status=403)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def check_outbound_whatsapp_pause(tenant=None) -> tuple[bool, str]:
    """
    Return (is_paused, reason) if either global or client-level outbound pause is active.
    """
    try:
        cfg = PlatformServiceConfig.objects.filter(pk=1).only(
            'global_outbound_paused', 'global_outbound_pause_reason'
        ).first()
    except Exception:
        cfg = None
    if cfg and cfg.global_outbound_paused:
        reason = cfg.global_outbound_pause_reason.strip() or 'Paused globally by platform operations'
        return True, f'Global outbound WhatsApp pause active: {reason}'
    if tenant and getattr(tenant, 'outbound_paused', False):
        reason = (getattr(tenant, 'outbound_pause_reason', '') or '').strip() or 'Paused by platform operations'
        return True, f'Client outbound WhatsApp pause active: {reason}'
    return False, ''


def reclaim_all_expired_leases() -> dict:
    """
    Reclaim expired customer processing locks, outbox event leases, webhook leases,
    and stale SENDING WhatsApp deliveries (marked UNKNOWN rather than blindly retried).
    """
    from apps.chatbot.models import Customer
    from apps.crm.automation_engine import reclaim_expired_business_event_leases
    from apps.crm.webhook_service import reclaim_expired_webhook_leases
    from apps.whatsapp.models import WhatsAppDelivery

    now = timezone.now()
    customer_released = Customer.objects.filter(processing_until__lt=now).exclude(processing_token='').update(
        processing_token='',
        processing_until=None,
    )
    event_reclaimed = reclaim_expired_business_event_leases()
    webhook_reclaimed = reclaim_expired_webhook_leases()
    stale_deliveries = WhatsAppDelivery.objects.filter(
        status='SENDING',
        updated_at__lt=now - timedelta(minutes=10),
    ).update(
        status='UNKNOWN',
        last_error='Sending lease expired after 10 minutes; inspect provider state before retrying.',
        updated_at=now,
    )
    return {
        'customer_leases_released': int(customer_released),
        'business_event_leases_reclaimed': int(event_reclaimed),
        'webhook_leases_reclaimed': int(webhook_reclaimed),
        'delivery_sending_expired': int(stale_deliveries),
    }
