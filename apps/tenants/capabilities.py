"""
Authoritative Capability Registry and Policy-Based Authorization Engine.
Provides consistent, centralized authorization across menus, navigation, views, APIs,
and background worker tasks.
"""

import logging
from typing import Dict, Any, Tuple, Optional, List
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.http import HttpResponseForbidden, JsonResponse
from functools import wraps

from .models import Tenant, TenantRole, SubscriptionStatus, UserSecurityProfile
from .modules import MODULE_CATALOG, ModuleStatus

logger = logging.getLogger(__name__)
User = get_user_model()


# =====================================================================
# AUTHORITATIVE CAPABILITY REGISTRY
# =====================================================================

CAPABILITY_REGISTRY: Dict[str, Dict[str, Any]] = {
    # -------------------------------------------------------------
    # Platform Administration Capabilities (Platform-Only)
    # -------------------------------------------------------------
    'platform_dashboard': {
        'key': 'platform_dashboard',
        'name': 'Platform Overview',
        'category': 'Platform',
        'scope': 'platform',
        'route_name': 'platform-dashboard',
        'min_role': None,
        'required_module': None,
        'allowed_actions': ['view', 'manage'],
        'is_implemented': True,
        'description': 'Global system overview, metrics, and health indicators.'
    },
    'platform_tenants': {
        'key': 'platform_tenants',
        'name': 'Tenants & Workspaces',
        'category': 'Platform',
        'scope': 'platform',
        'route_name': 'platform-tenants',
        'min_role': None,
        'required_module': None,
        'allowed_actions': ['view', 'create', 'edit', 'manage', 'inspect'],
        'is_implemented': True,
        'description': 'Tenant directory, provisioning, activation, and inspection.'
    },
    'platform_plans': {
        'key': 'platform_plans',
        'name': 'Subscription Plans & Bundles',
        'category': 'Platform',
        'scope': 'platform',
        'route_name': 'platform-access-matrix',
        'min_role': None,
        'required_module': None,
        'allowed_actions': ['view', 'edit', 'manage', 'bulk_assign'],
        'is_implemented': True,
        'description': 'Configure plan tier entitlements and module bundles.'
    },
    'platform_audit': {
        'key': 'platform_audit',
        'name': 'Platform Security Audit',
        'category': 'Platform',
        'scope': 'platform',
        'route_name': 'platform-audit',
        'min_role': None,
        'required_module': None,
        'allowed_actions': ['view', 'export'],
        'is_implemented': True,
        'description': 'System-wide immutable security audit trail.'
    },
    'platform_support': {
        'key': 'platform_support',
        'name': 'Platform Support Queue',
        'category': 'Platform',
        'scope': 'platform',
        'route_name': 'platform-dashboard',
        'min_role': None,
        'required_module': None,
        'allowed_actions': ['view', 'create', 'edit', 'manage'],
        'is_implemented': True,
        'description': 'Platform-level support inbox and ten-minute SLA escalation management.'
    },

    # -------------------------------------------------------------
    # Tenant Workspace Capabilities (Tenant-Scoped)
    # -------------------------------------------------------------
    'dashboard': {
        'key': 'dashboard',
        'name': 'Workspace Dashboard',
        'category': 'General',
        'scope': 'tenant',
        'route_name': 'dashboard',
        'min_role': TenantRole.STAFF,
        'required_module': None,
        'allowed_actions': ['view'],
        'is_implemented': True,
        'description': 'Primary operational overview for tenant team members.'
    },
    'inbox': {
        'key': 'inbox',
        'name': 'Shared WhatsApp Inbox',
        'category': 'Communication',
        'scope': 'tenant',
        'route_name': 'chat-conversations',
        'min_role': TenantRole.STAFF,
        'required_module': 'shared_inbox',
        'allowed_actions': ['view', 'send_message', 'assign', 'resolve'],
        'is_implemented': True,
        'description': 'Multi-agent WhatsApp conversation management.'
    },
    'contacts': {
        'key': 'contacts',
        'name': 'Customer Contacts',
        'category': 'CRM',
        'scope': 'tenant',
        'route_name': 'crm-contact-list',
        'min_role': TenantRole.STAFF,
        'required_module': 'contacts_companies',
        'allowed_actions': ['view', 'create', 'edit', 'delete', 'export', 'import'],
        'is_implemented': True,
        'description': 'Customer directory linked to WhatsApp phone numbers.'
    },
    'companies': {
        'key': 'companies',
        'name': 'Companies & Accounts',
        'category': 'CRM',
        'scope': 'tenant',
        'route_name': 'crm-company-list',
        'min_role': TenantRole.STAFF,
        'required_module': 'contacts_companies',
        'allowed_actions': ['view', 'create', 'edit', 'delete'],
        'is_implemented': True,
        'description': 'Company accounts and organizational affiliations.'
    },
    'deals': {
        'key': 'deals',
        'name': 'Deals & Sales Pipelines',
        'category': 'CRM',
        'scope': 'tenant',
        'route_name': 'crm-deal-list',
        'min_role': TenantRole.STAFF,
        'required_module': 'deals_pipelines',
        'allowed_actions': ['view', 'create', 'edit', 'change_stage', 'delete'],
        'is_implemented': True,
        'description': 'Visual sales pipelines, deal tracking, and win probability.'
    },
    'tasks': {
        'key': 'tasks',
        'name': 'Tasks & Follow-ups',
        'category': 'CRM',
        'scope': 'tenant',
        'route_name': 'crm-activity-list',
        'min_role': TenantRole.STAFF,
        'required_module': 'tasks_followups',
        'allowed_actions': ['view', 'create', 'edit', 'complete', 'delete'],
        'is_implemented': True,
        'description': 'Actionable reminders, phone calls, and team follow-ups.'
    },
    'bookings': {
        'key': 'bookings',
        'name': 'Consultations & Requests',
        'category': 'CRM',
        'scope': 'tenant',
        'route_name': 'bookings-list',
        'min_role': TenantRole.STAFF,
        'required_module': 'demo_scheduling',
        'allowed_actions': ['view', 'create', 'edit', 'confirm', 'cancel'],
        'is_implemented': True,
        'description': 'Consultation and service request bookings with handover.'
    },
    'services': {
        'key': 'services',
        'name': 'Services & Catalog',
        'category': 'Catalog',
        'scope': 'tenant',
        'route_name': 'service-list',
        'min_role': TenantRole.STAFF,
        'required_module': None,
        'allowed_actions': ['view', 'create', 'edit', 'delete'],
        'is_implemented': True,
        'description': 'Business offerings and service catalog with price structures.'
    },
    'knowledge': {
        'key': 'knowledge',
        'name': 'Knowledge Base & FAQs',
        'category': 'AI & Grounding',
        'scope': 'tenant',
        'route_name': 'knowledge-base',
        'min_role': TenantRole.ADMIN,
        'required_module': 'ai_assistant',
        'allowed_actions': ['view', 'create', 'edit', 'delete', 'sync'],
        'is_implemented': True,
        'description': 'Business profile grounding and FAQ documents for assistant.'
    },
    'team': {
        'key': 'team',
        'name': 'Team Management & Seats',
        'category': 'Settings',
        'scope': 'tenant',
        'route_name': 'tenant-team-list',
        'min_role': TenantRole.ADMIN,
        'required_module': 'team_management',
        'allowed_actions': ['view', 'create', 'edit', 'delete', 'manage'],
        'is_implemented': True,
        'description': 'Manage team seats, invite staff members, and assign roles.'
    },
    'whatsapp_settings': {
        'key': 'whatsapp_settings',
        'name': 'WhatsApp API Settings',
        'category': 'Settings',
        'scope': 'tenant',
        'route_name': 'whatsapp-config',
        'min_role': TenantRole.ADMIN,
        'required_module': None,
        'allowed_actions': ['view', 'edit', 'manage'],
        'is_implemented': True,
        'description': 'Meta Cloud API credentials, webhook tokens, and verify keys.'
    },
    'reports': {
        'key': 'reports',
        'name': 'Workspace Reports',
        'category': 'Analytics',
        'scope': 'tenant',
        'route_name': 'reports-overview',
        'min_role': TenantRole.STAFF,
        'required_module': 'reports',
        'allowed_actions': ['view', 'export'],
        'is_implemented': True,
        'description': 'Operational summary metrics for conversations and deals.'
    },
    'onboarding': {
        'key': 'onboarding',
        'name': 'Onboarding Wizard',
        'category': 'General',
        'scope': 'tenant',
        'route_name': 'onboarding-wizard',
        'min_role': TenantRole.ADMIN,
        'required_module': None,
        'allowed_actions': ['view', 'edit'],
        'is_implemented': True,
        'description': 'Guided setup wizard for profile, catalog, and WhatsApp API.'
    },
    'work_queue': {
        'key': 'work_queue',
        'name': 'Sales Work Queue',
        'category': 'CRM',
        'scope': 'tenant',
        'route_name': 'crm-work-queue',
        'min_role': TenantRole.STAFF,
        'required_module': 'tasks_followups',
        'allowed_actions': ['view'],
        'is_implemented': True,
        'description': 'Actionable sales work queue with 5 operational buckets.'
    },
    'automations': {
        'key': 'automations',
        'name': 'Workflow Automation',
        'category': 'Automation & AI',
        'scope': 'tenant',
        'route_name': 'crm-automations',
        'min_role': TenantRole.ADMIN,
        'required_module': 'automation',
        'allowed_actions': ['view', 'create', 'edit', 'toggle', 'dry_run'],
        'is_implemented': True,
        'description': 'Trigger-condition-action workflow automation engine.'
    },
    'support': {
        'key': 'support',
        'name': 'Customer Support & Onboarding',
        'category': 'Support',
        'scope': 'tenant',
        'route_name': 'crm-support',
        'min_role': TenantRole.STAFF,
        'required_module': 'support',
        'allowed_actions': ['view', 'create', 'edit', 'resolve'],
        'is_implemented': True,
        'description': 'Customer tickets, internal SLA notes, and post-sale onboarding tasks.'
    },
    'growth': {
        'key': 'growth',
        'name': 'Growth & Campaigns',
        'category': 'Growth',
        'scope': 'tenant',
        'route_name': 'crm-growth',
        'min_role': TenantRole.ADMIN,
        'required_module': 'marketing',
        'allowed_actions': ['view', 'create', 'manage_consent'],
        'is_implemented': True,
        'description': 'WhatsApp templates, consent evidence, scheduled broadcasts and delivery reports.'
    },
    'integrations': {
        'key': 'integrations',
        'name': 'Integration Centre',
        'category': 'Integrations',
        'scope': 'tenant',
        'route_name': 'crm-integrations',
        'min_role': TenantRole.ADMIN,
        'required_module': 'integrations',
        'allowed_actions': ['view', 'create', 'manage_webhooks'],
        'is_implemented': True,
        'description': 'External connectors and signed outbound webhooks.'
    },
    'help_support': {
        'key': 'help_support',
        'name': 'Platform Help & Support',
        'category': 'Account',
        'scope': 'tenant',
        'route_name': 'onboarding-wizard',
        'min_role': TenantRole.STAFF,
        'required_module': None,
        'allowed_actions': ['view', 'create', 'edit', 'resolve'],
        'is_implemented': True,
        'description': 'Client-to-platform help desk tickets escalated to Neoriz support.'
    },
}


