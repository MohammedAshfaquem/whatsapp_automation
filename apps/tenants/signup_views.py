import logging
from django.shortcuts import render, redirect
from django.contrib.auth import get_user_model, login as auth_login
from django.contrib import messages
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify
from django.http import HttpResponseForbidden
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .models import (
    Tenant, PlanTier, EmailVerificationToken, LegalDocument,
    LegalDocumentType, LegalAcceptance, TenantAuditLog, AuditLogAction,
    UserSecurityProfile, AccountActivationToken, ClientOnboarding,
    OnboardingApprovalStatus, OnboardingRegistrationStatus,
    TransactionalEmail, VerificationPurpose,
)
from .forms import ClientRegistrationForm
from .onboarding_service import (
    OnboardingError,
    VerificationThrottleError,
    change_onboarding_email,
    check_and_record_verification_send,
    confirm_recovery_email_token,
    consume_verification_token,
    get_client_ip,
    get_policy_config,
    is_synthetic_email,
    issue_onboarding_verification,
    normalize_email_safe,
    submit_public_registration,
)
from .email_service import email_status_label, queue_verification_email

User = get_user_model()
logger = logging.getLogger(__name__)


def generate_unique_tenant_slug(base_name: str) -> str:
    base_slug = slugify(base_name) or 'workspace'
    slug = base_slug
    counter = 1
    while Tenant.objects.filter(slug=slug).exists():
        counter += 1
        slug = f"{base_slug}-{counter}"
    return slug


def signup_view(request):
    """
    Public self-service SaaS instant provisioning is disabled per operator approval policy.
    Rejects direct POST submissions with HTTP 403 Forbidden.
    Redirects GET requests to the approval-gated client registration route.
    """
    if request.method == 'POST':
        return HttpResponseForbidden(
            "Self-service instant activation is disabled. Please submit a client registration request."
        )
    return redirect('request-access')


@never_cache
@require_http_methods(['GET', 'POST'])
def request_access_view(request):
    """
    Entry Point A: Public approval-gated client registration.
    Does not collect a password or create an active account before email verification and platform approval.
    """
    if request.user.is_authenticated:
        return redirect('dashboard')

    initial = {}
    plan_param = (request.GET.get('plan') or '').strip()
    if plan_param:
        plan_match = PlanTier.objects.filter(is_published=True, code__iexact=plan_param).first()
        if plan_match:
            initial['requested_plan'] = plan_match.pk

    status_code = 200
    if request.method == 'POST':
        form = ClientRegistrationForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            try:
                outcome = submit_public_registration(
                    business_name=cd['business_name'],
                    owner_full_name=cd['owner_full_name'],
                    owner_email=cd['owner_email'],
                    desired_username=cd['desired_username'],
                    whatsapp_number=cd.get('whatsapp_number', ''),
                    requested_plan=cd.get('requested_plan'),
                    terms_accepted=cd.get('terms_accepted', False),
                    marketing_consent=cd.get('marketing_consent', False),
                    notes=cd.get('notes', ''),
                    request=request,
                )
                if outcome.status == 'protected_conflict':
                    request.session.pop('pending_onboarding_id', None)
                    request.session['check_email_generic'] = outcome.message
                elif outcome.onboarding is not None:
                    request.session['pending_onboarding_id'] = str(outcome.onboarding.pk)
                    request.session.pop('check_email_generic', None)
                return redirect('registration-check-email')
            except VerificationThrottleError as exc:
                form.add_error(None, exc.message)
                status_code = 429
            except OnboardingError as exc:
                field_map = {
                    'invalid_email': 'owner_email',
                    'synthetic_identifier': 'owner_email',
                    'email_taken': 'owner_email',
                    'invalid_username': 'desired_username',
                    'username_taken': 'desired_username',
                    'invalid_business': 'business_name',
                    'business_taken': 'business_name',
                    'invalid_whatsapp': 'whatsapp_number',
                    'whatsapp_taken': 'whatsapp_number',
                    'terms_required': 'terms_accepted',
                }
                target_field = field_map.get(exc.code)
                form.add_error(target_field, exc.message)
                status_code = exc.status
    else:
        form = ClientRegistrationForm(initial=initial)

    active_terms = LegalDocument.get_active_document(LegalDocumentType.TERMS)
    active_privacy = LegalDocument.get_active_document(LegalDocumentType.PRIVACY)
    return render(
        request,
        'tenants/request_access.html',
        {
            'form': form,
            'active_terms': active_terms,
            'active_privacy': active_privacy,
        },
        status=status_code,
    )


