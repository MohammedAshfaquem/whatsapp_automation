import hashlib
from django.conf import settings
from django.db import migrations
from django.utils import timezone


def reconcile_legacy_tokens_and_accounts(apps, schema_editor):
    """
    Separate data migration after DDL commits cleanly (prevents PostgreSQL pending
    trigger event conflicts with index creation). Safely migrates legacy plaintext
    tokens to SHA-256 digests and reconciles existing user security profiles.
    """
    AccountActivationToken = apps.get_model('tenants', 'AccountActivationToken')
    EmailVerificationToken = apps.get_model('tenants', 'EmailVerificationToken')
    UserSecurityProfile = apps.get_model('tenants', 'UserSecurityProfile')
    Tenant = apps.get_model('tenants', 'Tenant')
    TenantMembership = apps.get_model('tenants', 'TenantMembership')
    TenantSubscription = apps.get_model('tenants', 'TenantSubscription')
    ClientOnboarding = apps.get_model('tenants', 'ClientOnboarding')
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))

    for tok in AccountActivationToken.objects.all().iterator():
        changed = []
        if not tok.purpose:
            tok.purpose = 'ACCOUNT_ACTIVATION'
            changed.append('purpose')
        if tok.legacy_token:
            tok.token_digest = hashlib.sha256(tok.legacy_token.encode('utf-8')).hexdigest()
            tok.legacy_token = None
            changed.extend(['token_digest', 'legacy_token'])
        if changed:
            tok.save(update_fields=changed)

    for tok in EmailVerificationToken.objects.select_related('user').all().iterator():
        changed = []
        if not tok.purpose:
            tok.purpose = 'EMAIL_VERIFY'
            changed.append('purpose')
        if not tok.intended_email and tok.user_id:
            tok.intended_email = (tok.user.email or '').strip()
            changed.append('intended_email')
        if tok.legacy_token:
            tok.token_digest = hashlib.sha256(tok.legacy_token.encode('utf-8')).hexdigest()
            tok.legacy_token = None
            changed.extend(['token_digest', 'legacy_token'])
        if changed:
            tok.save(update_fields=changed)

    now = timezone.now()
    synthetic_exact = {'risal@neorizsolutions.com'}
    for user in User.objects.all().iterator():
        raw_email = (user.email or '').strip().lower()
        is_synth = (
            raw_email in synthetic_exact
            or raw_email.endswith('.internal')
            or raw_email.endswith('.local')
            or raw_email == ''
        )
        profile = UserSecurityProfile.objects.filter(user_id=user.pk).first()
        if profile is None:
            is_priv = bool(user.is_superuser or user.is_staff)
            verified = bool(is_priv and not is_synth)
            UserSecurityProfile.objects.create(
                user_id=user.pk,
                email_verified=verified,
                email_verified_at=now if verified else None,
                is_trusted_seed=is_priv,
                internal_identifier=raw_email if is_synth and raw_email else None,
                is_synthetic_identifier=bool(is_synth and raw_email),
                skip_mailbox_gate=bool(is_synth),
                recovery_email=raw_email if (verified and raw_email) else '',
                recovery_email_verified=bool(verified and raw_email),
                recovery_email_verified_at=now if (verified and raw_email) else None,
            )
        else:
            changed = []
            if is_synth and raw_email:
                if not profile.internal_identifier:
                    profile.internal_identifier = raw_email
                    changed.append('internal_identifier')
                if not profile.is_synthetic_identifier:
                    profile.is_synthetic_identifier = True
                    changed.append('is_synthetic_identifier')
                if not profile.skip_mailbox_gate:
                    profile.skip_mailbox_gate = True
                    changed.append('skip_mailbox_gate')
                if profile.recovery_email.lower() in synthetic_exact:
                    profile.recovery_email = ''
                    profile.recovery_email_verified = False
                    profile.recovery_email_verified_at = None
                    changed.extend(['recovery_email', 'recovery_email_verified', 'recovery_email_verified_at'])
            elif profile.email_verified and raw_email and not profile.recovery_email:
                profile.recovery_email = raw_email
                profile.recovery_email_verified = True
                profile.recovery_email_verified_at = profile.email_verified_at or now
                changed.extend(['recovery_email', 'recovery_email_verified', 'recovery_email_verified_at'])
            if changed:
                profile.save(update_fields=changed)

    for tenant in Tenant.objects.filter(is_active=True).iterator():
        if ClientOnboarding.objects.filter(tenant_id=tenant.pk).exists():
            continue
        owner_membership = (
            TenantMembership.objects.filter(tenant_id=tenant.pk, is_active=True, role='OWNER')
            .select_related('user')
            .first()
        )
        if not owner_membership:
            continue
        owner = owner_membership.user
        profile = UserSecurityProfile.objects.filter(user_id=owner.pk).first()
        owner_verified = bool(profile and profile.email_verified)
        pw_set = bool(owner.password and not owner.password.startswith('!'))
        sub = TenantSubscription.objects.filter(tenant_id=tenant.pk).first()
        assigned_plan_id = sub.effective_plan_id if sub else None
        requested_plan_id = sub.requested_plan_id if sub else None
        ClientOnboarding.objects.create(
            source='SUPERADMIN_INVITE',
            business_name=tenant.name,
            owner_full_name=((owner.first_name + ' ' + owner.last_name).strip() or owner.username)[:150],
            owner_email=(owner.email or tenant.contact_email or f'{owner.username}@legacy.local'),
            desired_username=owner.username,
            whatsapp_number=(tenant.whatsapp_number or '')[:20],
            requested_plan_id=requested_plan_id,
            assigned_plan_id=assigned_plan_id,
            terms_accepted=True,
            terms_accepted_at=tenant.created_at,
            registration_status='ACTIVE' if (owner_verified and pw_set) else ('APPROVED' if pw_set else 'SUBMITTED'),
            email_verified=owner_verified,
            email_verified_at=profile.email_verified_at if owner_verified else None,
            approval_status='APPROVED',
            approved_at=sub.approved_at if sub and sub.approved_at else tenant.created_at,
            password_set=pw_set,
            password_set_at=tenant.created_at if pw_set else None,
            tenant_id=tenant.pk,
            owner_user_id=owner.pk,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('tenants', '0012_remove_accountactivationtoken_token_and_more'),
    ]

    operations = [
        migrations.RunPython(reconcile_legacy_tokens_and_accounts, migrations.RunPython.noop),
    ]
