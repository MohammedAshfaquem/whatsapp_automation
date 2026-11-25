"""
Comprehensive Release 1 Test Suite:
- Entry Point A (Public Registration) & Entry Point B (Super Admin Invite)
- 30-min Expiring Email Verification (digest-only, scanner-safe GET+POST, throttles, email change)
- Approval & Early Approval Gating + Separate Owner Password Setup + Email Outbox Failure Handling
- Direct Client Team Staff Administration, Role Hierarchy, Shared-Account Protection, Session Revocation
- Synthetic Internal Identifier Separation & Verified Recovery Email Routing
- Meta Setup Gate + 8-Item Client Setup Checklist
"""
from datetime import timedelta
import json
import pytest
from django.contrib.auth.models import User
from django.contrib.sessions.models import Session
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.tenants.email_service import unseal
from apps.tenants.models import (
    AccountActivationToken,
    AuditLogAction,
    ClientOnboarding,
    EmailVerificationToken,
    LegalDocument,
    LegalDocumentStatus,
    LegalDocumentType,
    OnboardingApprovalStatus,
    OnboardingRegistrationStatus,
    OnboardingSource,
    PlanTier,
    PlatformServiceConfig,
    SubscriptionStatus,
    Tenant,
    TenantAuditLog,
    TenantMembership,
    TenantRole,
    TenantSubscription,
    TransactionalEmail,
    UserSecurityProfile,
    VerificationPurpose,
)
from apps.tenants.onboarding_service import resolve_recovery_destination

pytestmark = pytest.mark.django_db


@pytest.fixture
def release1_env():
    basic = PlanTier.objects.create(
        code='basic',
        name='Basic',
        monthly_price=999,
        max_staff=3,
        max_services=10,
        max_contacts=500,
        is_published=True,
        ordering=1,
        enabled_modules=['shared_inbox', 'contacts_companies', 'team_management', 'settings'],
    )
    growth = PlanTier.objects.create(
        code='growth',
        name='Growth',
        monthly_price=2499,
        max_staff=10,
        max_services=50,
        max_contacts=5000,
        is_published=True,
        ordering=2,
        enabled_modules=['shared_inbox', 'contacts_companies', 'team_management', 'settings', 'reports'],
    )
    LegalDocument.objects.create(
        doc_type=LegalDocumentType.TERMS,
        version='1.0',
        title='Terms of Service',
        content='Terms',
        status=LegalDocumentStatus.PUBLISHED,
    )
    superadmin = User.objects.create_superuser('r1_super', 'ops@neorizsolutions.com', 'SuperStrong123!')
    UserSecurityProfile.objects.create(
        user=superadmin,
        email_verified=True,
        recovery_email='ops@neorizsolutions.com',
        recovery_email_verified=True,
        is_trusted_seed=True,
    )
    return {'basic': basic, 'growth': growth, 'superadmin': superadmin}


# ---------------------------------------------------------------------------
# 1. Public Registration, Email Verification & Approval Flow
# ---------------------------------------------------------------------------