@never_cache
@require_http_methods(['GET', 'POST'])
def registration_check_email_view(request):
    """
    Standalone "Check your email" flow for newly submitted or invited owners.
    Allows session-bound resend (enforcing 60s cooldown + 5/hr caps) and email address
    correction while unverified. Never leaks sensitive tokens or external accounts.
    """
    onboarding = None
    pending_id = request.session.get('pending_onboarding_id')
    if pending_id:
        onboarding = ClientOnboarding.objects.filter(pk=pending_id).first()

    generic_notice = request.session.get('check_email_generic')
    status_code = 200
    feedback = None
    error_feedback = None
    retry_after = 0

    if request.method == 'POST' and onboarding and not onboarding.email_verified:
        action = request.POST.get('action', 'resend')
        if action == 'change_email':
            new_email = request.POST.get('new_email', '')
            try:
                onboarding, _, _ = change_onboarding_email(
                    onboarding=onboarding,
                    new_email=new_email,
                    request=request,
                )
                feedback = f"Updated email address to {onboarding.owner_email} and sent a fresh 30-minute verification link. Any previous link is now invalid."
            except VerificationThrottleError as exc:
                error_feedback = exc.message
                retry_after = exc.retry_after
                status_code = 429
            except OnboardingError as exc:
                error_feedback = exc.message
                status_code = exc.status
        else:
            try:
                issue_onboarding_verification(onboarding=onboarding, request=request, enforce_cooldown=True)
                feedback = f"Sent a fresh verification email to {onboarding.owner_email} (valid for 30 minutes)."
            except VerificationThrottleError as exc:
                error_feedback = exc.message
                retry_after = exc.retry_after
                status_code = 429
            except OnboardingError as exc:
                error_feedback = exc.message
                status_code = exc.status

    latest_email = None
    email_status_text = None
    cooldown_remaining = retry_after
    policy = get_policy_config()
    if onboarding:
        latest_email = TransactionalEmail.objects.filter(
            onboarding=onboarding, purpose='VERIFICATION'
        ).order_by('-created_at').first()
        if latest_email:
            email_status_text = email_status_label(latest_email.status)
        if not onboarding.email_verified and cooldown_remaining == 0:
            last_tok = EmailVerificationToken.objects.filter(
                onboarding=onboarding, purpose=VerificationPurpose.EMAIL_VERIFY
            ).exclude(invalidation_reason='EMAIL_CHANGED').order_by('-created_at').first()
            if last_tok:
                elapsed = (timezone.now() - last_tok.created_at).total_seconds()
                if elapsed < policy['resend_cooldown_seconds']:
                    cooldown_remaining = max(1, int(policy['resend_cooldown_seconds'] - elapsed))

    response = render(
        request,
        'tenants/check_email.html',
        {
            'onboarding': onboarding,
            'generic_notice': generic_notice,
            'feedback': feedback,
            'error_feedback': error_feedback,
            'latest_email': latest_email,
            'email_status_text': email_status_text,
            'cooldown_remaining': cooldown_remaining,
            'expiry_minutes': policy['verification_expiry_minutes'],
        },
        status=status_code,
    )
    response['Cache-Control'] = 'no-store'
    return response


