"""
Shared business logic for Client Onboarding (self-registration & Super Admin invite),
email verification tokens, throttles, recovery routing, session revocation,
and direct tenant staff administration.
"""
import hashlib
import logging
import re
from dataclasses import dataclass

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.contrib.sessions.models import Session
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email as django_validate_email
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.text import slugify

from .models import (
    AccountActivationToken,
    AuditLogAction,
    ClientOnboarding,
    DemoRequest,
    EmailVerificationToken,
    LegalAcceptance,
    LegalDocument,
    LegalDocumentType,
    OnboardingApprovalStatus,
    OnboardingProgress,
    OnboardingRegistrationStatus,
    OnboardingSource,
    OnboardingStep,
    PlanTier,
    PlatformServiceConfig,
    RecoveryThrottle,
    SubscriptionStatus,
    Tenant,
    TenantAuditLog,
    TenantMembership,
    TenantRole,
    TenantSubscription,
    UserSecurityProfile,
    VerificationPurpose,
)

User = get_user_model()
logger = logging.getLogger(__name__)

E164_RE = re.compile(r'^\+[1-9]\d{6,14}$')
USERNAME_RE = re.compile(r'^[A-Za-z0-9_.+-]{3,150}$')
SYNTHETIC_EXACT_IDENTIFIERS = {'risal@neorizsolutions.com'}
SYNTHETIC_SUFFIXES = ('.internal', '.local', '.invalid', '.localhost', '.example')

ROLE_RANK = {
    TenantRole.OWNER: 3,
    TenantRole.ADMIN: 2,
    TenantRole.STAFF: 1,
}


class OnboardingError(Exception):
    def __init__(self, message, *, code='onboarding_error', status=400, extra=None):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status = status
        self.extra = extra or {}


class VerificationThrottleError(OnboardingError):
    def __init__(self, message, *, code='throttled', retry_after=60):
        super().__init__(message, code=code, status=429, extra={'retry_after': retry_after})
        self.retry_after = retry_after


def normalize_email_safe(raw_email: str) -> str:
    """
    Trim whitespace and lowercase ONLY the domain part of an email address,
    preserving local-part characters such as dots and '+tags'.
    """
    cleaned = (raw_email or '').strip()
    if not cleaned or '@' not in cleaned:
        raise OnboardingError("Please enter a valid email address.", code='invalid_email', status=400)
    local, domain = cleaned.rsplit('@', 1)
    if not local or not domain:
        raise OnboardingError("Please enter a valid email address.", code='invalid_email', status=400)
    normalized = f"{local}@{domain.lower()}"
    try:
        django_validate_email(normalized)
    except DjangoValidationError as exc:
        raise OnboardingError("Please enter a valid email address.", code='invalid_email', status=400) from exc
    return normalized


def is_synthetic_email(raw_email: str) -> bool:
    """
    Detect internal synthetic identifiers (such as risal@neorizsolutions.com or *.local/*.internal)
    that are NOT deliverable external mailboxes.
    """
    cleaned = (raw_email or '').strip().lower()
    if not cleaned:
        return False
    if cleaned in SYNTHETIC_EXACT_IDENTIFIERS:
        return True
    return any(cleaned.endswith(suffix) for suffix in SYNTHETIC_SUFFIXES)


def validate_whatsapp_e164(raw_number: str, *, required: bool = False) -> str:
    cleaned = re.sub(r'[\s\-\(\)]', '', (raw_number or '').strip())
    if not cleaned:
        if required:
            raise OnboardingError("WhatsApp Business number is required in E.164 format (e.g. +919876543210).", code='invalid_whatsapp', status=400)
        return ''
    if not E164_RE.match(cleaned):
        raise OnboardingError("WhatsApp Business number must be valid E.164 format (e.g. +919876543210).", code='invalid_whatsapp', status=400)
    return cleaned


def get_client_ip(request) -> str | None:
    if request is None:
        return None
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if forwarded:
        return forwarded.split(',')[0].strip()[:45]
    remote = request.META.get('REMOTE_ADDR', '')
    return remote.strip()[:45] or None


def get_policy_config() -> dict:
    cfg = PlatformServiceConfig.objects.filter(pk=1).first()
    return {
        'verification_expiry_minutes': (cfg.verification_expiry_minutes if cfg and cfg.verification_expiry_minutes else 30),
        'resend_cooldown_seconds': (cfg.resend_cooldown_seconds if cfg and cfg.resend_cooldown_seconds else 60),
        'resend_max_per_hour': (cfg.resend_max_per_hour if cfg and cfg.resend_max_per_hour else 5),
        'ip_max_per_hour': int(getattr(settings, 'VERIFICATION_IP_HOURLY_LIMIT', 15)),
        'support_alert_email': (cfg.support_alert_email if cfg and cfg.support_alert_email else 'support@neorizsolutions.com'),
        'support_escalation_minutes': (cfg.support_escalation_minutes if cfg and cfg.support_escalation_minutes else 10),
    }


def _consume_hourly_throttle(key: str, *, max_attempts: int, now=None) -> tuple[bool, int]:
    now = now or timezone.now()
    row, _ = RecoveryThrottle.objects.select_for_update().get_or_create(
        key=key,
        defaults={'window_started_at': now, 'attempts': 0},
    )
    elapsed = (now - row.window_started_at).total_seconds()
    if elapsed >= 3600:
        row.window_started_at = now
        row.attempts = 0
    if row.attempts >= max_attempts:
        retry_after = max(1, int(3600 - elapsed))
        return False, retry_after
    row.attempts += 1
    row.save(update_fields=['window_started_at', 'attempts'])
    return True, 0


def check_and_record_verification_send(
    *,
    email: str,
    ip_address: str | None = None,
    onboarding: ClientOnboarding | None = None,
    user=None,
    purpose: str = VerificationPurpose.EMAIL_VERIFY,
    enforce_cooldown: bool = True,
):
    """
    Enforce resend cooldown (60s), per-email hourly cap (5/hr), and per-IP hourly abuse cap
    under row locks before issuing a new verification token.
    """
    policy = get_policy_config()
    now = timezone.now()
    normalized = normalize_email_safe(email)

    if enforce_cooldown:
        last_qs = EmailVerificationToken.objects.select_for_update().filter(
            purpose=purpose,
        )
        if onboarding is not None:
            last_qs = last_qs.filter(onboarding=onboarding)
        elif user is not None:
            last_qs = last_qs.filter(user=user)
        else:
            last_qs = last_qs.filter(intended_email__iexact=normalized)
        last_tok = last_qs.exclude(invalidation_reason='EMAIL_CHANGED').order_by('-created_at').first()
        if last_tok is not None:
            since_last = (now - last_tok.created_at).total_seconds()
            if since_last < policy['resend_cooldown_seconds']:
                wait_sec = max(1, int(policy['resend_cooldown_seconds'] - since_last) + 1)
                raise VerificationThrottleError(
                    f"Please wait {wait_sec} seconds before requesting another verification email.",
                    code='cooldown',
                    retry_after=wait_sec,
                )

    email_key = hashlib.sha256(f"vfy-email:{purpose}:{normalized.lower()}".encode('utf-8')).hexdigest()
    ok_email, retry_email = _consume_hourly_throttle(
        email_key,
        max_attempts=policy['resend_max_per_hour'],
        now=now,
    )
    if not ok_email:
        raise VerificationThrottleError(
            "Maximum verification emails per hour reached for this address. Please try again later.",
            code='email_hourly_limit',
            retry_after=retry_email,
        )

    if ip_address:
        ip_key = hashlib.sha256(f"vfy-ip:{purpose}:{ip_address}".encode('utf-8')).hexdigest()
        ok_ip, retry_ip = _consume_hourly_throttle(
            ip_key,
            max_attempts=policy['ip_max_per_hour'],
            now=now,
        )
        if not ok_ip:
            raise VerificationThrottleError(
                "Too many verification requests from this network. Please wait before trying again.",
                code='ip_hourly_limit',
                retry_after=retry_ip,
            )