def test_public_registration_normalizes_preserves_dots_plus_and_scanner_safe_verify(release1_env):
    client = Client()
    # GET /request-access/ has no password fields
    form_page = client.get('/request-access/')
    assert form_page.status_code == 200
    assert b'name="password"' not in form_page.content

    before_users = User.objects.count()
    before_tenants = Tenant.objects.count()

    resp = client.post('/request-access/', {
        'business_name': 'GreenLeaf Dental',
        'owner_full_name': 'Meera Nair',
        'owner_email': '  Meera.Nair+owner@Example.COM  ',
        'desired_username': 'meera_dental',
        'whatsapp_number': '+919876543210',
        'requested_plan': release1_env['basic'].pk,
        'terms_accepted': 'on',
        'marketing_consent': '',
    })
    assert resp.status_code == 302
    assert '/registration/check-email/' in resp.url

    # No User or Tenant created on registration
    assert User.objects.count() == before_users
    assert Tenant.objects.count() == before_tenants

    onboarding = ClientOnboarding.objects.get(business_name='GreenLeaf Dental')
    assert onboarding.source == OnboardingSource.SELF_REGISTRATION
    assert onboarding.owner_email == 'Meera.Nair+owner@example.com'  # preserves dots and +tag; domain lowercased
    assert onboarding.email_verified is False
    assert onboarding.approval_status == OnboardingApprovalStatus.PENDING
    assert onboarding.marketing_consent is False

    # Verification token stored ONLY as SHA-256 digest in DB; 30-min expiry
    tok = EmailVerificationToken.objects.get(onboarding=onboarding, purpose=VerificationPurpose.EMAIL_VERIFY)
    assert tok.legacy_token is None
    assert len(tok.token_digest) == 64
    assert 25 <= (tok.expires_at - tok.created_at).total_seconds() / 60 <= 31

    # Outbox job queued with encrypted payload containing verification URL
    email_job = TransactionalEmail.objects.get(onboarding=onboarding, purpose='VERIFICATION')
    assert email_job.recipient == 'Meera.Nair+owner@example.com'
    verify_url = unseal(email_job.encrypted_payload)['url']
    verify_path = '/' + verify_url.split('://', 1)[1].split('/', 1)[1]

    # Scanner-safe GET shows confirmation without consuming token
    get_res = client.get(verify_path)
    assert get_res.status_code == 200
    assert 'no-store' in get_res['Cache-Control']
    assert b'workspace-navigation' not in get_res.content
    tok.refresh_from_db()
    onboarding.refresh_from_db()
    assert not tok.is_used and not onboarding.email_verified

    # Explicit POST confirms verification, keeps approval/subscription untouched
    post_res = client.post(verify_path)
    assert post_res.status_code == 200
    assert b'awaiting platform approval' in post_res.content.lower()
    onboarding.refresh_from_db()
    tok.refresh_from_db()
    assert tok.is_used is True
    assert onboarding.email_verified is True
    assert onboarding.approval_status == OnboardingApprovalStatus.PENDING
    assert onboarding.tenant is None
    assert onboarding.owner_user is None

    # Replay attempt fails
    assert client.post(verify_path).status_code == 410


def test_wrong_purpose_expired_and_email_change_invalidation(release1_env):
    client = Client()
    client.post('/request-access/', {
        'business_name': 'Lotus Travels',
        'owner_full_name': 'Kiran Rao',
        'owner_email': 'kiran@lotus-travels.com',
        'desired_username': 'kiran_lotus',
        'terms_accepted': 'on',
    })
    onboarding = ClientOnboarding.objects.get(business_name='Lotus Travels')
    first_job = TransactionalEmail.objects.filter(onboarding=onboarding, purpose='VERIFICATION').latest('created_at')
    first_url = unseal(first_job.encrypted_payload)['url']
    first_path = '/' + first_url.split('://', 1)[1].split('/', 1)[1]

    # Change email from check-email session invalidates old link
    change_res = client.post('/registration/check-email/', {
        'action': 'change_email',
        'new_email': 'kiran.correct@lotus-travels.com',
    })
    assert change_res.status_code == 200
    onboarding.refresh_from_db()
    assert onboarding.owner_email == 'kiran.correct@lotus-travels.com'
    assert client.post(first_path).status_code == 410

    # Expired token fails cleanly
    tok2 = EmailVerificationToken.objects.filter(onboarding=onboarding, is_used=False).first()
    tok2.expires_at = timezone.now() - timedelta(minutes=1)
    tok2.save(update_fields=['expires_at'])
    second_job = TransactionalEmail.objects.filter(onboarding=onboarding, verification_token=tok2).first()
    second_path = '/' + unseal(second_job.encrypted_payload)['url'].split('://', 1)[1].split('/', 1)[1]
    assert client.post(second_path).status_code == 410

    # Recovery token cannot be accepted on /verify-email/
    rec_tok = EmailVerificationToken.issue_token(
        user=release1_env['superadmin'],
        intended_email='ops@neorizsolutions.com',
        purpose=VerificationPurpose.RECOVERY_EMAIL_VERIFY,
        minutes=30,
    )
    assert client.get(f'/verify-email/{rec_tok.token}/').status_code == 400
    assert client.post(f'/verify-email/{rec_tok.token}/').status_code == 400