# =====================================================================
# AUTHORIZATION ENGINE & PRECEDENCE POLICY
# =====================================================================

def can_access_capability(user, tenant: Optional[Tenant], capability_key: str) -> Tuple[bool, str]:
    """
    Evaluates whether a user can access a specific capability within the given tenant context.
    Returns (allowed: bool, explanation: str).
    """
    cap = CAPABILITY_REGISTRY.get(capability_key)
    if not cap:
        return False, f"Unknown capability '{capability_key}'"

    # 1. Unauthenticated users cannot access any protected capability
    if not user or not user.is_authenticated:
        return False, "Authentication required"

    # 2. Scope: Platform-Only Capabilities
    if cap['scope'] == 'platform':
        if user.is_superuser and tenant is None:
            return True, "Granted: Platform Superadmin"
        return False, "Platform administration only"

    # 3. Scope: Tenant-Scoped Capabilities
    # Superuser handling
    if user.is_superuser:
        if tenant:
            # Inspection mode: Superuser inspecting a specific tenant workspace
            return True, "Granted: Platform Superadmin Inspection"
        if not Tenant.objects.exists():
            return True, "Granted: Unseeded single-tenant mode"
        return False, "Platform superadmin must select or inspect a tenant workspace"

    # Regular user requires active tenant context
    if not tenant:
        if not Tenant.objects.exists() and (user.is_staff or user.is_superuser):
            return True, "Granted: Unseeded single-tenant mode"
        return False, "No active workspace selected"

    # Check Tenant active status & Subscription status
    if not tenant.is_active:
        return False, "Workspace is deactivated"

    if hasattr(tenant, 'subscription'):
        sub_status = tenant.subscription.status
        if sub_status == SubscriptionStatus.SUSPENDED:
            return False, "Workspace subscription is suspended by platform administration"
        if sub_status == SubscriptionStatus.PENDING_APPROVAL:
            # Pending workspaces are restricted strictly to setup, verification, help & business onboarding
            allowed_pending_caps = ('onboarding', 'dashboard', 'whatsapp_settings', 'help_support')
            if capability_key not in allowed_pending_caps:
                return False, "Workspace subscription is pending platform administrator activation"

    # Check User Membership within this Tenant
    membership = tenant.memberships.filter(user=user, is_active=True).first()
    if not membership:
        return False, "No active membership in this workspace"

    # Role precedence: Check minimum role required
    min_role = cap.get('min_role')
    if min_role == TenantRole.OWNER and membership.role != TenantRole.OWNER:
        return False, "Requires Workspace Owner privileges"
    if min_role == TenantRole.ADMIN and membership.role not in (TenantRole.OWNER, TenantRole.ADMIN):
        return False, "Requires Workspace Administrator privileges"

    # Check Module Implementation State
    req_mod = cap.get('required_module')
    if req_mod:
        mod_info = MODULE_CATALOG.get(req_mod)
        if mod_info and mod_info['status'] == ModuleStatus.PLANNED:
            return False, f"Feature '{mod_info['name']}' is planned for a future release"

    # Check Platform Overrides for this Tenant (Explicit DENY overrides Plan)
    override = tenant.get_feature_override(capability_key)
    if override == 'DENY':
        return False, "Denied by platform administrator override"
    if override == 'ALLOW':
        return True, "Granted by platform administrator override"

    # Check Plan Entitlement (Inherited from effective plan bundle)
    if req_mod and hasattr(tenant, 'subscription') and tenant.subscription.effective_plan:
        plan = tenant.subscription.effective_plan
        plan_modules = plan.enabled_modules or []
        if req_mod not in plan_modules:
            return False, f"Module '{req_mod}' is not included in current plan ({plan.name})"

    return True, "Granted by plan"