def invalidate_open_verification_tokens(*, onboarding=None, user=None, reason='CANCELLED', purpose=None):
    qs = EmailVerificationToken.objects.filter(is_used=False)
    if purpose:
        qs = qs.filter(purpose=purpose)
    if onboarding is not None:
        qs = qs.filter(onboarding=onboarding)
    if user is not None and onboarding is None:
        qs = qs.filter(user=user)
    return qs.update(is_used=True, invalidation_reason=reason)


def issue_onboarding_verification(
    *,
    onboarding: ClientOnboarding,
    request=None,
    enforce_cooldown: bool = True,
    queue_mail: bool = True,
):
    from .email_service import queue_verification_email

    if onboarding.email_verified:
        raise OnboardingError("Email address is already verified.", code='already_verified', status=400)
    if onboarding.approval_status == OnboardingApprovalStatus.REJECTED:
        raise OnboardingError("This registration was rejected and cannot verify.", code='rejected', status=400)

    normalized_email = normalize_email_safe(onboarding.owner_email)
    if is_synthetic_email(normalized_email):
        raise OnboardingError(
            "Internal synthetic identifiers cannot receive external verification mail.",
            code='synthetic_identifier',
            status=400,
        )

    ip_addr = get_client_ip(request)
    policy = get_policy_config()

    with transaction.atomic():
        locked = ClientOnboarding.objects.select_for_update().get(pk=onboarding.pk)
        if locked.email_verified:
            raise OnboardingError("Email address is already verified.", code='already_verified', status=400)
        check_and_record_verification_send(
            email=normalized_email,
            ip_address=ip_addr,
            onboarding=locked,
            user=locked.owner_user,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            enforce_cooldown=enforce_cooldown,
        )
        token_obj = EmailVerificationToken.issue_token(
            onboarding=locked,
            user=locked.owner_user,
            intended_email=normalized_email,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            minutes=policy['verification_expiry_minutes'],
        )
        email_job = None
        if queue_mail:
            email_job = queue_verification_email(
                request=request,
                token=token_obj,
                recipient=normalized_email,
                onboarding=locked,
                tenant=locked.tenant,
                user=locked.owner_user,
            )
    return token_obj, email_job


def _unique_tenant_slug(business_name: str) -> str:
    base = slugify(business_name) or 'client-workspace'
    base = base[:140]
    candidate = base
    suffix = 1
    while Tenant.objects.filter(slug=candidate).exists():
        candidate = f"{base}-{suffix}"[:160]
        suffix += 1
    return candidate


def _ensure_legal_acceptance_for_onboarding(onboarding: ClientOnboarding, user: User, ip_address: str | None = None):
    doc = onboarding.terms_document or LegalDocument.get_active_document(LegalDocumentType.TERMS)
    if doc and not LegalAcceptance.objects.filter(user=user, document=doc).exists():
        LegalAcceptance.objects.create(
            user=user,
            document=doc,
            ip_address=ip_address,
        )


@dataclass
class RegistrationOutcome:
    status: str  # 'created', 'pending_existing', 'protected_conflict', 'conflict'
    onboarding: ClientOnboarding | None = None
    email_job_id: str | None = None
    message: str = ''


def submit_public_registration(
    *,
    business_name: str,
    owner_full_name: str,
    owner_email: str,
    desired_username: str,
    whatsapp_number: str = '',
    requested_plan: PlanTier | None = None,
    terms_accepted: bool = False,
    marketing_consent: bool = False,
    notes: str = '',
    request=None,
) -> RegistrationOutcome:
    """
    Entry Point A: Public self-registration.
    Captures onboarding details without setting any password, enforces normalized email,
    prevents takeover of existing accounts/usernames/workspaces, issues a 30-min verification token,
    and queues verification mail.
    """
    from .email_service import queue_verification_email

    biz = (business_name or '').strip()
    full_name = (owner_full_name or '').strip()
    username = (desired_username or '').strip()
    if not biz:
        raise OnboardingError("Business name is required.", code='invalid_business', status=400)
    if not full_name:
        raise OnboardingError("Owner or administrator full name is required.", code='invalid_name', status=400)
    if not USERNAME_RE.match(username):
        raise OnboardingError(
            "Desired username must be 3–150 characters using letters, numbers, dots, underscores, +, or hyphens.",
            code='invalid_username',
            status=400,
        )
    if not terms_accepted:
        raise OnboardingError("You must accept the Terms of Service and Privacy Policy to register.", code='terms_required', status=400)

    normalized_email = normalize_email_safe(owner_email)
    if is_synthetic_email(normalized_email):
        raise OnboardingError(
            "Please use a real deliverable business email address for registration.",
            code='synthetic_identifier',
            status=400,
        )
    cleaned_wa = validate_whatsapp_e164(whatsapp_number, required=False)
    ip_addr = get_client_ip(request)
    policy = get_policy_config()

    with transaction.atomic():
        # Block silent takeover of existing User accounts without mutating them.
        if User.objects.filter(email__iexact=normalized_email).exists():
            return RegistrationOutcome(
                status='protected_conflict',
                onboarding=None,
                message=(
                    "If this email is eligible for registration, we have sent a verification link. "
                    "If you already have an account, please sign in or recover access instead."
                ),
            )
        if User.objects.filter(username__iexact=username).exists():
            raise OnboardingError("That username is already taken. Please choose a different username.", code='username_taken', status=409)
        if Tenant.objects.filter(name__iexact=biz).exists():
            raise OnboardingError("A workspace with this business name already exists.", code='business_taken', status=409)
        if cleaned_wa and Tenant.objects.filter(whatsapp_number=cleaned_wa).exists():
            raise OnboardingError("That WhatsApp Business number is already assigned to another workspace.", code='whatsapp_taken', status=409)

        # Lock existing pending onboardings with same email, username, business name, or WA number
        conflict_qs = ClientOnboarding.objects.select_for_update().exclude(
            approval_status=OnboardingApprovalStatus.REJECTED
        ).exclude(
            registration_status=OnboardingRegistrationStatus.CANCELLED
        )
        existing_same_email = conflict_qs.filter(owner_email__iexact=normalized_email).first()
        if existing_same_email is not None:
            if existing_same_email.email_verified or existing_same_email.approval_status == OnboardingApprovalStatus.APPROVED:
                return RegistrationOutcome(
                    status='protected_conflict',
                    onboarding=None,
                    message=(
                        "If this email is eligible for registration, we have sent a verification link. "
                        "Your email may already have an active onboarding or approved workspace."
                    ),
                )
            # Duplicate unverified pending registration for same address: do NOT mutate or overwrite;
            # return existing record only if username also matches, otherwise protect without leak.
            if existing_same_email.desired_username.lower() != username.lower():
                return RegistrationOutcome(
                    status='protected_conflict',
                    onboarding=None,
                    message=(
                        "If this email is eligible for registration, we have sent a verification link."
                    ),
                )
            return RegistrationOutcome(
                status='pending_existing',
                onboarding=existing_same_email,
                message="A registration for this email is already awaiting verification.",
            )

        if conflict_qs.filter(desired_username__iexact=username).exists():
            raise OnboardingError("That username is reserved by an active registration.", code='username_taken', status=409)
        if conflict_qs.filter(business_name__iexact=biz).exists():
            raise OnboardingError("A registration for this business name is already in progress.", code='business_taken', status=409)
        if cleaned_wa and conflict_qs.filter(whatsapp_number=cleaned_wa).exists():
            raise OnboardingError("That WhatsApp number is already linked to another onboarding.", code='whatsapp_taken', status=409)

        check_and_record_verification_send(
            email=normalized_email,
            ip_address=ip_addr,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            enforce_cooldown=False,
        )

        active_terms = LegalDocument.get_active_document(LegalDocumentType.TERMS)
        now = timezone.now()
        demo = DemoRequest.objects.create(
            name=full_name,
            email=normalized_email,
            phone=cleaned_wa or 'N/A',
            company_name=biz,
            primary_interest=requested_plan.name if requested_plan else '',
            notes=notes[:1000] if notes else '',
            status='NEW',
            ip_address=ip_addr,
        )
        onboarding = ClientOnboarding.objects.create(
            source=OnboardingSource.SELF_REGISTRATION,
            business_name=biz,
            owner_full_name=full_name,
            owner_email=normalized_email,
            desired_username=username,
            whatsapp_number=cleaned_wa,
            requested_plan=requested_plan,
            terms_accepted=True,
            terms_accepted_at=now,
            terms_document=active_terms,
            marketing_consent=bool(marketing_consent),
            marketing_consent_at=now if marketing_consent else None,
            ip_address=ip_addr,
            notes=notes[:1000] if notes else '',
            registration_status=OnboardingRegistrationStatus.SUBMITTED,
            email_verified=False,
            approval_status=OnboardingApprovalStatus.PENDING,
            password_set=False,
            demo_request=demo,
        )
        token_obj = EmailVerificationToken.issue_token(
            onboarding=onboarding,
            intended_email=normalized_email,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            minutes=policy['verification_expiry_minutes'],
        )
        email_job = queue_verification_email(
            request=request,
            token=token_obj,
            recipient=normalized_email,
            onboarding=onboarding,
        )
        TenantAuditLog.objects.create(
            tenant=None,
            actor=None,
            action=AuditLogAction.ONBOARDING_REGISTERED,
            summary=f"Public registration submitted for {biz} ({username})",
            details={
                'onboarding_id': str(onboarding.pk),
                'source': onboarding.source,
                'email': normalized_email,
                'requested_plan': requested_plan.code if requested_plan else None,
                'marketing_consent': bool(marketing_consent),
            },
            ip_address=ip_addr,
        )
        return RegistrationOutcome(
            status='created',
            onboarding=onboarding,
            email_job_id=str(email_job.pk) if email_job else None,
            message="Registration submitted. Please verify your email address within 30 minutes.",
        )