@never_cache
@require_http_methods(['GET', 'HEAD', 'POST'])
def activate_account_view(request, token):
    """
    Single-use, expiring activation link for pre-provisioned & email-verified identities
    to establish their own password. Never marks an unverified email as verified.
    """
    activation_token = AccountActivationToken.lookup_by_raw(token)

    if not activation_token or not activation_token.is_valid:
        resp = render(request, 'tenants/activate_error.html', {
            'error': 'This activation link is invalid, has already been used, or has expired. Please contact your Super Admin to request a new activation link.'
        }, status=400)
        resp['Cache-Control'] = 'no-store'
        return resp

    user = activation_token.user
    onboarding = ClientOnboarding.objects.filter(owner_user=user).first()
    if onboarding and (not onboarding.email_verified or onboarding.approval_status != OnboardingApprovalStatus.APPROVED):
        resp = render(request, 'tenants/activate_error.html', {
            'error': 'Owner email verification and platform approval must be completed before setting a password.'
        }, status=403)
        resp['Cache-Control'] = 'no-store'
        return resp

    error_msg = None

    if request.method == 'POST':
        password = request.POST.get('password', '')
        confirm_password = request.POST.get('confirm_password', '')

        if len(password) > 1024:
            error_msg = 'Password is too long.'
        elif not password or len(password) < 8:
            error_msg = "Password must be at least 8 characters long."
        elif password != confirm_password:
            error_msg = "Passwords do not match."
        else:
            from django.contrib.auth.password_validation import validate_password
            from django.core.exceptions import ValidationError
            try:
                validate_password(password, user=user)
            except ValidationError as error:
                resp = render(request, 'tenants/activate.html', {
                    'user_obj': user,
                    'token': token,
                    'expires_at': activation_token.expires_at,
                    'error_msg': ' '.join(error.messages),
                })
                resp['Cache-Control'] = 'no-store'
                return resp

            with transaction.atomic():
                user = User.objects.select_for_update().get(pk=user.pk)
                activation_token = AccountActivationToken.objects.select_for_update().get(pk=activation_token.pk)
                if not activation_token.is_valid:
                    resp = render(request, 'tenants/activate_error.html', {'error': 'This activation link has expired or been used.'}, status=400)
                    resp['Cache-Control'] = 'no-store'
                    return resp

                now = timezone.now()
                user.set_password(password)
                user.is_active = True
                user.save(update_fields=['password', 'is_active'])

                activation_token.is_used = True
                activation_token.used_at = now
                activation_token.save(update_fields=['is_used', 'used_at'])

                locked_onb = ClientOnboarding.objects.select_for_update().filter(owner_user=user).first()
                if locked_onb:
                    locked_onb.password_set = True
                    locked_onb.password_set_at = now
                    if locked_onb.email_verified and locked_onb.approval_status == OnboardingApprovalStatus.APPROVED:
                        locked_onb.registration_status = OnboardingRegistrationStatus.ACTIVE
                    locked_onb.save(update_fields=['password_set', 'password_set_at', 'registration_status', 'updated_at'])

                TenantAuditLog.objects.create(
                    tenant=locked_onb.tenant if locked_onb else None,
                    actor=user,
                    action=AuditLogAction.ACCOUNT_ACTIVATED,
                    summary=f"User @{user.username} established password via single-use activation token",
                    details={'user_id': user.pk}
                )

            if request.user.is_authenticated and request.user.pk != user.pk:
                resp = render(request, 'tenants/activate_complete.html', {'user_obj': user})
                resp['Cache-Control'] = 'no-store'
                return resp

            from django.contrib.auth import authenticate
            authenticated_user = authenticate(username=user.username, password=password)
            if authenticated_user:
                auth_login(request, authenticated_user)
                return redirect('spa-app-root')
            return redirect('login')

    resp = render(request, 'tenants/activate.html', {
        'user_obj': user,
        'token': token,
        'error_msg': error_msg,
        'expires_at': activation_token.expires_at,
    })
    resp['Cache-Control'] = 'no-store'
    return resp