def test_verification_resend_cooldown_hourly_email_and_ip_throttles(release1_env):
    client = Client()
    client.post('/request-access/', {
        'business_name': 'Rate Limit Studio',
        'owner_full_name': 'Dev Patel',
        'owner_email': 'dev@ratelimit-studio.com',
        'desired_username': 'dev_rate',
        'terms_accepted': 'on',
    })
    # Immediate resend hits 60s cooldown -> 429
    r_cool = client.post('/registration/check-email/', {'action': 'resend'})
    assert r_cool.status_code == 429

    # Backdate previous tokens past cooldown to test 5/hr per-email cap
    onboarding = ClientOnboarding.objects.get(business_name='Rate Limit Studio')
    for i in range(4):
        EmailVerificationToken.objects.filter(onboarding=onboarding).update(
            created_at=timezone.now() - timedelta(seconds=120)
        )
        r_ok = client.post('/registration/check-email/', {'action': 'resend'})
        assert r_ok.status_code == 200

    # 6th attempt within 1 hour hits hourly email cap -> 429 even past 60s cooldown
    EmailVerificationToken.objects.filter(onboarding=onboarding).update(
        created_at=timezone.now() - timedelta(seconds=120)
    )
    r_hour = client.post('/registration/check-email/', {'action': 'resend'})
    assert r_hour.status_code == 429


def test_existing_account_non_takeover_and_early_approval_gating(release1_env):
    existing = User.objects.create_user('existing_owner', 'already@taken-biz.com', 'StrongPass987!')
    client = Client()

    # Registering with existing email must NOT mutate user or error-leak
    r = client.post('/request-access/', {
        'business_name': 'Impostor Biz',
        'owner_full_name': 'Attacker',
        'owner_email': 'already@taken-biz.com',
        'desired_username': 'impostor_user',
        'terms_accepted': 'on',
    })
    assert r.status_code == 302
    assert '/registration/check-email/' in r.url
    existing.refresh_from_db()
    assert existing.check_password('StrongPass987!')
    assert not ClientOnboarding.objects.filter(business_name='Impostor Biz').exists()

    # Register clean client & test EARLY APPROVAL before email verification
    client.post('/request-access/', {
        'business_name': 'Early Approved Co',
        'owner_full_name': 'Sana Ali',
        'owner_email': 'sana@early-co.com',
        'desired_username': 'sana_early',
        'terms_accepted': 'on',
    })
    onboarding = ClientOnboarding.objects.get(business_name='Early Approved Co')

    admin_c = Client()
    admin_c.force_login(release1_env['superadmin'])
    app_res = admin_c.post(
        f'/api/platform/onboarding/{onboarding.pk}/approve/',
        data=json.dumps({'plan_code': 'growth', 'whatsapp_number': '+919800001122', 'decision_reason': 'Priority approved'}),
        content_type='application/json',
    )
    assert app_res.status_code == 200
    onboarding.refresh_from_db()
    assert onboarding.approval_status == OnboardingApprovalStatus.APPROVED
    assert onboarding.email_verified is False
    # No activation token issued yet because email isn't verified!
    assert not AccountActivationToken.objects.filter(user=onboarding.owner_user).exists()
    assert admin_c.post(f'/api/platform/onboarding/{onboarding.pk}/resend-activation/', data='{}', content_type='application/json').status_code == 409
    assert admin_c.post(f'/api/platform/tenants/{onboarding.tenant_id}/activation/').status_code == 409

    # Owner clicks verification link AFTER early approval -> now activation token IS issued
    v_job = TransactionalEmail.objects.filter(onboarding=onboarding, purpose='VERIFICATION').latest('created_at')
    v_path = '/' + unseal(v_job.encrypted_payload)['url'].split('://', 1)[1].split('/', 1)[1]
    verify_post = Client().post(v_path)
    assert verify_post.status_code == 200
    assert AccountActivationToken.objects.filter(user=onboarding.owner_user, is_used=False).exists()

    # Owner activates password via single-use /activate/<token>/
    a_job = TransactionalEmail.objects.filter(onboarding=onboarding, purpose='ACTIVATION').latest('created_at')
    a_path = '/' + unseal(a_job.encrypted_payload)['url'].split('://', 1)[1].split('/', 1)[1]
    owner_c = Client()
    act_res = owner_c.post(a_path, {'password': 'BrandNewOwnerPass99!', 'confirm_password': 'BrandNewOwnerPass99!'})
    assert act_res.status_code == 302
    onboarding.refresh_from_db()
    assert onboarding.password_set is True
    assert onboarding.registration_status == OnboardingRegistrationStatus.ACTIVE

    # Setup gate: Inbox blocked before Meta verified, Onboarding Checklist allowed!
    assert owner_c.get('/api/crm/overview/').status_code == 403
    chk = owner_c.get('/api/onboarding/status/')
    assert chk.status_code == 200
    items = {i['key']: i['completed'] for i in chk.json()['checklist']['items']}
    assert items['email_verified'] is True
    assert items['password_set'] is True
    assert items['plan_active'] is True
    assert items['whatsapp_meta_configured'] is False