def change_onboarding_email(
    *,
    onboarding: ClientOnboarding,
    new_email: str,
    request=None,
    actor=None,
):
    """
    Update pending registration/invite email cleanly: normalizes address, blocks takeovers,
    invalidates prior unconsumed verification tokens ('EMAIL_CHANGED'), resets verification
    state if changed, and queues a new verification email to the corrected address.
    """
    from .email_service import queue_verification_email

    normalized = normalize_email_safe(new_email)
    if is_synthetic_email(normalized):
        raise OnboardingError("Internal synthetic addresses cannot receive verification mail.", code='synthetic_identifier', status=400)

    ip_addr = get_client_ip(request)
    policy = get_policy_config()

    with transaction.atomic():
        locked = ClientOnboarding.objects.select_for_update().get(pk=onboarding.pk)
        if locked.password_set or locked.registration_status == OnboardingRegistrationStatus.ACTIVE:
            raise OnboardingError("Owner account is already active; update contact/recovery email in account settings instead.", code='already_active', status=400)
        if locked.approval_status == OnboardingApprovalStatus.REJECTED:
            raise OnboardingError("Cannot update email for a rejected onboarding.", code='rejected', status=400)

        old_email = locked.owner_email
        if normalized.lower() == old_email.lower() and not locked.email_verified:
            raise OnboardingError("Please enter a different email address or use Resend.", code='unchanged_email', status=400)

        existing_user = User.objects.filter(email__iexact=normalized)
        if locked.owner_user_id:
            existing_user = existing_user.exclude(pk=locked.owner_user_id)
        if existing_user.exists():
            raise OnboardingError("That email address is already associated with another account.", code='email_taken', status=409)

        if ClientOnboarding.objects.exclude(pk=locked.pk).exclude(
            approval_status=OnboardingApprovalStatus.REJECTED
        ).exclude(
            registration_status=OnboardingRegistrationStatus.CANCELLED
        ).filter(owner_email__iexact=normalized).exists():
            raise OnboardingError("That email address is already linked to another active registration.", code='email_taken', status=409)

        invalidate_open_verification_tokens(
            onboarding=locked,
            user=locked.owner_user,
            reason='EMAIL_CHANGED',
            purpose=VerificationPurpose.EMAIL_VERIFY,
        )

        locked.owner_email = normalized
        locked.email_verified = False
        locked.email_verified_at = None
        if locked.approval_status == OnboardingApprovalStatus.PENDING:
            locked.registration_status = OnboardingRegistrationStatus.SUBMITTED
        locked.save(update_fields=['owner_email', 'email_verified', 'email_verified_at', 'registration_status', 'updated_at'])

        if locked.owner_user_id:
            owner = locked.owner_user
            owner.email = normalized
            owner.save(update_fields=['email'])
            sec = UserSecurityProfile.get_or_create_for_user(owner)
            sec.email_verified = False
            sec.email_verified_at = None
            sec.recovery_email_verified = False
            sec.recovery_email_verified_at = None
            sec.save(update_fields=['email_verified', 'email_verified_at', 'recovery_email_verified', 'recovery_email_verified_at'])
        if locked.tenant_id:
            Tenant.objects.filter(pk=locked.tenant_id).update(contact_email=normalized)
        if locked.demo_request_id:
            DemoRequest.objects.filter(pk=locked.demo_request_id).update(email=normalized)

        check_and_record_verification_send(
            email=normalized,
            ip_address=ip_addr,
            onboarding=locked,
            user=locked.owner_user,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            enforce_cooldown=False,
        )
        token_obj = EmailVerificationToken.issue_token(
            onboarding=locked,
            user=locked.owner_user,
            intended_email=normalized,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            minutes=policy['verification_expiry_minutes'],
        )
        email_job = queue_verification_email(
            request=request,
            token=token_obj,
            recipient=normalized,
            onboarding=locked,
            tenant=locked.tenant,
            user=locked.owner_user,
        )
        TenantAuditLog.objects.create(
            tenant=locked.tenant,
            actor=actor,
            action=AuditLogAction.CREDENTIALS_UPDATED,
            summary=f"Registration verification email updated for {locked.business_name}",
            details={'onboarding_id': str(locked.pk), 'old_email': old_email, 'new_email': normalized},
            ip_address=ip_addr,
        )
        return locked, token_obj, email_job