@never_cache
@require_http_methods(['GET', 'HEAD', 'POST'])
def verify_email_view(request, token):
    """
    Mail-scanner-safe two-step email verification endpoint.
    GET shows confirmation button without consuming token.
    POST atomically verifies & consumes the EMAIL_VERIFY token.
    """
    if request.method in ('GET', 'HEAD'):
        token_obj = EmailVerificationToken.lookup_by_raw(token)
        if not token_obj:
            resp = render(request, 'tenants/verify_result.html', {'is_valid': False, 'error_message': 'This verification link is invalid.'}, status=404)
            resp['Cache-Control'] = 'no-store'
            return resp
        if token_obj.purpose != VerificationPurpose.EMAIL_VERIFY:
            resp = render(request, 'tenants/verify_result.html', {'is_valid': False, 'error_message': 'This link is for a different verification purpose.'}, status=400)
            resp['Cache-Control'] = 'no-store'
            return resp
        if not token_obj.is_valid:
            msg = 'This verification link is invalid, superseded, already consumed, or has expired. Request a new link below.'
            resp = render(request, 'tenants/verify_result.html', {'is_valid': False, 'error_message': msg}, status=410)
            resp['Cache-Control'] = 'no-store'
            return resp
        target_email = token_obj.intended_email or (token_obj.onboarding.owner_email if token_obj.onboarding else (token_obj.user.email if token_obj.user else ''))
        if token_obj.onboarding and token_obj.onboarding.owner_email.lower() != target_email.lower():
            resp = render(request, 'tenants/verify_result.html', {'is_valid': False, 'error_message': 'This verification link was superseded by an email update.'}, status=410)
            resp['Cache-Control'] = 'no-store'
            return resp
        resp = render(request, 'tenants/verify_confirm.html', {
            'token': token,
            'target_email': target_email,
            'business_name': token_obj.onboarding.business_name if token_obj.onboarding else '',
            'expires_at': token_obj.expires_at,
            'is_recovery': False,
        })
        resp['Cache-Control'] = 'no-store'
        return resp

    try:
        res = consume_verification_token(raw_token=token, request=request)
    except OnboardingError as exc:
        resp = render(request, 'tenants/verify_result.html', {
            'is_valid': False,
            'error_message': exc.message,
        }, status=exc.status)
        resp['Cache-Control'] = 'no-store'
        return resp

    onboarding = res['onboarding']
    user_obj = res['user']
    verified_email = onboarding.owner_email if onboarding else user_obj.email
    resp = render(request, 'tenants/verify_result.html', {
        'is_valid': True,
        'user_email': verified_email,
        'next_step': res['next_step'],
        'onboarding': onboarding,
    })
    resp['Cache-Control'] = 'no-store'
    return resp


@never_cache
@require_http_methods(['GET', 'HEAD', 'POST'])
def verify_recovery_email_view(request, token):
    """
    Mail-scanner-safe confirmation endpoint for verifying a user's recovery email address.
    """
    if request.method in ('GET', 'HEAD'):
        token_obj = EmailVerificationToken.lookup_by_raw(token)
        if not token_obj or token_obj.purpose != VerificationPurpose.RECOVERY_EMAIL_VERIFY or not token_obj.is_valid:
            resp = render(request, 'tenants/verify_result.html', {
                'is_valid': False,
                'error_message': 'This recovery email verification link is invalid, expired, or already used.',
                'is_recovery': True,
            }, status=410 if token_obj else 404)
            resp['Cache-Control'] = 'no-store'
            return resp
        resp = render(request, 'tenants/verify_confirm.html', {
            'token': token,
            'target_email': token_obj.intended_email,
            'expires_at': token_obj.expires_at,
            'is_recovery': True,
        })
        resp['Cache-Control'] = 'no-store'
        return resp

    try:
        res = confirm_recovery_email_token(raw_token=token, request=request)
    except OnboardingError as exc:
        resp = render(request, 'tenants/verify_result.html', {
            'is_valid': False,
            'error_message': exc.message,
            'is_recovery': True,
        }, status=exc.status)
        resp['Cache-Control'] = 'no-store'
        return resp

    resp = render(request, 'tenants/verify_result.html', {
        'is_valid': True,
        'is_recovery': True,
        'user_email': res['recovery_email'],
        'next_step': 'recovery_verified',
    })
    resp['Cache-Control'] = 'no-store'
    return resp


