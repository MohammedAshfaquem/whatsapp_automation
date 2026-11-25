"""
REST API endpoints for Release 1:
- Super Admin Onboarding directory, invite, approval, rejection, verification/activation resend, and email correction
- Direct Client Team Staff Administration (create, edit, deactivate, reset password without old password, audit view)
"""
import json
import logging
from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .capabilities import can_perform_action
from .email_service import email_status_label, queue_activation
from .models import (
    AccountActivationToken,
    AuditLogAction,
    ClientOnboarding,
    EmailVerificationToken,
    OnboardingApprovalStatus,
    OnboardingRegistrationStatus,
    PlanTier,
    TenantAuditLog,
    TenantMembership,
    TenantRole,
    TransactionalEmail,
    UserSecurityProfile,
    VerificationPurpose,
)
from .onboarding_service import (
    OnboardingError,
    VerificationThrottleError,
    approve_client_onboarding,
    can_manage_member,
    change_onboarding_email,
    create_superadmin_invite,
    create_tenant_staff_member,
    is_shared_identity,
    issue_onboarding_verification,
    reject_client_onboarding,
    reset_tenant_staff_password,
    update_tenant_staff_member,
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
    if request.body:
        try:
            return json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            pass
    return request.POST.dict()


def _serialize_onboarding(obj: ClientOnboarding) -> dict:
    latest_v_email = (
        TransactionalEmail.objects.filter(onboarding=obj, purpose='VERIFICATION')
        .order_by('-created_at')
        .first()
    )
    latest_a_email = (
        TransactionalEmail.objects.filter(onboarding=obj, purpose='ACTIVATION')
        .order_by('-created_at')
        .first()
    )
    latest_v_tok = (
        EmailVerificationToken.objects.filter(
            onboarding=obj,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            is_used=False,
            invalidation_reason='',
        )
        .order_by('-created_at')
        .first()
    )
    latest_a_tok = (
        AccountActivationToken.objects.filter(
            user=obj.owner_user,
            purpose='ACCOUNT_ACTIVATION',
            is_used=False,
        )
        .order_by('-created_at')
        .first()
        if obj.owner_user_id else None
    )

    if obj.approval_status == OnboardingApprovalStatus.REJECTED:
        next_action = 'Rejected'
    elif not obj.email_verified:
        next_action = 'Awaiting owner email verification'
    elif obj.approval_status == OnboardingApprovalStatus.PENDING:
        next_action = 'Ready for platform approval & plan assignment'
    elif not obj.password_set:
        next_action = 'Awaiting owner password setup'
    elif obj.tenant_id and obj.tenant.requires_meta_setup:
        next_action = 'Owner completing Meta WhatsApp setup'
    else:
        next_action = 'Active & Ready'

    latest_email = latest_a_email or latest_v_email
    if not obj.email_verified and latest_v_email:
        latest_email = latest_v_email

    return {
        'id': str(obj.pk),
        'source': obj.source,
        'source_display': obj.get_source_display(),
        'business_name': obj.business_name,
        'owner_full_name': obj.owner_full_name,
        'owner_email': obj.owner_email,
        'desired_username': obj.desired_username,
        'whatsapp_number': obj.whatsapp_number,
        'requested_plan': (
            {'id': obj.requested_plan.id, 'code': obj.requested_plan.code, 'name': obj.requested_plan.name}
            if obj.requested_plan_id else None
        ),
        'assigned_plan': (
            {'id': obj.assigned_plan.id, 'code': obj.assigned_plan.code, 'name': obj.assigned_plan.name}
            if obj.assigned_plan_id else None
        ),
        'registration_status': obj.registration_status,
        'registration_status_display': obj.get_registration_status_display(),
        'email_verified': obj.email_verified,
        'email_verified_at': obj.email_verified_at.isoformat() if obj.email_verified_at else None,
        'approval_status': obj.approval_status,
        'approval_status_display': obj.get_approval_status_display(),
        'approved_by': obj.approved_by.username if obj.approved_by_id else None,
        'approved_at': obj.approved_at.isoformat() if obj.approved_at else None,
        'decision_reason': obj.decision_reason,
        'password_set': obj.password_set,
        'password_set_at': obj.password_set_at.isoformat() if obj.password_set_at else None,
        'terms_accepted': obj.terms_accepted,
        'marketing_consent': obj.marketing_consent,
        'tenant_id': obj.tenant_id,
        'tenant_name': obj.tenant.name if obj.tenant_id else None,
        'verification_expires_at': latest_v_tok.expires_at.isoformat() if latest_v_tok else None,
        'activation_expires_at': latest_a_tok.expires_at.isoformat() if latest_a_tok else None,
        'email_delivery': (
            {
                'purpose': latest_email.purpose,
                'status': latest_email.status,
                'status_label': email_status_label(latest_email.status),
                'attempts': latest_email.attempts,
                'last_error': latest_email.last_error,
                'updated_at': latest_email.updated_at.isoformat(),
            }
            if latest_email else None
        ),
        'next_action': next_action,
        'created_at': obj.created_at.isoformat(),
        'updated_at': obj.updated_at.isoformat(),
    }


@_api_login_required
@require_GET
def platform_onboarding_list_api(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)

    qs = ClientOnboarding.objects.select_related(
        'requested_plan', 'assigned_plan', 'approved_by', 'tenant', 'owner_user'
    ).order_by('-created_at')

    status_filter = (request.GET.get('status') or '').strip().upper()
    if status_filter == 'PENDING_APPROVAL':
        qs = qs.filter(approval_status=OnboardingApprovalStatus.PENDING)
    elif status_filter == 'AWAITING_EMAIL':
        qs = qs.filter(email_verified=False).exclude(approval_status=OnboardingApprovalStatus.REJECTED)
    elif status_filter == 'AWAITING_PASSWORD':
        qs = qs.filter(approval_status=OnboardingApprovalStatus.APPROVED, email_verified=True, password_set=False)
    elif status_filter in ('APPROVED', 'REJECTED'):
        qs = qs.filter(approval_status=status_filter)

    q = (request.GET.get('q') or '').strip()
    if q:
        qs = qs.filter(
            Q(business_name__icontains=q)
            | Q(owner_email__icontains=q)
            | Q(owner_full_name__icontains=q)
            | Q(desired_username__icontains=q)
        )

    items = [_serialize_onboarding(o) for o in qs[:100]]
    all_rows = ClientOnboarding.objects.all()
    counts = {
        'total': all_rows.count(),
        'pending_approval': all_rows.filter(approval_status=OnboardingApprovalStatus.PENDING).count(),
        'awaiting_email': all_rows.filter(email_verified=False).exclude(approval_status=OnboardingApprovalStatus.REJECTED).count(),
        'awaiting_password': all_rows.filter(approval_status=OnboardingApprovalStatus.APPROVED, email_verified=True, password_set=False).count(),
        'active': all_rows.filter(registration_status=OnboardingRegistrationStatus.ACTIVE).count(),
        'rejected': all_rows.filter(approval_status=OnboardingApprovalStatus.REJECTED).count(),
    }
    plans = [
        {'id': p.id, 'code': p.code, 'name': p.name, 'max_staff': p.max_staff}
        for p in PlanTier.objects.all().order_by('ordering', 'id')
    ]
    return JsonResponse({'onboardings': items, 'counts': counts, 'plans': plans})


@_api_login_required
@require_POST
def platform_onboarding_invite_api(request):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    data = _parse_body(request)
    plan_code = (data.get('plan_code') or data.get('plan') or '').strip()
    plan_id = data.get('plan_id')
    plan = None
    if plan_id:
        plan = PlanTier.objects.filter(pk=plan_id).first()
    elif plan_code:
        plan = PlanTier.objects.filter(code__iexact=plan_code).first()

    try:
        res = create_superadmin_invite(
            actor=request.user,
            business_name=data.get('business_name') or data.get('name') or '',
            owner_full_name=data.get('owner_full_name') or data.get('admin_name') or '',
            owner_email=data.get('owner_email') or data.get('admin_email') or '',
            desired_username=data.get('desired_username') or data.get('admin_username') or '',
            assigned_plan=plan,
            whatsapp_number=data.get('whatsapp_number') or '',
            notes=data.get('notes') or '',
            request=request,
        )
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code, **exc.extra}, status=exc.status)

    return JsonResponse({
        'status': 'invited',
        'onboarding': _serialize_onboarding(res['onboarding']),
        'message': f"Client workspace '{res['tenant'].name}' invited. Verification email queued before password setup.",
    }, status=201)