def _provision_workspace_and_owner(
    *,
    onboarding: ClientOnboarding,
    plan: PlanTier,
    whatsapp_number: str,
    actor: User | None,
    ip_address: str | None = None,
) -> tuple[Tenant, User]:
    """
    Create or link Tenant, Subscription, OnboardingProgress, and Owner User + Membership
    for an approved ClientOnboarding record. Caller MUST hold transaction & row lock.
    """
    owner_user = onboarding.owner_user
    if owner_user is None:
        if User.objects.filter(username__iexact=onboarding.desired_username).exists():
            raise OnboardingError(
                f"Username '{onboarding.desired_username}' is already taken.",
                code='username_taken',
                status=409,
            )
        if User.objects.filter(email__iexact=onboarding.owner_email).exists():
            raise OnboardingError(
                f"Email '{onboarding.owner_email}' already belongs to an existing account.",
                code='email_taken',
                status=409,
            )
        parts = onboarding.owner_full_name.strip().split(None, 1)
        first_name = parts[0][:150] if parts else onboarding.desired_username
        last_name = parts[1][:150] if len(parts) > 1 else ''
        owner_user = User.objects.create(
            username=onboarding.desired_username,
            email=onboarding.owner_email,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        owner_user.set_unusable_password()
        owner_user.save(update_fields=['password'])

        profile = UserSecurityProfile.get_or_create_for_user(owner_user)
        profile.email_verified = bool(onboarding.email_verified)
        profile.email_verified_at = onboarding.email_verified_at if onboarding.email_verified else None
        profile.recovery_email = onboarding.owner_email if onboarding.email_verified else ''
        profile.recovery_email_verified = bool(onboarding.email_verified)
        profile.recovery_email_verified_at = onboarding.email_verified_at if onboarding.email_verified else None
        profile.save()

    tenant = onboarding.tenant
    if tenant is None:
        if Tenant.objects.filter(name__iexact=onboarding.business_name).exists():
            raise OnboardingError(
                f"Workspace '{onboarding.business_name}' already exists.",
                code='business_taken',
                status=409,
            )
        cleaned_wa = validate_whatsapp_e164(whatsapp_number, required=False)
        if cleaned_wa and Tenant.objects.filter(whatsapp_number=cleaned_wa).exists():
            raise OnboardingError("That WhatsApp Business number is already assigned to another workspace.", code='whatsapp_taken', status=409)

        tenant = Tenant.objects.create(
            name=onboarding.business_name,
            slug=_unique_tenant_slug(onboarding.business_name),
            is_active=True,
            plan=plan.code if plan else 'starter',
            max_staff=plan.max_staff if plan else 10,
            max_services=plan.max_services if plan else 25,
            contact_email=onboarding.owner_email,
            whatsapp_number=cleaned_wa,
            contact_phone=cleaned_wa,
            requires_meta_setup=True,
        )
        TenantSubscription.objects.create(
            tenant=tenant,
            requested_plan=onboarding.requested_plan or plan,
            effective_plan=plan,
            status=SubscriptionStatus.ACTIVE,
            approved_by=actor,
            approved_at=timezone.now(),
        )
        OnboardingProgress.objects.get_or_create(
            tenant=tenant,
            defaults={
                'current_step': OnboardingStep.WHATSAPP,
                'completed_steps': [OnboardingStep.PROFILE, OnboardingStep.PLAN],
            },
        )
    else:
        cleaned_wa = validate_whatsapp_e164(whatsapp_number, required=False)
        if cleaned_wa and Tenant.objects.exclude(pk=tenant.pk).filter(whatsapp_number=cleaned_wa).exists():
            raise OnboardingError("That WhatsApp Business number is already assigned to another workspace.", code='whatsapp_taken', status=409)
        if cleaned_wa:
            tenant.whatsapp_number = cleaned_wa
            tenant.contact_phone = tenant.contact_phone or cleaned_wa
        tenant.is_active = True
        tenant.plan = plan.code if plan else tenant.plan
        if plan:
            tenant.max_staff = plan.max_staff
            tenant.max_services = plan.max_services
        tenant.save()
        sub, _ = TenantSubscription.objects.get_or_create(
            tenant=tenant,
            defaults={'status': SubscriptionStatus.ACTIVE, 'effective_plan': plan},
        )
        sub.approve(actor, plan=plan)

    TenantMembership.objects.get_or_create(
        tenant=tenant,
        user=owner_user,
        defaults={'role': TenantRole.OWNER, 'is_active': True},
    )
    if onboarding.terms_accepted:
        _ensure_legal_acceptance_for_onboarding(onboarding, owner_user, ip_address=ip_address)
    if onboarding.demo_request_id:
        DemoRequest.objects.filter(pk=onboarding.demo_request_id).update(
            status='PROVISIONED',
            routed_to_tenant=tenant,
        )
    return tenant, owner_user


def approve_client_onboarding(
    *,
    onboarding: ClientOnboarding,
    actor: User,
    assigned_plan: PlanTier,
    whatsapp_number: str | None = None,
    decision_reason: str = '',
    request=None,
) -> dict:
    """
    Approve a ClientOnboarding request with an explicit plan assignment.
    Creates tenant, subscription, and owner identity. Issues password-setup token ONLY
    when the owner email is already verified; otherwise keeps setup gated behind email verification.
    """
    from .email_service import queue_activation, queue_verification_email

    if assigned_plan is None:
        raise OnboardingError("An active subscription plan must be assigned before approval.", code='plan_required', status=400)

    ip_addr = get_client_ip(request)
    policy = get_policy_config()
    now = timezone.now()

    with transaction.atomic():
        locked = ClientOnboarding.objects.select_for_update().get(pk=onboarding.pk)
        if locked.approval_status == OnboardingApprovalStatus.REJECTED:
            raise OnboardingError("Rejected registrations cannot be approved directly.", code='already_rejected', status=400)

        target_wa = whatsapp_number if whatsapp_number is not None else locked.whatsapp_number
        cleaned_wa = validate_whatsapp_e164(target_wa, required=False)

        tenant, owner_user = _provision_workspace_and_owner(
            onboarding=locked,
            plan=assigned_plan,
            whatsapp_number=cleaned_wa,
            actor=actor,
            ip_address=ip_addr,
        )

        locked.whatsapp_number = cleaned_wa
        locked.assigned_plan = assigned_plan
        locked.approval_status = OnboardingApprovalStatus.APPROVED
        locked.approved_by = actor
        locked.approved_at = now
        locked.decision_reason = (decision_reason or '').strip()[:1000]
        locked.tenant = tenant
        locked.owner_user = owner_user
        locked.registration_status = (
            OnboardingRegistrationStatus.ACTIVE
            if (locked.email_verified and locked.password_set)
            else OnboardingRegistrationStatus.APPROVED
        )
        locked.save()

        activation_job = None
        verification_job = None
        if locked.email_verified:
            if not owner_user.has_usable_password():
                act_tok = AccountActivationToken.create_for_user(owner_user, valid_hours=48)
                activation_job = queue_activation(request, act_tok, tenant=tenant, onboarding=locked)
        else:
            # Never skip verification when approved before email verify; ensure a live verification token exists
            has_live_verify = EmailVerificationToken.objects.filter(
                onboarding=locked,
                purpose=VerificationPurpose.EMAIL_VERIFY,
                is_used=False,
                invalidation_reason='',
                expires_at__gt=now,
            ).exists()
            if not has_live_verify and not is_synthetic_email(locked.owner_email):
                v_tok = EmailVerificationToken.issue_token(
                    onboarding=locked,
                    user=owner_user,
                    intended_email=locked.owner_email,
                    purpose=VerificationPurpose.EMAIL_VERIFY,
                    minutes=policy['verification_expiry_minutes'],
                )
                verification_job = queue_verification_email(
                    request=request,
                    token=v_tok,
                    recipient=locked.owner_email,
                    onboarding=locked,
                    tenant=tenant,
                    user=owner_user,
                )

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=actor,
            action=AuditLogAction.ONBOARDING_APPROVED,
            summary=f"Approved onboarding for {locked.business_name} on plan {assigned_plan.name}",
            details={
                'onboarding_id': str(locked.pk),
                'plan': assigned_plan.code,
                'email_verified': locked.email_verified,
                'reason': locked.decision_reason,
            },
            ip_address=ip_addr,
        )
        return {
            'onboarding': locked,
            'tenant': tenant,
            'owner': owner_user,
            'activation_email_id': str(activation_job.pk) if activation_job else None,
            'verification_email_id': str(verification_job.pk) if verification_job else None,
        }