def test_entry_point_b_superadmin_invite_requires_verification_before_password(release1_env):
    admin_c = Client()
    admin_c.force_login(release1_env['superadmin'])

    r = admin_c.post(
        '/api/platform/onboarding/invite/',
        data=json.dumps({
            'business_name': 'Invited Enterprise',
            'owner_full_name': 'Vikram Verma',
            'owner_email': 'vikram@invited-ent.com',
            'desired_username': 'vikram_ent',
            'plan_code': 'growth',
            'whatsapp_number': '+919900112233',
        }),
        content_type='application/json',
    )
    assert r.status_code == 201
    data = r.json()['onboarding']
    assert 'token' not in json.dumps(r.json())
    assert data['approval_status'] == 'APPROVED'
    assert data['email_verified'] is False
    assert data['password_set'] is False
    # Verification email queued first, no activation token until verified
    onboarding = ClientOnboarding.objects.get(pk=data['id'])
    assert TransactionalEmail.objects.filter(onboarding=onboarding, purpose='VERIFICATION').exists()
    assert not AccountActivationToken.objects.filter(user=onboarding.owner_user).exists()


def test_reject_onboarding_and_outbox_failure_visibility(release1_env):
    client = Client()
    client.post('/request-access/', {
        'business_name': 'Rejected Shop',
        'owner_full_name': 'Bad Actor',
        'owner_email': 'bad@rejected-shop.com',
        'desired_username': 'bad_shop',
        'terms_accepted': 'on',
    })
    onboarding = ClientOnboarding.objects.get(business_name='Rejected Shop')
    TransactionalEmail.objects.filter(onboarding=onboarding).update(status='FAILED', last_error='550 Mailbox unavailable')

    admin_c = Client()
    admin_c.force_login(release1_env['superadmin'])
    listing = admin_c.get('/api/platform/onboarding/').json()['onboardings']
    row = next(x for x in listing if x['id'] == str(onboarding.pk))
    assert row['email_delivery']['status'] == 'FAILED'

    rej = admin_c.post(
        f'/api/platform/onboarding/{onboarding.pk}/reject/',
        data=json.dumps({'reason': 'Unverified business details'}),
        content_type='application/json',
    )
    assert rej.status_code == 200
    assert rej.json()['onboarding']['approval_status'] == 'REJECTED'
    assert EmailVerificationToken.objects.filter(onboarding=onboarding, is_used=False).count() == 0


# ---------------------------------------------------------------------------
# 2. Direct Team Staff Admin, Hierarchy, Shared Accounts, Session Revocation & Recovery
# ---------------------------------------------------------------------------