def can_perform_action(user, tenant: Optional[Tenant], capability_key: str, action: str = 'view') -> Tuple[bool, str]:
    """
    Evaluates whether a user can perform an action (e.g. view, create, edit, delete, export, send_message)
    on a capability within the given tenant context.
    """
    allowed, reason = can_access_capability(user, tenant, capability_key)
    if not allowed:
        return False, reason

    cap = CAPABILITY_REGISTRY[capability_key]
    if action not in cap.get('allowed_actions', ['view']):
        return False, f"Action '{action}' is not supported for '{capability_key}'"

    # Platform superadmins can perform all supported actions
    if user.is_superuser:
        return True, "Superuser access"

    # Unverified Email Gate: Unverified users can only view or execute setup/help actions
    security_profile = UserSecurityProfile.get_or_create_for_user(user)
    if not security_profile.email_verified and not security_profile.skip_mailbox_gate:
        if action not in ('view',) and capability_key not in ('onboarding', 'help_support'):
            return False, "Email verification required before performing write or sending actions"

    # Role action constraints
    if not tenant:
        return True, "Granted: Unseeded mode"

    membership = tenant.memberships.filter(user=user, is_active=True).first()
    if not membership:
        return False, "No active membership"

    if membership.role == TenantRole.STAFF:
        sensitive_actions = ('delete', 'manage', 'import', 'export', 'bulk_assign')
        if action in sensitive_actions:
            return False, f"Staff users cannot perform '{action}' actions"

    if membership.role == TenantRole.ADMIN:
        # Admins can perform most actions, but transferring ownership requires OWNER
        if action == 'manage' and capability_key == 'team':
            return True, "Admin access"

    return True, "Permitted"