def reject_client_onboarding(
    *,
    onboarding: ClientOnboarding,
    actor: User,
    reason: str = '',
    request=None,
) -> ClientOnboarding:
    reason_clean = (reason or '').strip()[:1000]
    if not reason_clean:
        raise OnboardingError("Please provide a decision reason when rejecting an onboarding.", code='reason_required', status=400)

    ip_addr = get_client_ip(request)
    with transaction.atomic():
        locked = ClientOnboarding.objects.select_for_update().get(pk=onboarding.pk)
        if locked.password_set or locked.registration_status == OnboardingRegistrationStatus.ACTIVE:
            raise OnboardingError("Cannot reject an already active workspace via onboarding.", code='already_active', status=400)

        invalidate_open_verification_tokens(onboarding=locked, user=locked.owner_user, reason='REJECTED')
        if locked.owner_user_id:
            AccountActivationToken.objects.filter(user=locked.owner_user, is_used=False).update(is_used=True)
            locked.owner_user.is_active = False
            locked.owner_user.save(update_fields=['is_active'])
        if locked.tenant_id:
            locked.tenant.is_active = False
            locked.tenant.save(update_fields=['is_active'])

        locked.approval_status = OnboardingApprovalStatus.REJECTED
        locked.registration_status = OnboardingRegistrationStatus.REJECTED
        locked.approved_by = actor
        locked.approved_at = timezone.now()
        locked.decision_reason = reason_clean
        locked.save()

        TenantAuditLog.objects.create(
            tenant=locked.tenant,
            actor=actor,
            action=AuditLogAction.ONBOARDING_REJECTED,
            summary=f"Rejected onboarding for {locked.business_name}",
            details={'onboarding_id': str(locked.pk), 'reason': reason_clean},
            ip_address=ip_addr,
        )
    return locked


def create_superadmin_invite(
    *,
    actor: User,
    business_name: str,
    owner_full_name: str,
    owner_email: str,
    desired_username: str,
    assigned_plan: PlanTier,
    whatsapp_number: str = '',
    notes: str = '',
    request=None,
) -> dict:
    """
    Entry Point B: Super Admin creates/invites a new client workspace.
    Enforces the exact same ClientOnboarding model, marks approval_status=APPROVED immediately,
    and still requires owner email verification + owner password setup before operational use.
    """
    from .email_service import queue_verification_email

    biz = (business_name or '').strip()
    full_name = (owner_full_name or '').strip()
    username = (desired_username or '').strip()
    if not biz:
        raise OnboardingError("Business name is required.", code='invalid_business', status=400)
    if not full_name:
        raise OnboardingError("Owner full name is required.", code='invalid_name', status=400)
    if not USERNAME_RE.match(username):
        raise OnboardingError("Username must be 3–150 valid characters.", code='invalid_username', status=400)
    if assigned_plan is None:
        raise OnboardingError("An active plan must be assigned.", code='plan_required', status=400)

    normalized_email = normalize_email_safe(owner_email)
    if is_synthetic_email(normalized_email):
        raise OnboardingError("Owner email must be a deliverable mailbox address.", code='synthetic_identifier', status=400)
    cleaned_wa = validate_whatsapp_e164(whatsapp_number, required=False)
    ip_addr = get_client_ip(request)
    policy = get_policy_config()
    now = timezone.now()

    with transaction.atomic():
        if User.objects.filter(username__iexact=username).exists():
            raise OnboardingError("Username already exists.", code='username_taken', status=409)
        if User.objects.filter(email__iexact=normalized_email).exists():
            raise OnboardingError("An account with this email already exists.", code='email_taken', status=409)
        if Tenant.objects.filter(name__iexact=biz).exists():
            raise OnboardingError("A workspace with this business name already exists.", code='business_taken', status=409)
        if cleaned_wa and Tenant.objects.filter(whatsapp_number=cleaned_wa).exists():
            raise OnboardingError("That WhatsApp Business number is already assigned.", code='whatsapp_taken', status=409)
        if ClientOnboarding.objects.select_for_update().exclude(
            approval_status=OnboardingApprovalStatus.REJECTED
        ).exclude(
            registration_status=OnboardingRegistrationStatus.CANCELLED
        ).filter(owner_email__iexact=normalized_email).exists():
            raise OnboardingError("An active onboarding for this email already exists.", code='email_taken', status=409)

        check_and_record_verification_send(
            email=normalized_email,
            ip_address=ip_addr,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            enforce_cooldown=False,
        )

        onboarding = ClientOnboarding.objects.create(
            source=OnboardingSource.SUPERADMIN_INVITE,
            business_name=biz,
            owner_full_name=full_name,
            owner_email=normalized_email,
            desired_username=username,
            whatsapp_number=cleaned_wa,
            requested_plan=assigned_plan,
            assigned_plan=assigned_plan,
            terms_accepted=False,
            notes=(notes or '').strip()[:1000],
            registration_status=OnboardingRegistrationStatus.APPROVED,
            email_verified=False,
            approval_status=OnboardingApprovalStatus.APPROVED,
            approved_by=actor,
            approved_at=now,
            decision_reason='Invited by platform administrator',
            password_set=False,
            ip_address=ip_addr,
        )
        tenant, owner_user = _provision_workspace_and_owner(
            onboarding=onboarding,
            plan=assigned_plan,
            whatsapp_number=cleaned_wa,
            actor=actor,
            ip_address=ip_addr,
        )
        onboarding.tenant = tenant
        onboarding.owner_user = owner_user
        onboarding.save(update_fields=['tenant', 'owner_user'])

        v_tok = EmailVerificationToken.issue_token(
            onboarding=onboarding,
            user=owner_user,
            intended_email=normalized_email,
            purpose=VerificationPurpose.EMAIL_VERIFY,
            minutes=policy['verification_expiry_minutes'],
        )
        email_job = queue_verification_email(
            request=request,
            token=v_tok,
            recipient=normalized_email,
            onboarding=onboarding,
            tenant=tenant,
            user=owner_user,
        )
        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=actor,
            action=AuditLogAction.ONBOARDING_APPROVED,
            summary=f"Invited new client {biz} ({normalized_email})",
            details={
                'onboarding_id': str(onboarding.pk),
                'source': onboarding.source,
                'plan': assigned_plan.code,
            },
            ip_address=ip_addr,
        )
        return {
            'onboarding': onboarding,
            'tenant': tenant,
            'owner': owner_user,
            'verification_email_id': str(email_job.pk) if email_job else None,
        }