@_api_login_required
@require_POST
def platform_onboarding_approve_api(request, onboarding_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    onboarding = get_object_or_404(ClientOnboarding, pk=onboarding_id)
    data = _parse_body(request)
    plan_code = (data.get('plan_code') or data.get('plan') or '').strip()
    plan_id = data.get('plan_id')
    plan = None
    if plan_id:
        plan = PlanTier.objects.filter(pk=plan_id).first()
    elif plan_code:
        plan = PlanTier.objects.filter(code__iexact=plan_code).first()
    if plan is None:
        plan = onboarding.requested_plan

    try:
        res = approve_client_onboarding(
            onboarding=onboarding,
            actor=request.user,
            assigned_plan=plan,
            whatsapp_number=data.get('whatsapp_number') if 'whatsapp_number' in data else None,
            decision_reason=data.get('decision_reason') or data.get('reason') or '',
            request=request,
        )
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code, **exc.extra}, status=exc.status)

    return JsonResponse({
        'status': 'approved',
        'onboarding': _serialize_onboarding(res['onboarding']),
        'message': (
            "Approved! Owner email is verified and password setup instructions were sent."
            if res['onboarding'].email_verified
            else "Approved! Password setup stays gated until the owner verifies their email address."
        ),
    })


@_api_login_required
@require_POST
def platform_onboarding_reject_api(request, onboarding_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    onboarding = get_object_or_404(ClientOnboarding, pk=onboarding_id)
    data = _parse_body(request)
    try:
        updated = reject_client_onboarding(
            onboarding=onboarding,
            actor=request.user,
            reason=data.get('decision_reason') or data.get('reason') or '',
            request=request,
        )
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    return JsonResponse({'status': 'rejected', 'onboarding': _serialize_onboarding(updated)})


@_api_login_required
@require_POST
def platform_onboarding_resend_verification_api(request, onboarding_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    onboarding = get_object_or_404(ClientOnboarding, pk=onboarding_id)
    try:
        issue_onboarding_verification(onboarding=onboarding, request=request, enforce_cooldown=True)
    except VerificationThrottleError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code, 'retry_after': exc.retry_after}, status=429)
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    onboarding.refresh_from_db()
    return JsonResponse({
        'status': 'sent',
        'onboarding': _serialize_onboarding(onboarding),
        'message': f"Verification email queued for {onboarding.owner_email}.",
    })


