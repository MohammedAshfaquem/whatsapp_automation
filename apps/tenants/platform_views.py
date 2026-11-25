"""
Platform Administration Views.
Strictly accessible only by authenticated Platform Superadministrators.
Provides global overview, tenant directory, subscription approvals, access bundle matrix,
tenant capability overrides, and security audit logs.
"""

import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction

from .models import (
    Tenant, TenantSubscription, SubscriptionStatus, PlanTier,
    TenantFeatureOverride, OverrideChoice, TenantAuditLog, AuditLogAction
)
from .capabilities import (
    CAPABILITY_REGISTRY, can_access_capability, require_platform_admin
)
from .modules import MODULE_CATALOG

logger = logging.getLogger(__name__)


@require_platform_admin
def platform_dashboard_view(request):
    """
    Platform Administration Overview.
    Displays platform-wide operational KPIs and pending tenant approvals.
    """
    total_tenants = Tenant.objects.count()
    active_tenants = Tenant.objects.filter(is_active=True).count()
    pending_approvals = TenantSubscription.objects.filter(
        status=SubscriptionStatus.PENDING_APPROVAL
    ).select_related('tenant', 'requested_plan')
    suspended_tenants = TenantSubscription.objects.filter(
        status=SubscriptionStatus.SUSPENDED
    ).count()

    recent_audits = TenantAuditLog.objects.select_related('tenant', 'actor').order_by('-created_at')[:10]

    return render(request, 'platform/dashboard.html', {
        'total_tenants': total_tenants,
        'active_tenants': active_tenants,
        'pending_approvals_count': pending_approvals.count(),
        'pending_approvals': pending_approvals[:5],
        'suspended_tenants': suspended_tenants,
        'recent_audits': recent_audits,
    })