def consume_verification_token(*, raw_token: str, request=None) -> dict:
    """
    Atomically verify and consume a single-use EMAIL_VERIFY token on explicit POST confirmation.
    Enforces token purpose == EMAIL_VERIFY, expiry, single use, and intended_email match.
    If an onboarding is already approved, issues the separate ACCOUNT_ACTIVATION password setup token.
    Never sets passwords, never approves registrations, never unlocks subscriptions or Meta readiness.
    """
    from .email_service import queue_activation

    if not raw_token:
        raise OnboardingError("Invalid verification link.", code='invalid_token', status=400)

    digest = EmailVerificationToken.hash_token(raw_token)
    now = timezone.now()
    ip_addr = get_client_ip(request)

    with transaction.atomic():
        token = (
            EmailVerificationToken.objects.select_for_update()
            .filter(token_digest=digest)
            .first()
        )
        if token is None:
            token = (
                EmailVerificationToken.objects.select_for_update()
                .filter(legacy_token=raw_token)
                .first()
            )
        if token is None:
            raise OnboardingError("This verification link is invalid or unrecognizable.", code='invalid_token', status=404)
        if token.purpose != VerificationPurpose.EMAIL_VERIFY:
            raise OnboardingError("This token cannot be used for email verification.", code='wrong_purpose', status=400)
        if token.invalidation_reason:
            raise OnboardingError("This verification link is no longer valid because a newer request superseded it.", code='superseded', status=410)
        if token.is_used:
            raise OnboardingError("This verification link has already been used.", code='already_used', status=410)
        if token.expires_at <= now:
            raise OnboardingError("This verification link has expired. Please request a fresh verification email.", code='expired', status=410)

        onboarding = None
        if token.onboarding_id:
            onboarding = ClientOnboarding.objects.select_for_update().get(pk=token.onboarding_id)
            if onboarding.approval_status == OnboardingApprovalStatus.REJECTED:
                raise OnboardingError("This registration has been rejected.", code='rejected', status=400)
            if token.intended_email and onboarding.owner_email.lower() != token.intended_email.lower():
                raise OnboardingError("This verification link belongs to an older email address.", code='email_mismatch', status=410)
        elif token.user_id:
            user_locked = User.objects.select_for_update().get(pk=token.user_id)
            if token.intended_email and user_locked.email.lower() != token.intended_email.lower():
                raise OnboardingError("This verification link belongs to an older email address.", code='email_mismatch', status=410)
        else:
            raise OnboardingError("Verification token is detached.", code='invalid_token', status=400)

        token.is_used = True
        token.used_at = now
        token.save(update_fields=['is_used', 'used_at'])

        # Invalidate any other unused EMAIL_VERIFY tokens for the same target
        invalidate_open_verification_tokens(
            onboarding=onboarding,
            user=token.user if onboarding is None else None,
            reason='VERIFIED',
            purpose=VerificationPurpose.EMAIL_VERIFY,
        )

        activation_job = None
        next_step = 'awaiting_approval'

        if onboarding is not None:
            onboarding.email_verified = True
            onboarding.email_verified_at = now
            if onboarding.approval_status == OnboardingApprovalStatus.APPROVED:
                onboarding.registration_status = (
                    OnboardingRegistrationStatus.ACTIVE
                    if onboarding.password_set
                    else OnboardingRegistrationStatus.APPROVED
                )
            else:
                onboarding.registration_status = OnboardingRegistrationStatus.EMAIL_VERIFIED
            onboarding.save(update_fields=['email_verified', 'email_verified_at', 'registration_status', 'updated_at'])

            if onboarding.owner_user_id:
                sec = UserSecurityProfile.get_or_create_for_user(onboarding.owner_user)
                sec.email_verified = True
                sec.email_verified_at = now
                if not is_synthetic_email(onboarding.owner_email):
                    sec.recovery_email = onboarding.owner_email
                    sec.recovery_email_verified = True
                    sec.recovery_email_verified_at = now
                sec.save()

            if onboarding.approval_status == OnboardingApprovalStatus.APPROVED and onboarding.owner_user_id:
                if not onboarding.owner_user.has_usable_password():
                    act_tok = AccountActivationToken.create_for_user(onboarding.owner_user, valid_hours=48)
                    activation_job = queue_activation(request, act_tok, tenant=onboarding.tenant, onboarding=onboarding)
                    next_step = 'password_setup_emailed'
                else:
                    next_step = 'login_ready'

            TenantAuditLog.objects.create(
                tenant=onboarding.tenant,
                actor=onboarding.owner_user,
                action=AuditLogAction.CREDENTIALS_UPDATED,
                summary=f"Verified owner email for {onboarding.business_name}",
                details={'onboarding_id': str(onboarding.pk), 'next_step': next_step},
                ip_address=ip_addr,
            )
            return {
                'onboarding': onboarding,
                'user': onboarding.owner_user,
                'next_step': next_step,
                'activation_email_id': str(activation_job.pk) if activation_job else None,
            }

        # Standalone User verification
        user_obj = User.objects.get(pk=token.user_id)
        sec = UserSecurityProfile.get_or_create_for_user(user_obj)
        sec.email_verified = True
        sec.email_verified_at = now
        if not is_synthetic_email(user_obj.email):
            sec.recovery_email = user_obj.email
            sec.recovery_email_verified = True
            sec.recovery_email_verified_at = now
        sec.save()
        if user_obj.has_usable_password():
            next_step = 'login_ready'
        else:
            next_step = 'awaiting_approval'
        TenantAuditLog.objects.create(
            tenant=None,
            actor=user_obj,
            action=AuditLogAction.CREDENTIALS_UPDATED,
            summary=f"Verified email address for {user_obj.username}",
            details={'user_id': user_obj.pk},
            ip_address=ip_addr,
        )
        return {
            'onboarding': None,
            'user': user_obj,
            'next_step': next_step,
            'activation_email_id': None,
        }


# ---------------------------------------------------------------------------
# Recovery Email & Direct Staff Administration
# ---------------------------------------------------------------------------

def revoke_user_sessions(user: User, *, keep_session_key: str | None = None) -> int:
    """
    Invalidate all active DB-backed sessions for a specific user (optionally keeping one key).
    """
    target_uid = str(user.pk)
    revoked = 0
    for sess in Session.objects.filter(expire_date__gte=timezone.now()).iterator():
        if keep_session_key and sess.session_key == keep_session_key:
            continue
        try:
            data = sess.get_decoded()
        except Exception:
            continue
        if str(data.get('_auth_user_id', '')) == target_uid:
            sess.delete()
            revoked += 1
    return revoked


def is_shared_identity(user: User, tenant: Tenant) -> bool:
    """
    Returns True if the User belongs to other tenants or holds platform privileges,
    meaning tenant-scoped admins MUST NOT mutate global credentials (username/password/email).
    """
    if user.is_superuser or user.is_staff:
        return True
    return TenantMembership.objects.filter(user=user).exclude(tenant=tenant).exists()


def can_manage_member(actor_membership: TenantMembership | None, target_membership: TenantMembership, *, actor_user: User | None = None) -> bool:
    if actor_user and actor_user.is_superuser:
        return True
    if not actor_membership or not actor_membership.is_active:
        return False
    if actor_membership.tenant_id != target_membership.tenant_id:
        return False
    actor_rank = ROLE_RANK.get(actor_membership.role, 0)
    target_rank = ROLE_RANK.get(target_membership.role, 0)
    if actor_membership.role == TenantRole.OWNER:
        # Owner can manage Admins & Staff, and edit non-conflicting profile fields of Owners,
        # though last-owner demotion/deactivation is blocked separately.
        return actor_rank >= target_rank
    if actor_membership.role == TenantRole.ADMIN:
        # Admin can manage STAFF only — strictly lower rank!
        return actor_rank > target_rank
    return False


def assert_not_last_active_owner(tenant: Tenant, target_membership: TenantMembership, *, new_role: str | None = None, new_active: bool | None = None):
    would_lose_owner = (
        target_membership.role == TenantRole.OWNER
        and target_membership.is_active
        and ((new_role is not None and new_role != TenantRole.OWNER) or (new_active is False))
    )
    if not would_lose_owner:
        return
    other_owners = TenantMembership.objects.filter(
        tenant=tenant,
        role=TenantRole.OWNER,
        is_active=True,
    ).exclude(pk=target_membership.pk).exists()
    if not other_owners:
        raise OnboardingError("Cannot demote or deactivate the sole active Workspace Owner.", code='last_owner', status=400)


def assign_staff_identity_fields(
    *,
    user: User,
    contact_email: str = '',
    synthetic_identifier: str = '',
    skip_mailbox_gate: bool = True,
):
    profile = UserSecurityProfile.get_or_create_for_user(user)
    cleaned_email = (contact_email or '').strip()
    cleaned_synth = (synthetic_identifier or '').strip()

    if cleaned_synth:
        synth_lower = cleaned_synth.lower()
        conflict = UserSecurityProfile.objects.filter(internal_identifier__iexact=synth_lower).exclude(user=user).exists()
        if conflict:
            raise OnboardingError("That internal login identifier is already assigned.", code='identifier_taken', status=409)
        profile.internal_identifier = synth_lower
        profile.is_synthetic_identifier = True
        profile.skip_mailbox_gate = True

    if cleaned_email:
        normalized = normalize_email_safe(cleaned_email)
        if is_synthetic_email(normalized):
            # Treat internal synthetic addresses cleanly as synthetic identifier, not deliverable email
            profile.internal_identifier = normalized.lower()
            profile.is_synthetic_identifier = True
            profile.skip_mailbox_gate = True
            if not user.email:
                user.email = ''
                user.save(update_fields=['email'])
        else:
            if User.objects.filter(email__iexact=normalized).exclude(pk=user.pk).exists():
                raise OnboardingError("That contact email belongs to another account.", code='email_taken', status=409)
            user.email = normalized
            user.save(update_fields=['email'])
            profile.recovery_email = normalized
            profile.skip_mailbox_gate = bool(skip_mailbox_gate)
    elif skip_mailbox_gate:
        profile.skip_mailbox_gate = True

    profile.save()
    return profile