@_api_login_required
@require_POST
def platform_onboarding_resend_activation_api(request, onboarding_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    onboarding = get_object_or_404(ClientOnboarding, pk=onboarding_id)
    if onboarding.approval_status != OnboardingApprovalStatus.APPROVED:
        return JsonResponse({'error': 'Onboarding must be approved before issuing password setup.'}, status=409)
    if not onboarding.email_verified:
        return JsonResponse({'error': 'Owner email verification is required before sending password setup.'}, status=409)
    if not onboarding.owner_user_id:
        return JsonResponse({'error': 'Owner user is not provisioned yet.'}, status=409)
    if onboarding.owner_user.has_usable_password():
        return JsonResponse({'error': 'Owner already has a password configured.'}, status=409)

    with transaction.atomic():
        owner = User.objects.select_for_update().get(pk=onboarding.owner_user_id)
        act_tok = AccountActivationToken.create_for_user(owner, valid_hours=48)
        queue_activation(request, act_tok, tenant=onboarding.tenant, onboarding=onboarding)
        TenantAuditLog.objects.create(
            tenant=onboarding.tenant,
            actor=request.user,
            action=AuditLogAction.CREDENTIALS_UPDATED,
            summary=f"Re-sent password setup email to verified owner {owner.username}",
            details={'onboarding_id': str(onboarding.pk), 'owner_user_id': owner.pk},
        )
    return JsonResponse({
        'status': 'sent',
        'onboarding': _serialize_onboarding(onboarding),
        'message': f"Single-use password setup email queued for {onboarding.owner_email}.",
    })


@_api_login_required
@require_POST
def platform_onboarding_change_email_api(request, onboarding_id):
    if not request.user.is_superuser:
        return JsonResponse({'error': 'Platform Superadmin access required.'}, status=403)
    onboarding = get_object_or_404(ClientOnboarding, pk=onboarding_id)
    data = _parse_body(request)
    new_email = data.get('new_email') or data.get('owner_email') or ''
    try:
        updated, _, _ = change_onboarding_email(
            onboarding=onboarding,
            new_email=new_email,
            request=request,
            actor=request.user,
        )
    except VerificationThrottleError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code, 'retry_after': exc.retry_after}, status=429)
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)
    return JsonResponse({
        'status': 'updated',
        'onboarding': _serialize_onboarding(updated),
        'message': f"Updated email to {updated.owner_email} and sent fresh verification link.",
    })


# ---------------------------------------------------------------------------
# Client Team Direct Staff Administration APIs
# ---------------------------------------------------------------------------