@require_platform_admin
def platform_tenants_view(request):
    """
    Tenant Directory & Workspace Management.
    Supports search, filtering, subscription activation, and entering inspection mode.
    """
    search_query = request.GET.get('q', '').strip()
    status_filter = request.GET.get('status', '').strip()

    tenants_qs = Tenant.objects.select_related('subscription', 'subscription__effective_plan').order_by('name')

    if search_query:
        tenants_qs = tenants_qs.filter(name__icontains=search_query)

    if status_filter == 'PENDING':
        tenants_qs = tenants_qs.filter(subscription__status=SubscriptionStatus.PENDING_APPROVAL)
    elif status_filter == 'ACTIVE':
        tenants_qs = tenants_qs.filter(subscription__status=SubscriptionStatus.ACTIVE)
    elif status_filter == 'SUSPENDED':
        tenants_qs = tenants_qs.filter(subscription__status=SubscriptionStatus.SUSPENDED)

    # Handle quick administrative actions
    if request.method == 'POST':
        action = request.POST.get('action')
        target_tenant_id = request.POST.get('tenant_id')
        tenant = get_object_or_404(Tenant, id=target_tenant_id)

        if action == 'approve_subscription':
            if hasattr(tenant, 'subscription'):
                tenant.subscription.approve(approver_user=request.user)
                TenantAuditLog.objects.create(
                    tenant=tenant,
                    actor=request.user,
                    action=AuditLogAction.SUBSCRIPTION_UPDATED,
                    summary=f"Subscription approved by {request.user.username}",
                    details={'new_status': SubscriptionStatus.ACTIVE},
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, f"Activated subscription for '{tenant.name}'.")

        elif action == 'suspend_tenant':
            if hasattr(tenant, 'subscription'):
                tenant.subscription.status = SubscriptionStatus.SUSPENDED
                tenant.subscription.save(update_fields=['status'])
                TenantAuditLog.objects.create(
                    tenant=tenant,
                    actor=request.user,
                    action=AuditLogAction.TENANT_STATUS_CHANGED,
                    summary=f"Workspace suspended by {request.user.username}",
                    details={'new_status': SubscriptionStatus.SUSPENDED},
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.warning(request, f"Workspace '{tenant.name}' has been suspended.")

        elif action == 'reactivate_tenant':
            if hasattr(tenant, 'subscription'):
                tenant.subscription.status = SubscriptionStatus.ACTIVE
                tenant.subscription.save(update_fields=['status'])
                tenant.is_active = True
                tenant.save(update_fields=['is_active'])
                TenantAuditLog.objects.create(
                    tenant=tenant,
                    actor=request.user,
                    action=AuditLogAction.TENANT_STATUS_CHANGED,
                    summary=f"Workspace reactivated by {request.user.username}",
                    details={'new_status': SubscriptionStatus.ACTIVE},
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                messages.success(request, f"Workspace '{tenant.name}' reactivated.")

        return redirect('platform-tenants')

    return render(request, 'platform/tenants.html', {
        'tenants': tenants_qs,
        'search_query': search_query,
        'status_filter': status_filter,
    })


@require_platform_admin
def platform_inspect_tenant_view(request, tenant_id):
    """
    Enters Explicit Tenant Inspection Mode for a Platform Superadministrator.
    Audits the sensitive inspection action and sets the session context.
    """
    tenant = get_object_or_404(Tenant, id=tenant_id)

    TenantAuditLog.objects.create(
        tenant=tenant,
        actor=request.user,
        action=AuditLogAction.TENANT_INSPECTED,
        summary=f"Platform superadmin {request.user.username} entered inspection mode for '{tenant.name}'",
        details={'tenant_id': str(tenant.id), 'tenant_slug': tenant.slug},
        ip_address=request.META.get('REMOTE_ADDR')
    )

    request.session['inspecting_tenant_id'] = tenant.id
    request.session['active_tenant_id'] = tenant.id
    messages.info(request, f"Inspection Mode: Viewing '{tenant.name}'. You are operating with superadmin privileges.")
    return redirect('dashboard')


@require_platform_admin
def platform_exit_inspection_view(request):
    """
    Exits Tenant Inspection Mode and returns to Platform Administration.
    """
    inspecting_id = request.session.pop('inspecting_tenant_id', None)
    request.session.pop('active_tenant_id', None)

    if inspecting_id:
        tenant = Tenant.objects.filter(id=inspecting_id).first()
        if tenant:
            TenantAuditLog.objects.create(
                tenant=tenant,
                actor=request.user,
                action=AuditLogAction.TENANT_INSPECTED,
                summary=f"Platform superadmin {request.user.username} exited inspection mode for '{tenant.name}'",
                ip_address=request.META.get('REMOTE_ADDR')
            )

    messages.success(request, "Exited tenant inspection mode. Returned to platform administration.")
    return redirect('platform-tenants')


@require_platform_admin
def platform_access_matrix_view(request):
    """
    Subscription Plans & Access Matrix.
    Displays Capabilities (Rows) vs Plans (Columns).
    Supports bundle editing, copying configurations between plans, and bulk plan assignment.
    """
    plans = PlanTier.objects.order_by('ordering', 'name')
    tenant_capabilities = [
        c for c in CAPABILITY_REGISTRY.values() if c['scope'] == 'tenant'
    ]

    # Handle Plan Updates or Bulk Assignment
    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_plan_bundle':
            plan_code = request.POST.get('plan_code')
            plan = get_object_or_404(PlanTier, code=plan_code)
            enabled_modules = request.POST.getlist('modules')

            # Validate that modules exist in catalog and are not PLANNED
            valid_modules = []
            for m in enabled_modules:
                if m in MODULE_CATALOG:
                    valid_modules.append(m)

            old_modules = plan.enabled_modules
            plan.enabled_modules = valid_modules
            plan.save(update_fields=['enabled_modules', 'updated_at'])

            TenantAuditLog.objects.create(
                actor=request.user,
                action=AuditLogAction.FEATURE_OVERRIDE_CHANGED,
                summary=f"Updated module bundle for plan '{plan.name}'",
                details={'plan': plan.code, 'before': old_modules, 'after': valid_modules},
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Updated capability bundle for {plan.name} plan.")
            return redirect('platform-access-matrix')

        elif action == 'copy_plan_bundle':
            source_code = request.POST.get('source_plan')
            target_code = request.POST.get('target_plan')
            source_plan = get_object_or_404(PlanTier, code=source_code)
            target_plan = get_object_or_404(PlanTier, code=target_code)

            target_plan.enabled_modules = list(source_plan.enabled_modules)
            target_plan.save(update_fields=['enabled_modules', 'updated_at'])

            messages.success(request, f"Copied bundle from {source_plan.name} to {target_plan.name}.")
            return redirect('platform-access-matrix')

        elif action == 'bulk_assign_plan':
            target_plan_code = request.POST.get('target_plan_code')
            selected_tenant_ids = request.POST.getlist('tenant_ids')
            confirm = request.POST.get('confirm') == 'yes'

            target_plan = get_object_or_404(PlanTier, code=target_plan_code)
            tenants = Tenant.objects.filter(id__in=selected_tenant_ids)

            if not confirm:
                # Show impact preview before concrete bulk execution
                return render(request, 'platform/bulk_assign_preview.html', {
                    'target_plan': target_plan,
                    'tenants': tenants,
                    'selected_ids': selected_tenant_ids,
                })

            # Execute Bulk Assignment inside atomic transaction
            with transaction.atomic():
                updated_count = 0
                for t in tenants:
                    if hasattr(t, 'subscription'):
                        sub = t.subscription
                        sub.effective_plan = target_plan
                        sub.save(update_fields=['effective_plan', 'updated_at'])
                    t.max_staff = target_plan.max_staff
                    t.max_services = target_plan.max_services
                    t.save(update_fields=['max_staff', 'max_services', 'updated_at'])
                    updated_count += 1

                TenantAuditLog.objects.create(
                    actor=request.user,
                    action=AuditLogAction.BULK_PLAN_ASSIGNED,
                    summary=f"Bulk assigned plan '{target_plan.name}' to {updated_count} tenants",
                    details={'plan': target_plan.code, 'tenant_ids': selected_tenant_ids},
                    ip_address=request.META.get('REMOTE_ADDR')
                )

            messages.success(request, f"Successfully migrated {updated_count} workspaces to {target_plan.name} plan.")
            return redirect('platform-access-matrix')

    # Build Matrix Data: Capability -> Plan -> is_enabled
    matrix_rows = []
    for cap in tenant_capabilities:
        req_mod = cap.get('required_module')
        row = {
            'capability': cap,
            'required_module': req_mod,
            'plan_access': {}
        }
        for p in plans:
            if not req_mod:
                row['plan_access'][p.code] = True
            else:
                row['plan_access'][p.code] = req_mod in (p.enabled_modules or [])
        matrix_rows.append(row)

    all_tenants = Tenant.objects.order_by('name')

    return render(request, 'platform/access_matrix.html', {
        'plans': plans,
        'capabilities': tenant_capabilities,
        'matrix_rows': matrix_rows,
        'all_tenants': all_tenants,
    })


@require_platform_admin
def platform_tenant_overrides_view(request, tenant_id):
    """
    Tenant-Specific Capability Overrides.
    Configures Inherit / Explicit Allow / Explicit Deny per capability for a tenant.
    Displays live effective status and explanation.
    """
    tenant = get_object_or_404(Tenant, id=tenant_id)
    tenant_capabilities = [
        c for c in CAPABILITY_REGISTRY.values() if c['scope'] == 'tenant'
    ]

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'save_overrides':
            for cap in tenant_capabilities:
                key = cap['key']
                val = request.POST.get(f'override_{key}', 'INHERIT')
                reason = request.POST.get(f'reason_{key}', '').strip()

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
                    # INHERIT removes explicit override record
                    TenantFeatureOverride.objects.filter(tenant=tenant, feature_key=key).delete()

            TenantAuditLog.objects.create(
                tenant=tenant,
                actor=request.user,
                action=AuditLogAction.FEATURE_OVERRIDE_CHANGED,
                summary=f"Updated capability overrides for '{tenant.name}'",
                ip_address=request.META.get('REMOTE_ADDR')
            )
            messages.success(request, f"Updated capability overrides for '{tenant.name}'.")
            return redirect('platform-tenant-overrides', tenant_id=tenant.id)

    # Compute effective status for each capability
    override_rows = []
    for cap in tenant_capabilities:
        key = cap['key']
        override_val = tenant.get_feature_override(key)
        allowed, reason = can_access_capability(request.user, tenant, key)
        override_rows.append({
            'capability': cap,
            'override': override_val,
            'effective_allowed': allowed,
            'reason': reason,
        })

    return render(request, 'platform/tenant_overrides.html', {
        'tenant': tenant,
        'override_rows': override_rows,
        'OverrideChoice': OverrideChoice,
    })


@require_platform_admin
def platform_audit_view(request):
    """
    Platform-Wide Security Audit Trail.
    """
    logs = TenantAuditLog.objects.select_related('tenant', 'actor').order_by('-created_at')[:100]
    return render(request, 'platform/audit.html', {
        'logs': logs,
    })