def create_tenant_staff_member(
    *,
    tenant: Tenant,
    actor: User,
    actor_membership: TenantMembership | None,
    username: str,
    full_name: str = '',
    role: str = TenantRole.STAFF,
    password: str = '',
    contact_email: str = '',
    synthetic_identifier: str = '',
    request=None,
) -> TenantMembership:
    clean_username = (username or '').strip()
    if not USERNAME_RE.match(clean_username):
        raise OnboardingError("Username must be 3–150 valid characters (letters, digits, ., _, +, -).", code='invalid_username', status=400)
    if role not in (TenantRole.STAFF, TenantRole.ADMIN):
        raise OnboardingError("Direct creation only supports Staff or Admin roles.", code='invalid_role', status=400)
    if not actor.is_superuser:
        if not actor_membership or not actor_membership.is_active:
            raise OnboardingError("Forbidden.", code='forbidden', status=403)
        if actor_membership.role == TenantRole.ADMIN and role != TenantRole.STAFF:
            raise OnboardingError("Tenant Admins can only create Staff members.", code='hierarchy_violation', status=403)
        if actor_membership.role not in (TenantRole.OWNER, TenantRole.ADMIN):
            raise OnboardingError("Only Workspace Owners or Admins can create team members.", code='forbidden', status=403)
    if not password:
        raise OnboardingError("Initial password is required for direct staff creation.", code='password_required', status=400)

    ip_addr = get_client_ip(request)
    with transaction.atomic():
        locked_tenant = Tenant.objects.select_for_update().get(pk=tenant.pk)
        if not locked_tenant.can_add_staff():
            raise OnboardingError(
                f"Staff limit reached ({locked_tenant.effective_max_staff}). Upgrade your subscription plan to add more staff.",
                code='staff_limit_reached',
                status=400,
            )
        if User.objects.filter(username__iexact=clean_username).exists():
            raise OnboardingError("That username is already in use.", code='username_taken', status=409)

        parts = (full_name or '').strip().split(None, 1)
        first_name = parts[0][:150] if parts else ''
        last_name = parts[1][:150] if len(parts) > 1 else ''

        new_user = User(
            username=clean_username,
            first_name=first_name,
            last_name=last_name,
            is_active=True,
        )
        try:
            validate_password(password, user=new_user)
        except DjangoValidationError as exc:
            raise OnboardingError(" ".join(exc.messages), code='weak_password', status=400) from exc

        new_user.set_password(password)
        new_user.save()

        assign_staff_identity_fields(
            user=new_user,
            contact_email=contact_email,
            synthetic_identifier=synthetic_identifier,
            skip_mailbox_gate=True,
        )
        membership = TenantMembership.objects.create(
            tenant=locked_tenant,
            user=new_user,
            role=role,
            is_active=True,
        )
        TenantAuditLog.objects.create(
            tenant=locked_tenant,
            actor=actor,
            action=AuditLogAction.STAFF_CREATED,
            summary=f"Created team member {clean_username} ({role})",
            details={
                'target_user_id': new_user.pk,
                'target_username': clean_username,
                'role': role,
                'mailbox_gate_skipped': True,
            },
            ip_address=ip_addr,
        )
        return membership


def update_tenant_staff_member(
    *,
    tenant: Tenant,
    actor: User,
    actor_membership: TenantMembership | None,
    membership_id: int,
    username: str | None = None,
    full_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    contact_email: str | None = None,
    synthetic_identifier: str | None = None,
    request=None,
) -> TenantMembership:
    ip_addr = get_client_ip(request)
    with transaction.atomic():
        target = (
            TenantMembership.objects.select_for_update()
            .select_related('user')
            .filter(pk=membership_id, tenant=tenant)
            .first()
        )
        if target is None:
            raise OnboardingError("Team member not found.", code='not_found', status=404)
        if not can_manage_member(actor_membership, target, actor_user=actor):
            raise OnboardingError("You do not have permission to modify this team member.", code='hierarchy_violation', status=403)

        target_user = target.user
        global_change_requested = any(v is not None for v in (username, full_name, contact_email, synthetic_identifier))
        if global_change_requested and not actor.is_superuser and is_shared_identity(target_user, tenant):
            raise OnboardingError(
                "This user belongs to multiple workspaces or holds platform privileges. Edit only their workspace role/status here, or manage their identity via Platform Admin.",
                code='shared_identity_protected',
                status=409,
            )

        if role is not None and role != target.role:
            if role not in (TenantRole.STAFF, TenantRole.ADMIN, TenantRole.OWNER):
                raise OnboardingError("Invalid role.", code='invalid_role', status=400)
            if not actor.is_superuser:
                actor_rank = ROLE_RANK.get(actor_membership.role, 0) if actor_membership else 0
                new_rank = ROLE_RANK.get(role, 0)
                if actor_membership and actor_membership.role == TenantRole.ADMIN:
                    raise OnboardingError("Admins cannot change member roles.", code='hierarchy_violation', status=403)
                if new_rank > actor_rank:
                    raise OnboardingError("Cannot promote a member above your own role.", code='hierarchy_violation', status=403)
            assert_not_last_active_owner(tenant, target, new_role=role)
            target.role = role

        if is_active is not None and bool(is_active) != target.is_active:
            assert_not_last_active_owner(tenant, target, new_active=bool(is_active))
            if target.user_id == actor.pk and not bool(is_active) and not actor.is_superuser:
                raise OnboardingError("You cannot deactivate your own active workspace membership.", code='self_deactivation', status=400)
            target.is_active = bool(is_active)

        target.save()

        changed_summary = []
        old_username = target_user.username
        if username is not None:
            clean_un = username.strip()
            if not USERNAME_RE.match(clean_un):
                raise OnboardingError("Invalid username format.", code='invalid_username', status=400)
            if clean_un != target_user.username:
                if User.objects.filter(username__iexact=clean_un).exclude(pk=target_user.pk).exists():
                    raise OnboardingError("That username is already taken.", code='username_taken', status=409)
                target_user.username = clean_un
                changed_summary.append(f"username {old_username}->{clean_un}")

        if full_name is not None:
            parts = full_name.strip().split(None, 1)
            target_user.first_name = parts[0][:150] if parts else ''
            target_user.last_name = parts[1][:150] if len(parts) > 1 else ''
            changed_summary.append("full_name")

        target_user.save()

        if contact_email is not None or synthetic_identifier is not None:
            assign_staff_identity_fields(
                user=target_user,
                contact_email=contact_email or '',
                synthetic_identifier=synthetic_identifier or '',
                skip_mailbox_gate=True,
            )
            changed_summary.append("identity_contact")

        if not target.is_active:
            # If user has no active memberships elsewhere, revoke their sessions immediately
            still_active_elsewhere = TenantMembership.objects.filter(user=target_user, is_active=True).exists()
            if not still_active_elsewhere and not target_user.is_superuser:
                revoke_user_sessions(target_user)

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=actor,
            action=AuditLogAction.STAFF_UPDATED,
            summary=f"Updated team member {target_user.username}",
            details={
                'target_user_id': target_user.pk,
                'role': target.role,
                'is_active': target.is_active,
                'changes': changed_summary,
            },
            ip_address=ip_addr,
        )
        return target


