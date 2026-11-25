"""
Authoritative Navigation Registry and Template Context Processor.
Ensures that navigation menus accurately mirror the capability registry and authorization rules.
Platform menus NEVER appear for tenant users.
"""

from typing import Dict, Any, List
from django.urls import reverse, NoReverseMatch
from .capabilities import CAPABILITY_REGISTRY, can_access_capability, can_perform_action
from .models import UserSecurityProfile


def get_navigation_for_request(request) -> Dict[str, Any]:
    user = getattr(request, 'user', None)
    if not user or not user.is_authenticated:
        return {
            'platform_menus': [],
            'tenant_menus': [],
            'is_platform_admin': False,
            'is_inspecting': False,
            'current_tenant': None,
            'user_tenants': [],
            'membership': None,
            'email_verified': False,
        }

    tenant = getattr(request, 'tenant', None)
    membership = getattr(request, 'membership', None)
    user_tenants = getattr(request, 'user_tenants', [])
    is_inspecting = getattr(request, 'is_inspecting', False)
    is_platform_admin = user.is_superuser and not is_inspecting

    sec_profile = UserSecurityProfile.get_or_create_for_user(user)

    # 1. Platform Menus (Only for platform administrators operating in platform context)
    platform_menus = []
    if is_platform_admin:
        platform_cap_keys = ['platform_dashboard', 'platform_tenants', 'platform_plans', 'platform_audit']
        for k in platform_cap_keys:
            cap = CAPABILITY_REGISTRY[k]
            try:
                url = reverse(cap['route_name'])
            except NoReverseMatch:
                url = '#'
            platform_menus.append({
                'key': k,
                'name': cap['name'],
                'url': url,
                'icon': k,
                'is_active': request.resolver_match and request.resolver_match.url_name == cap['route_name'],
            })

    # 2. Tenant Menus (Only when a workspace is active or being inspected)
    tenant_menus = []
    if tenant:
        tenant_cap_keys = [
            'dashboard', 'inbox', 'contacts', 'companies', 'deals',
            'tasks', 'bookings', 'services', 'knowledge', 'reports',
            'team', 'whatsapp_settings', 'onboarding'
        ]
        for k in tenant_cap_keys:
            allowed, _ = can_access_capability(user, tenant, k)
            if allowed:
                cap = CAPABILITY_REGISTRY[k]
                try:
                    url = reverse(cap['route_name'])
                except NoReverseMatch:
                    url = '#'
                tenant_menus.append({
                    'key': k,
                    'name': cap['name'],
                    'category': cap['category'],
                    'url': url,
                    'is_active': request.resolver_match and request.resolver_match.url_name == cap['route_name'],
                })

    return {
        'platform_menus': platform_menus,
        'tenant_menus': tenant_menus,
        'is_platform_admin': is_platform_admin,
        'is_inspecting': is_inspecting,
        'current_tenant': tenant,
        'user_tenants': user_tenants,
        'membership': membership,
        'email_verified': bool(sec_profile.email_verified or sec_profile.skip_mailbox_gate),
    }


def navigation_context(request):
    """Context processor making navigation metadata available to all templates."""
    return {
        'nav': get_navigation_for_request(request)
    }