def _serialize_member(m: TenantMembership, *, actor_membership: TenantMembership | None, actor_user) -> dict:
    sec = UserSecurityProfile.get_or_create_for_user(m.user)
    return {
        'id': m.id,
        'user_id': m.user.id,
        'username': m.user.username,
        'full_name': m.user.get_full_name() or m.user.username,
        'first_name': m.user.first_name,
        'last_name': m.user.last_name,
        'email': m.user.email,
        'internal_identifier': sec.internal_identifier or '',
        'is_synthetic_identifier': sec.is_synthetic_identifier,
        'recovery_email': sec.recovery_email,
        'recovery_email_verified': sec.recovery_email_verified,
        'email_verified': sec.email_verified,
        'skip_mailbox_gate': sec.skip_mailbox_gate,
        'has_usable_password': m.user.has_usable_password(),
        'role': m.role,
        'role_display': m.get_role_display(),
        'is_active': m.is_active,
        'is_shared_account': is_shared_identity(m.user, m.tenant),
        'can_manage': can_manage_member(actor_membership, m, actor_user=actor_user),
        'joined_at': m.created_at.isoformat(),
    }


@_api_login_required
@require_POST
def team_member_create_api(request):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'create')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    actor_membership = getattr(request, 'membership', None) or TenantMembership.objects.filter(
        tenant=tenant, user=request.user, is_active=True
    ).first()
    data = _parse_body(request)
    try:
        membership = create_tenant_staff_member(
            tenant=tenant,
            actor=request.user,
            actor_membership=actor_membership,
            username=data.get('username', ''),
            full_name=data.get('full_name', ''),
            role=(data.get('role') or TenantRole.STAFF).strip().upper(),
            password=data.get('password', ''),
            contact_email=data.get('contact_email') or data.get('email') or '',
            synthetic_identifier=data.get('synthetic_identifier') or '',
            request=request,
        )
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)

    return JsonResponse({
        'status': 'created',
        'member': _serialize_member(membership, actor_membership=actor_membership, actor_user=request.user),
        'message': f"Staff account @{membership.user.username} created and ready for sign-in.",
    }, status=201)


@_api_login_required
@require_http_methods(['PATCH', 'POST'])
def team_member_update_api(request, membership_id):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'edit')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    actor_membership = getattr(request, 'membership', None) or TenantMembership.objects.filter(
        tenant=tenant, user=request.user, is_active=True
    ).first()
    data = _parse_body(request)
    try:
        updated = update_tenant_staff_member(
            tenant=tenant,
            actor=request.user,
            actor_membership=actor_membership,
            membership_id=membership_id,
            username=data.get('username') if 'username' in data else None,
            full_name=data.get('full_name') if 'full_name' in data else None,
            role=data.get('role').strip().upper() if data.get('role') else None,
            is_active=data.get('is_active') if 'is_active' in data else None,
            contact_email=data.get('contact_email') if 'contact_email' in data else (data.get('email') if 'email' in data else None),
            synthetic_identifier=data.get('synthetic_identifier') if 'synthetic_identifier' in data else None,
            request=request,
        )
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)

    return JsonResponse({
        'status': 'updated',
        'member': _serialize_member(updated, actor_membership=actor_membership, actor_user=request.user),
        'message': f"Updated @{updated.user.username}.",
    })


@_api_login_required
@require_POST
def team_member_reset_password_api(request, membership_id):
    tenant = getattr(request, 'tenant', None)
    if not tenant:
        return JsonResponse({'error': 'Active workspace required.'}, status=400)
    allowed, reason = can_perform_action(request.user, tenant, 'team', 'edit')
    if not allowed:
        return JsonResponse({'error': 'Permission Denied', 'reason': reason}, status=403)

    actor_membership = getattr(request, 'membership', None) or TenantMembership.objects.filter(
        tenant=tenant, user=request.user, is_active=True
    ).first()
    data = _parse_body(request)
    new_pw = data.get('new_password', '')
    confirm_pw = data.get('confirm_password')
    if confirm_pw is not None and new_pw != confirm_pw:
        return JsonResponse({'error': 'Passwords do not match.', 'code': 'password_mismatch'}, status=400)

    try:
        res = reset_tenant_staff_password(
            tenant=tenant,
            actor=request.user,
            actor_membership=actor_membership,
            membership_id=membership_id,
            new_password=new_pw,
            request=request,
        )
    except OnboardingError as exc:
        return JsonResponse({'error': exc.message, 'code': exc.code}, status=exc.status)

    return JsonResponse({
        'status': 'password_reset',
        'username': res['username'],
        'sessions_revoked': res['sessions_revoked'],
        'message': f"Password updated for @{res['username']} and {res['sessions_revoked']} active session(s) revoked.",
    })