def reset_tenant_staff_password(
    *,
    tenant: Tenant,
    actor: User,
    actor_membership: TenantMembership | None,
    membership_id: int,
    new_password: str,
    request=None,
) -> dict:
    """
    Administrative password reset WITHOUT requiring old password.
    Enforces role hierarchy, shared-account protection, Django password validators,
    and session revocation for the target user. Never logs or returns passwords.
    """
    ip_addr = get_client_ip(request)
    if not new_password:
        raise OnboardingError("New password is required.", code='password_required', status=400)

    with transaction.atomic():
        target = (
            TenantMembership.objects.select_for_update()
            .select_related('user')
            .filter(pk=membership_id, tenant=tenant)
            .first()
        )
        if target is None:
            raise OnboardingError("Team member not found.", code='not_found', status=404)
        if not can_manage_member(actor_membership, target, actor_user=actor):
            raise OnboardingError("You do not have permission to reset this member's password.", code='hierarchy_violation', status=403)
        if target.user_id == actor.pk:
            raise OnboardingError("Use your own Account Profile to change your own password.", code='self_reset_disallowed', status=400)

        target_user = target.user
        if not actor.is_superuser and is_shared_identity(target_user, tenant):
            raise OnboardingError(
                "This user belongs to multiple workspaces or holds platform privileges. Password resets for shared accounts must be handled via Platform Admin.",
                code='shared_identity_protected',
                status=409,
            )

        try:
            validate_password(new_password, user=target_user)
        except DjangoValidationError as exc:
            raise OnboardingError(" ".join(exc.messages), code='weak_password', status=400) from exc

        target_user.set_password(new_password)
        target_user.save(update_fields=['password'])

        keep_key = request.session.session_key if request and hasattr(request, 'session') and target_user.pk == actor.pk else None
        revoked_count = revoke_user_sessions(target_user, keep_session_key=keep_key)

        TenantAuditLog.objects.create(
            tenant=tenant,
            actor=actor,
            action=AuditLogAction.STAFF_PASSWORD_RESET,
            summary=f"Administratively reset password for {target_user.username}",
            details={
                'target_user_id': target_user.pk,
                'target_username': target_user.username,
                'sessions_revoked': revoked_count,
            },
            ip_address=ip_addr,
        )
        return {
            'user_id': target_user.pk,
            'username': target_user.username,
            'sessions_revoked': revoked_count,
        }


def resolve_recovery_destination(user: User) -> tuple[str | None, str]:
    """
    Resolve safe password-recovery destination for a user without side effects.
    Returns (email_or_None, reason_code):
    - Prioritizes verified real recovery_email over everything else.
    - Blocks synthetic internal identifiers without verified recovery email.
    - Respects explicit unverified UserSecurityProfile records and unverified onboarding records.
    """
    profile = UserSecurityProfile.objects.filter(user=user).first()
    if profile is not None:
        if profile.recovery_email_verified and profile.recovery_email and not is_synthetic_email(profile.recovery_email):
            return profile.recovery_email.strip(), 'verified_recovery_email'
        if profile.email_verified and user.email and not is_synthetic_email(user.email) and not profile.is_synthetic_identifier:
            return user.email.strip(), 'verified_primary_email'
        if user.is_superuser and user.email and not is_synthetic_email(user.email) and not profile.is_synthetic_identifier:
            return user.email.strip(), 'superuser_email'
        return None, 'no_verified_recovery_email'

    # Read-only legacy fallback when no explicit UserSecurityProfile exists yet
    if (
        user.has_usable_password()
        and user.email
        and not is_synthetic_email(user.email)
        and not ClientOnboarding.objects.filter(owner_user=user, email_verified=False).exists()
    ):
        return user.email.strip(), 'legacy_primary_email'
    return None, 'no_verified_recovery_email'


def initiate_recovery_email_change(*, user: User, new_recovery_email: str, request=None) -> dict:
    """
    Allows an authenticated user (Super Admin, Owner/Admin, or staff) to set/change a real
    recovery email address and sends a single-use verification link (RECOVERY_EMAIL_VERIFY).
    Never activates recovery_email until confirmed by token!
    """
    from .email_service import queue_recovery_email_verification

    normalized = normalize_email_safe(new_recovery_email)
    if is_synthetic_email(normalized):
        raise OnboardingError("Recovery email cannot be an internal synthetic address.", code='synthetic_identifier', status=400)

    ip_addr = get_client_ip(request)
    policy = get_policy_config()

    with transaction.atomic():
        profile = UserSecurityProfile.objects.select_for_update().get(user=user) if UserSecurityProfile.objects.filter(user=user).exists() else UserSecurityProfile.get_or_create_for_user(user)
        check_and_record_verification_send(
            email=normalized,
            ip_address=ip_addr,
            user=user,
            purpose=VerificationPurpose.RECOVERY_EMAIL_VERIFY,
            enforce_cooldown=True,
        )
        profile.pending_recovery_email = normalized
        profile.save(update_fields=['pending_recovery_email', 'updated_at'])

        tok = EmailVerificationToken.issue_token(
            user=user,
            intended_email=normalized,
            purpose=VerificationPurpose.RECOVERY_EMAIL_VERIFY,
            minutes=policy['verification_expiry_minutes'],
        )
        email_job = queue_recovery_email_verification(
            request=request,
            token=tok,
            recipient=normalized,
            user=user,
        )
        TenantAuditLog.objects.create(
            tenant=None,
            actor=user,
            action=AuditLogAction.RECOVERY_EMAIL_UPDATED,
            summary=f"Initiated recovery email verification for {user.username}",
            details={'user_id': user.pk, 'pending_recovery_email': normalized},
            ip_address=ip_addr,
        )
        return {
            'pending_recovery_email': normalized,
            'email_job_id': str(email_job.pk) if email_job else None,
        }


def confirm_recovery_email_token(*, raw_token: str, request=None) -> dict:
    if not raw_token:
        raise OnboardingError("Invalid recovery email verification token.", code='invalid_token', status=400)
    digest = EmailVerificationToken.hash_token(raw_token)
    now = timezone.now()
    ip_addr = get_client_ip(request)

    with transaction.atomic():
        token = (
            EmailVerificationToken.objects.select_for_update()
            .filter(token_digest=digest)
            .first()
        )
        if token is None or token.purpose != VerificationPurpose.RECOVERY_EMAIL_VERIFY:
            raise OnboardingError("Invalid or wrong-purpose recovery email token.", code='invalid_token', status=400)
        if token.invalidation_reason:
            raise OnboardingError("This verification link was superseded.", code='superseded', status=410)
        if token.is_used:
            raise OnboardingError("This verification link was already used.", code='already_used', status=410)
        if token.expires_at <= now:
            raise OnboardingError("This verification link has expired.", code='expired', status=410)
        if not token.user_id:
            raise OnboardingError("Verification token has no target account.", code='invalid_token', status=400)

        profile = UserSecurityProfile.get_or_create_for_user(token.user)
        if not profile.pending_recovery_email or profile.pending_recovery_email.lower() != token.intended_email.lower():
            raise OnboardingError("Recovery email no longer matches pending change.", code='email_mismatch', status=410)

        token.is_used = True
        token.used_at = now
        token.save(update_fields=['is_used', 'used_at'])

        profile.recovery_email = profile.pending_recovery_email
        profile.recovery_email_verified = True
        profile.recovery_email_verified_at = now
        profile.pending_recovery_email = ''
        profile.save(update_fields=['recovery_email', 'recovery_email_verified', 'recovery_email_verified_at', 'pending_recovery_email', 'updated_at'])

        TenantAuditLog.objects.create(
            tenant=None,
            actor=token.user,
            action=AuditLogAction.RECOVERY_EMAIL_UPDATED,
            summary=f"Verified recovery email for {token.user.username}",
            details={'user_id': token.user_id, 'recovery_email': profile.recovery_email},
            ip_address=ip_addr,
        )
        return {'user': token.user, 'recovery_email': profile.recovery_email}
