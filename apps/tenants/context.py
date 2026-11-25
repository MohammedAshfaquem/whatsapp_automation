import threading
from typing import Optional
from django.contrib.auth.models import User
from .models import Tenant, TenantMembership, TenantRole

_thread_locals = threading.local()


def set_current_tenant(tenant: Optional[Tenant]):
    """Set the current tenant in thread-local storage."""
    _thread_locals.tenant = tenant


def get_current_tenant() -> Optional[Tenant]:
    """Retrieve the current tenant from thread-local storage."""
    return getattr(_thread_locals, 'tenant', None)


def clear_current_tenant():
    """Clear the tenant from thread-local storage."""
    if hasattr(_thread_locals, 'tenant'):
        del _thread_locals.tenant


def get_user_membership(user: User, tenant: Optional[Tenant]) -> Optional[TenantMembership]:
    """Get active membership of user in tenant."""
    if not user.is_authenticated or not tenant:
        return None
    return TenantMembership.objects.filter(
        user=user,
        tenant=tenant,
        is_active=True
    ).first()


def user_can_manage_tenant(user: User, tenant: Optional[Tenant]) -> bool:
    """Check if user is a platform superadmin, tenant owner, or tenant admin."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not tenant:
        return False
    membership = get_user_membership(user, tenant)
    return bool(membership and membership.is_owner_or_admin)


def user_can_access_tenant(user: User, tenant: Optional[Tenant]) -> bool:
    """Check if user has any active role in the tenant or is superuser."""
    if not user.is_authenticated:
        return False
    if user.is_superuser:
        return True
    if not tenant:
        return False
    return TenantMembership.objects.filter(
        user=user,
        tenant=tenant,
        is_active=True
    ).exists()