def test_direct_staff_creation_hierarchy_session_revocation_and_shared_protection(release1_env):
    t1 = Tenant.objects.create(name='Alpha Client', slug='alpha-client', max_staff=3, is_active=True, requires_meta_setup=False)
    t2 = Tenant.objects.create(name='Beta Client', slug='beta-client', max_staff=3, is_active=True, requires_meta_setup=False)
    for t in (t1, t2):
        TenantSubscription.objects.create(tenant=t, effective_plan=release1_env['basic'], status=SubscriptionStatus.ACTIVE)

    owner1 = User.objects.create_user('alpha_owner', 'owner@alpha-co.com', 'OwnerStrong123!')
    UserSecurityProfile.objects.create(user=owner1, email_verified=True, recovery_email='owner@alpha-co.com', recovery_email_verified=True)
    TenantMembership.objects.create(tenant=t1, user=owner1, role=TenantRole.OWNER, is_active=True)

    c_owner = Client()
    c_owner.force_login(owner1)

    # Owner creates Admin & synthetic-ID Staff without needing mailbox verification
    r_adm = c_owner.post('/api/team/members/', data=json.dumps({
        'username': 'alpha_admin',
        'full_name': 'Alpha Admin',
        'role': 'ADMIN',
        'password': 'AdminStrong999!',
        'contact_email': 'admin@alpha-co.com',
    }), content_type='application/json')
    assert r_adm.status_code == 201
    admin_m_id = r_adm.json()['member']['id']

    r_staff = c_owner.post('/api/team/members/', data=json.dumps({
        'username': 'desk_staff',
        'full_name': 'Desk Agent',
        'role': 'STAFF',
        'password': 'StaffStrong999!',
        'synthetic_identifier': 'risal@neorizsolutions.com',
    }), content_type='application/json')
    assert r_staff.status_code == 201
    staff_m_id = r_staff.json()['member']['id']
    assert r_staff.json()['member']['is_synthetic_identifier'] is True
    assert r_staff.json()['member']['skip_mailbox_gate'] is True

    # Seat limit enforced (3 seats: owner + admin + staff = 3/3)
    r_over = c_owner.post('/api/team/members/', data=json.dumps({
        'username': 'extra_staff',
        'role': 'STAFF',
        'password': 'ExtraStrong999!',
    }), content_type='application/json')
    assert r_over.status_code == 400

    # Staff can sign in directly via internal synthetic identifier and bypass mailbox gate!
    c_staff = Client()
    login_res = c_staff.post('/login/', {'username': 'risal@neorizsolutions.com', 'password': 'StaffStrong999!'})
    assert login_res.status_code == 302
    assert c_staff.get('/api/crm/contacts/').status_code == 200  # permitted operational view
    assert c_staff.get('/api/team/').status_code == 403  # team management requires ADMIN+
    assert c_staff.post('/api/team/members/', data='{}', content_type='application/json').status_code == 403

    # Self-service recovery MUST NOT send reset mail for synthetic identifier without verified recovery_email
    Email_count_before = TransactionalEmail.objects.count()
    c_staff.post('/password-reset/', {'email': 'risal@neorizsolutions.com'})
    assert TransactionalEmail.objects.count() == Email_count_before

    # Staff configures & verifies a real recovery email -> now recovery routes ONLY there
    rec_api = c_staff.post('/api/auth/recovery-email/', data=json.dumps({'recovery_email': 'real.personal@alpha-co.com'}), content_type='application/json')
    assert rec_api.status_code == 200
    rec_job = TransactionalEmail.objects.get(pk=rec_api.json()['email_job_id'])
    rec_path = '/' + unseal(rec_job.encrypted_payload)['url'].split('://', 1)[1].split('/', 1)[1]
    assert Client().get(rec_path).status_code == 200  # GET non-consuming
    assert Client().post(rec_path).status_code == 200
    staff_user = User.objects.get(username='desk_staff')
    dest, _ = resolve_recovery_destination(staff_user)
    assert dest == 'real.personal@alpha-co.com'

    # Hierarchy: ADMIN cannot create/edit/reset another ADMIN or OWNER
    admin_user = User.objects.get(username='alpha_admin')
    c_adm = Client()
    c_adm.force_login(admin_user)
    assert c_adm.post('/api/team/members/', data=json.dumps({
        'username': 'bad_admin', 'role': 'ADMIN', 'password': 'Password987!'
    }), content_type='application/json').status_code == 403
    assert c_adm.post(f'/api/team/members/{TenantMembership.objects.get(tenant=t1, user=owner1).pk}/reset-password/', data=json.dumps({
        'new_password': 'HackOwnerPassword9!'
    }), content_type='application/json').status_code == 403

    # Administrative password reset WITHOUT old password revokes staff's active session & hides secret from audit logs
    reset_res = c_owner.post(f'/api/team/members/{staff_m_id}/reset-password/', data=json.dumps({
        'new_password': 'BrandNewStaffPassword123!',
        'confirm_password': 'BrandNewStaffPassword123!',
    }), content_type='application/json')
    assert reset_res.status_code == 200
    assert reset_res.json()['sessions_revoked'] >= 1
    assert c_staff.get('/api/crm/contacts/').status_code == 401  # revoked session!

    audit = TenantAuditLog.objects.filter(tenant=t1, action=AuditLogAction.STAFF_PASSWORD_RESET).latest('created_at')
    assert 'BrandNewStaffPassword123!' not in json.dumps(audit.details)
    assert 'BrandNewStaffPassword123!' not in audit.summary

    # Shared-account protection: if staff also belongs to t2, t1 owner cannot globally rename or reset password!
    TenantMembership.objects.create(tenant=t2, user=staff_user, role=TenantRole.STAFF, is_active=True)
    assert c_owner.patch(f'/api/team/members/{staff_m_id}/', data=json.dumps({'username': 'hijack_name'}), content_type='application/json').status_code == 409
    assert c_owner.post(f'/api/team/members/{staff_m_id}/reset-password/', data=json.dumps({'new_password': 'SharedHijackPassword9!'}), content_type='application/json').status_code == 409