@never_cache
@require_http_methods(['GET', 'POST'])
def resend_verification_view(request):
    """
    Throttled resend endpoint supporting both pending registrations (ClientOnboarding)
    and existing unverified real-mailbox users. Enforces 60s cooldown, 5/hr/email, and IP cap.
    """
    if request.method == 'POST':
        raw_email = (request.POST.get('email') or '').strip()
        if not raw_email and request.user.is_authenticated:
            raw_email = request.user.email

        try:
            normalized = normalize_email_safe(raw_email)
        except OnboardingError as exc:
            messages.error(request, exc.message)
            return render(request, 'tenants/resend_verification.html', {'error_message': exc.message}, status=400)

        ip_addr = get_client_ip(request)
        if not is_synthetic_email(normalized):
            onboarding = ClientOnboarding.objects.filter(
                owner_email__iexact=normalized,
                email_verified=False,
            ).exclude(approval_status=OnboardingApprovalStatus.REJECTED).order_by('-created_at').first()

            if onboarding is not None:
                try:
                    issue_onboarding_verification(onboarding=onboarding, request=request, enforce_cooldown=True)
                except VerificationThrottleError as exc:
                    messages.warning(request, exc.message)
                    return render(request, 'tenants/resend_verification.html', {'error_message': exc.message, 'retry_after': exc.retry_after}, status=429)
            else:
                user = User.objects.filter(email__iexact=normalized, is_active=True).first()
                sec = UserSecurityProfile.get_or_create_for_user(user) if user else None
                try:
                    with transaction.atomic():
                        check_and_record_verification_send(
                            email=normalized,
                            ip_address=ip_addr,
                            user=user,
                            purpose=VerificationPurpose.EMAIL_VERIFY,
                            enforce_cooldown=bool(user and sec and not sec.email_verified and not sec.skip_mailbox_gate),
                        )
                        if user and sec and not sec.email_verified and not sec.skip_mailbox_gate:
                            policy = get_policy_config()
                            tok = EmailVerificationToken.issue_token(
                                user=user,
                                intended_email=normalized,
                                purpose=VerificationPurpose.EMAIL_VERIFY,
                                minutes=policy['verification_expiry_minutes'],
                            )
                            queue_verification_email(request=request, token=tok, recipient=normalized, user=user)
                except VerificationThrottleError as exc:
                    messages.warning(request, exc.message)
                    return render(request, 'tenants/resend_verification.html', {'error_message': exc.message, 'retry_after': exc.retry_after}, status=429)

        # Safe generic response to prevent user enumeration
        messages.success(request, "If an eligible unverified account or registration matches that email, a fresh 30-minute verification link has been sent.")
        return render(request, 'tenants/resend_verification.html', {'sent': True})

    return render(request, 'tenants/resend_verification.html')


def verification_notice_view(request):
    """
    Displays gate screen for unverified users attempting to access protected workspace areas.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect('login')

    sec_profile = UserSecurityProfile.get_or_create_for_user(user)
    if sec_profile.email_verified or sec_profile.skip_mailbox_gate:
        return redirect('dashboard')

    return render(request, 'tenants/verify_notice.html', {
        'user': user,
    })


def access_pending_view(request):
    """
    Standalone status screen for verified/registered clients awaiting approval or workspace assignment.
    """
    user = request.user
    if user.is_authenticated:
        memberships = user.tenant_memberships.filter(is_active=True, tenant__is_active=True)
        if memberships.exists():
            return redirect('dashboard')
        onboarding = ClientOnboarding.objects.filter(owner_user=user).first()
        return render(request, 'tenants/access_pending.html', {
            'user': user,
            'onboarding': onboarding,
        })

    pending_id = request.session.get('pending_onboarding_id')
    onboarding = ClientOnboarding.objects.filter(pk=pending_id).first() if pending_id else None
    if onboarding:
        return render(request, 'tenants/access_pending.html', {
            'user': None,
            'onboarding': onboarding,
        })
    return redirect('login')


def tenant_select_view(request):
    """
    Allows multi-tenant users to switch between their authorized workspaces.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect('login')

    memberships = user.tenant_memberships.filter(is_active=True, tenant__is_active=True).select_related('tenant')
    if not memberships.exists():
        return redirect('access-pending')

    if memberships.count() == 1:
        request.session['active_tenant_id'] = memberships.first().tenant.id
        return redirect('dashboard')

    return render(request, 'tenants/tenant_select.html', {
        'memberships': memberships,
        'current_tenant': getattr(request, 'tenant', None),
    })


def tenant_switch_view(request, tenant_id):
    """
    Switches active workspace context for a multi-tenant user.
    Enforces membership check so users cannot switch into workspaces they do not belong to.
    """
    user = request.user
    if not user.is_authenticated:
        return redirect('login')

    # Validate that user has an active membership in target tenant
    membership = user.tenant_memberships.filter(
        tenant_id=tenant_id,
        is_active=True,
        tenant__is_active=True
    ).first()

    if not membership:
        logger.warning(f"Unauthorized workspace switch attempt: User {user} attempted to switch to tenant {tenant_id}")
        return HttpResponseForbidden("You do not have an active membership in this workspace.")

    request.session['active_tenant_id'] = membership.tenant.id
    messages.success(request, f"Switched to workspace: {membership.tenant.name}")
    return redirect('dashboard')