# =====================================================================
# VIEW DECORATORS
# =====================================================================

def require_capability(capability_key: str, action: str = 'view'):
    """
    Decorator for views enforcing capability access and action permission.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            tenant = getattr(request, 'tenant', None)
            allowed, reason = can_perform_action(request.user, tenant, capability_key, action)
            if not allowed:
                logger.warning(
                    f"Forbidden: User {request.user} denied action '{action}' on '{capability_key}'. Reason: {reason}"
                )
                if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.path.startswith('/api/'):
                    return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)
                raise PermissionDenied(f"Access Denied: {reason}")
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator


def require_platform_admin(view_func):
    """
    Decorator restricting view strictly to platform superadministrators.
    """
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser:
            logger.warning(f"Platform admin view attempted by non-superuser: {request.user}")
            raise PermissionDenied("Platform administration access required.")
        return view_func(request, *args, **kwargs)
    return _wrapped_view


# =====================================================================
# DRF PERMISSION CLASSES
# =====================================================================

try:
    from rest_framework.permissions import BasePermission

    class HasCapabilityPermission(BasePermission):
        """
        DRF permission class evaluating capability and action permissions.
        """
        capability_key = 'dashboard'
        action = 'view'

        def has_permission(self, request, view):
            if not request.user or not request.user.is_authenticated:
                return False
            tenant = getattr(request, 'tenant', None)
            allowed, _ = can_perform_action(request.user, tenant, self.capability_key, self.action)
            return allowed

    def capability_permission(cap_key: str, action: str = 'view'):
        """
        Factory producing a DRF BasePermission subclass configured for a capability and action.
        """
        return type(
            f'HasCapability_{cap_key}_{action}',
            (HasCapabilityPermission,),
            {'capability_key': cap_key, 'action': action}
        )

except ImportError:
    HasCapabilityPermission = None
    capability_permission = None
