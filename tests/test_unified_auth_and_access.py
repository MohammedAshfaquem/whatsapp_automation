import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta

from apps.tenants.models import (
    Tenant, TenantMembership, TenantRole, PlanTier, TenantSubscription,
    SubscriptionStatus, EmailVerificationToken, UserSecurityProfile,
    TenantFeatureOverride, OverrideChoice, TenantMonthlyUsage,
    TenantAuditLog, AuditLogAction, OnboardingProgress, OnboardingStep
)
from apps.tenants.capabilities import (
    CAPABILITY_REGISTRY, can_access_capability, can_perform_action
)
from apps.tenants.onboarding_views import run_synthetic_assistant_test
from apps.business.models import BusinessProfile
from apps.services.models import Service, PriceType
from apps.knowledge_base.models import FAQ, KnowledgeDocument
from apps.chatbot.models import Customer
from apps.crm.models import Company, Pipeline
from apps.whatsapp.models import WhatsAppConfig, WhatsAppDelivery
from apps.whatsapp.delivery import dispatch

User = get_user_model()


@pytest.fixture
def auth_setup(db):
    # 1. Plans
    basic_plan = PlanTier.objects.create(
        code='basic',
        name='Basic Plan',
        price_display_mode='CONTACT_SALES',
        max_staff=2,
        max_services=5,
        max_contacts=50,
        monthly_message_allowance=100,
        max_documents=5,
        enabled_modules=['shared_inbox', 'demo_scheduling'],
        is_published=True,
        ordering=1
    )
    growth_plan = PlanTier.objects.create(
        code='growth',
        name='Growth Plan',
        price_display_mode='CONTACT_SALES',
        max_staff=5,
        max_services=20,
        max_contacts=500,
        monthly_message_allowance=1000,
        max_documents=25,
        enabled_modules=['shared_inbox', 'contacts_companies', 'deals_pipelines', 'tasks_followups', 'ai_assistant', 'team_management'],
        is_published=True,
        ordering=2
    )

    # 2. Superadmin (Platform Administrator)
    platform_super = User.objects.create_superuser(
        username='platform_super',
        email='super@neorizsolutions.com',
        password='SuperAdminPassword123!'
    )
    UserSecurityProfile.objects.create(user=platform_super, email_verified=True, is_trusted_seed=True)

    # 3. Tenants & Owners
    tenant_a = Tenant.objects.create(
        name='Alpha Agency',
        slug='alpha-agency',
        plan='GROWTH',
        max_staff=5,
        max_services=20,
        is_active=True
    )
    TenantSubscription.objects.create(
        tenant=tenant_a,
        effective_plan=growth_plan,
        status=SubscriptionStatus.ACTIVE
    )

    owner_a = User.objects.create_user(
        username='owner_a',
        email='owner_a@alpha.com',
        password='Password123!'
    )
    UserSecurityProfile.objects.create(user=owner_a, email_verified=True)
    TenantMembership.objects.create(
        tenant=tenant_a,
        user=owner_a,
        role=TenantRole.OWNER,
        is_active=True
    )

    tenant_b = Tenant.objects.create(
        name='Beta Retail',
        slug='beta-retail',
        plan='BASIC',
        max_staff=2,
        max_services=5,
        is_active=True
    )
    TenantSubscription.objects.create(
        tenant=tenant_b,
        effective_plan=basic_plan,
        status=SubscriptionStatus.ACTIVE
    )

    owner_b = User.objects.create_user(
        username='owner_b',
        email='owner_b@beta.com',
        password='Password123!'
    )
    UserSecurityProfile.objects.create(user=owner_b, email_verified=True)
    TenantMembership.objects.create(
        tenant=tenant_b,
        user=owner_b,
        role=TenantRole.OWNER,
        is_active=True
    )

    # 4. Multi-Tenant User (belongs to both Alpha and Beta)
    multi_user = User.objects.create_user(
        username='multi_member',
        email='consultant@shared.com',
        password='Password123!'
    )
    UserSecurityProfile.objects.create(user=multi_user, email_verified=True)
    TenantMembership.objects.create(tenant=tenant_a, user=multi_user, role=TenantRole.STAFF, is_active=True)
    TenantMembership.objects.create(tenant=tenant_b, user=multi_user, role=TenantRole.STAFF, is_active=True)

    # 5. User without Tenant
    stranded_user = User.objects.create_user(
        username='no_tenant_user',
        email='notenant@example.com',
        password='Password123!'
    )
    UserSecurityProfile.objects.create(user=stranded_user, email_verified=True)

    # 6. Unverified User in Tenant A
    unverified_user = User.objects.create_user(
        username='unverified_user',
        email='unverified@alpha.com',
        password='Password123!'
    )
    UserSecurityProfile.objects.create(user=unverified_user, email_verified=False)
    TenantMembership.objects.create(tenant=tenant_a, user=unverified_user, role=TenantRole.STAFF, is_active=True)

    return {
        'basic_plan': basic_plan,
        'growth_plan': growth_plan,
        'platform_super': platform_super,
        'tenant_a': tenant_a,
        'tenant_b': tenant_b,
        'owner_a': owner_a,
        'owner_b': owner_b,
        'multi_user': multi_user,
        'stranded_user': stranded_user,
        'unverified_user': unverified_user,
    }


# =============================================================================
# 1. UNIFIED LOGIN ROUTING & REDIRECT VALIDATION
# =============================================================================

@pytest.mark.django_db
def test_unified_login_superadmin_routes_to_platform(client, auth_setup):
    res = client.post(reverse('login'), {
        'username': 'platform_super',
        'password': 'SuperAdminPassword123!'
    }, follow=False)
    assert res.status_code == 302
    assert res['Location'] == '/app/platform/dashboard'


@pytest.mark.django_db
def test_unified_login_single_tenant_owner_routes_to_dashboard(client, auth_setup):
    res = client.post(reverse('login'), {
        'username': 'owner_a',
        'password': 'Password123!'
    }, follow=False)
    assert res.status_code == 302
    assert res['Location'] == '/app/dashboard'
    # Active tenant session populated
    assert client.session['active_tenant_id'] == auth_setup['tenant_a'].id


@pytest.mark.django_db
def test_unified_login_multi_tenant_routes_to_workspace_selection(client, auth_setup):
    res = client.post(reverse('login'), {
        'username': 'multi_member',
        'password': 'Password123!'
    }, follow=False)
    assert res.status_code == 302
    assert res['Location'] == reverse('tenant-select')


@pytest.mark.django_db
def test_unified_login_user_without_tenant_routes_to_access_pending(client, auth_setup):
    res = client.post(reverse('login'), {
        'username': 'no_tenant_user',
        'password': 'Password123!'
    }, follow=False)
    assert res.status_code == 302
    assert res['Location'] == reverse('access-pending')


@pytest.mark.django_db
def test_unified_login_rejects_open_redirect(client, auth_setup):
    res = client.post(reverse('login') + '?next=https://evil-phishing.com/steal', {
        'username': 'owner_a',
        'password': 'Password123!'
    }, follow=False)
    assert res.status_code == 302
    # Malicious external domain must be ignored and routed to internal dashboard
    assert res['Location'] == '/app/dashboard'


# =============================================================================
# 2. SIGNUP SECURITY & ACCOUNT TAKEOVER PREVENTION
# =============================================================================

@pytest.mark.django_db
def test_signup_rejects_existing_email_without_password_takeover(client, auth_setup):
    # Ensure platform_super password cannot be overwritten
    old_pw_hash = auth_setup['platform_super'].password

    res = client.post(reverse('signup'), {
        'email': 'super@neorizsolutions.com',
        'business_name': 'Hacker Company',
        'full_name': 'Attacker',
        'phone': '+919876543210',
        'plan': auth_setup['basic_plan'].id,
        'password': 'AttackerNewPassword123!',
        'confirm_password': 'AttackerNewPassword123!',
        'terms_accepted': 'on',
    })
    assert res.status_code == 403

    # Verify password hash did not change
    auth_setup['platform_super'].refresh_from_db()
    assert auth_setup['platform_super'].password == old_pw_hash


@pytest.mark.django_db
def test_signup_creates_unverified_security_profile(client, auth_setup):
    """Attempting to POST to signup returns 403 Forbidden per disabled self-service policy."""
    res = client.post(reverse('signup'), {
        'email': 'newclient@example.com',
        'business_name': 'New Horizon Ltd',
        'full_name': 'Sarah Connor',
        'phone': '+919988776655',
        'plan': auth_setup['basic_plan'].id,
        'password': 'SecureClientPassword123!',
        'confirm_password': 'SecureClientPassword123!',
        'terms_accepted': 'on',
    }, follow=False)
    assert res.status_code == 403
    assert not User.objects.filter(email='newclient@example.com').exists()


# =============================================================================
# 3. ATOMIC SINGLE-USE EMAIL VERIFICATION
# =============================================================================

@pytest.mark.django_db
def test_email_verification_atomic_consumption(client, auth_setup):
    user = auth_setup['unverified_user']
    token = EmailVerificationToken.generate_for_user(user)

    # GET alone must NOT consume the verification token
    res_get = client.get(reverse('verify-email', args=[token.token]))
    assert res_get.status_code == 200
    token.refresh_from_db()
    assert token.is_used is False

    # First consumption via explicit POST: valid
    res = client.post(reverse('verify-email', args=[token.token]))
    assert res.status_code in (200, 302)

    sec_profile = UserSecurityProfile.objects.get(user=user)
    assert sec_profile.email_verified is True
    assert sec_profile.email_verified_at is not None

    token.refresh_from_db()
    assert token.is_used is True

    # Replay attempt: must fail
    res2 = client.post(reverse('verify-email', args=[token.token]))
    assert res2.status_code == 410
    assert "already" in res2.content.decode().lower()


# =============================================================================
# 4. EMAIL VERIFICATION ACCESS GATE
# =============================================================================

@pytest.mark.django_db
def test_unverified_user_gate_blocks_protected_urls(client, auth_setup):
    client.force_login(auth_setup['unverified_user'])
    session = client.session
    session['active_tenant_id'] = auth_setup['tenant_a'].id
    session.save()

    # Attempting to access CRM contacts view
    res = client.get(reverse('crm-contact-list'))
    assert res.status_code == 302
    assert res['Location'] == reverse('verification-notice')

    # Allowed setup paths
    res_onboard = client.get(reverse('onboarding-wizard'))
    assert res_onboard.status_code in (200, 302)


# =============================================================================
# 5. AUTHORITATIVE CAPABILITY REGISTRY & PRECEDENCE (INHERIT, ALLOW, DENY)
# =============================================================================

@pytest.mark.django_db
def test_capability_precedence_plan_vs_overrides(auth_setup):
    tenant = auth_setup['tenant_a']  # Growth Plan: includes contacts_companies
    user = auth_setup['owner_a']

    # 1. Inherited from plan: 'contacts' is allowed
    allowed, reason = can_access_capability(user, tenant, 'contacts')
    assert allowed is True
    assert "Granted by plan" in reason

    # 2. Explicit DENY override takes precedence over plan
    TenantFeatureOverride.objects.create(
        tenant=tenant,
        feature_key='contacts',
        override=OverrideChoice.DENY,
        reason='Suspended temporarily by platform admin'
    )
    allowed, reason = can_access_capability(user, tenant, 'contacts')
    assert allowed is False
    assert "Denied by platform administrator override" in reason

    # 3. Explicit ALLOW override grants feature not in plan
    # Basic plan does not have 'ai_assistant'
    tenant_b = auth_setup['tenant_b']
    owner_b = auth_setup['owner_b']
    allowed_b, _ = can_access_capability(owner_b, tenant_b, 'knowledge')
    assert allowed_b is False  # Not in basic plan

    TenantFeatureOverride.objects.create(
        tenant=tenant_b,
        feature_key='knowledge',
        override=OverrideChoice.ALLOW,
        reason='Beta pilot feature granted'
    )
    allowed_b_new, reason_b = can_access_capability(owner_b, tenant_b, 'knowledge')
    assert allowed_b_new is True
    assert "Granted by platform administrator override" in reason_b


@pytest.mark.django_db
def test_platform_capabilities_forbidden_to_tenant_users(auth_setup):
    tenant = auth_setup['tenant_a']
    owner = auth_setup['owner_a']

    # Tenant owner cannot access platform_tenants capability
    allowed, reason = can_access_capability(owner, tenant, 'platform_tenants')
    assert allowed is False
    assert "Platform administration" in reason

    # Platform superadmin in platform mode can access
    superadmin = auth_setup['platform_super']
    allowed_super, _ = can_access_capability(superadmin, None, 'platform_tenants')
    assert allowed_super is True


# =============================================================================
# 6. PLATFORM INSPECTION MODE & AUDIT TRAIL
# =============================================================================

@pytest.mark.django_db
def test_platform_inspection_mode_lifecycle(client, auth_setup):
    superadmin = auth_setup['platform_super']
    tenant = auth_setup['tenant_a']

    client.force_login(superadmin)

    # 1. Enter Inspection Mode
    res_inspect = client.get(reverse('platform-inspect-tenant', args=[tenant.id]), follow=True)
    assert res_inspect.status_code == 200
    assert client.session.get('inspecting_tenant_id') == tenant.id
    assert client.session.get('active_tenant_id') == tenant.id

    # Audit log recorded
    log = TenantAuditLog.objects.filter(tenant=tenant, action=AuditLogAction.TENANT_INSPECTED).first()
    assert log is not None
    assert superadmin.username in log.summary

    # The SPA renders its inspection banner from authoritative bootstrap state.
    assert res_inspect.request['PATH_INFO'] == '/app/dashboard'
    bootstrap = client.get(reverse('api-bootstrap'))
    assert bootstrap.status_code == 200
    assert bootstrap.json()['is_inspecting'] is True
    assert bootstrap.json()['inspected_tenant']['id'] == tenant.id
    assert bootstrap.json()['tenant']['id'] == tenant.id

    # 2. Exit Inspection Mode
    res_exit = client.get(reverse('platform-exit-inspection'), follow=True)
    assert res_exit.status_code == 200
    assert 'inspecting_tenant_id' not in client.session
    assert 'active_tenant_id' not in client.session
    bootstrap = client.get(reverse('api-bootstrap'))
    assert bootstrap.status_code == 200
    assert bootstrap.json()['is_inspecting'] is False
    assert bootstrap.json()['inspected_tenant'] is None


# =============================================================================
# 7. CONCURRENCY-SAFE PLAN LIMIT ENFORCEMENT
# =============================================================================

@pytest.mark.django_db
def test_seat_limit_enforcement(auth_setup):
    tenant_fresh = Tenant.objects.create(name='Fresh Agency', slug='fresh-agency', max_staff=2, is_active=True)
    TenantSubscription.objects.create(tenant=tenant_fresh, effective_plan=auth_setup['basic_plan'], status=SubscriptionStatus.ACTIVE)
    assert tenant_fresh.effective_max_staff == 2
    assert tenant_fresh.can_add_staff() is True

    # Add 1 staff (total 1)
    u1 = User.objects.create_user(username='u1', email='u1@b.com')
    TenantMembership.objects.create(tenant=tenant_fresh, user=u1, role=TenantRole.STAFF, is_active=True)
    assert tenant_fresh.can_add_staff() is True

    # Add 2nd staff (total 2)
    u2 = User.objects.create_user(username='u2', email='u2@b.com')
    TenantMembership.objects.create(tenant=tenant_fresh, user=u2, role=TenantRole.STAFF, is_active=True)
    assert tenant_fresh.can_add_staff() is False


@pytest.mark.django_db
def test_contact_limit_enforcement(auth_setup):
    tenant = auth_setup['tenant_b']  # Max 50 contacts
    tenant.subscription.effective_plan.max_contacts = 2
    tenant.subscription.effective_plan.save()

    assert tenant.effective_max_contacts == 2
    assert tenant.can_add_contact() is True

    Customer.objects.create(tenant=tenant, phone_number='+919000000001', name='C1')
    Customer.objects.create(tenant=tenant, phone_number='+919000000002', name='C2')

    assert tenant.can_add_contact() is False


@pytest.mark.django_db
def test_monthly_message_allowance_enforcement(auth_setup):
    tenant = auth_setup['tenant_b']
    tenant.subscription.effective_plan.monthly_message_allowance = 2
    tenant.subscription.effective_plan.save()

    assert tenant.effective_monthly_message_allowance == 2
    assert tenant.can_send_monthly_message() is True

    # Increment 2 usage
    tenant.increment_monthly_message_usage(sent=True)
    tenant.increment_monthly_message_usage(sent=True)

    assert tenant.can_send_monthly_message() is False

    # Attempting to dispatch WhatsApp message when quota exceeded marks it BLOCKED
    delivery = WhatsAppDelivery.objects.create(
        dedup_key='test-monthly-limit-1',
        recipient_phone='+919999999999',
        payload={'text': 'Hello over quota'},
        tenant=tenant,
        status='PENDING'
    )
    result = dispatch(delivery.id)
    assert result is False

    delivery.refresh_from_db()
    assert delivery.status == 'BLOCKED'
    assert "allowance" in delivery.last_error.lower()


# =============================================================================
# 8. BULK PLAN MIGRATION WITH PREVIEW
# =============================================================================

@pytest.mark.django_db
def test_bulk_plan_migration_flow(client, auth_setup):
    superadmin = auth_setup['platform_super']
    tenant_b = auth_setup['tenant_b']
    growth_plan = auth_setup['growth_plan']

    client.force_login(superadmin)

    # 1. Preview request (confirm not sent)
    res_preview = client.post(reverse('platform-access-matrix'), {
        'action': 'bulk_assign_plan',
        'target_plan_code': growth_plan.code,
        'tenant_ids': [tenant_b.id],
    })
    assert res_preview.status_code == 200
    assert "Bulk Plan Assignment Preview" in res_preview.content.decode()

    # 2. Confirmed bulk execution
    res_exec = client.post(reverse('platform-access-matrix'), {
        'action': 'bulk_assign_plan',
        'target_plan_code': growth_plan.code,
        'tenant_ids': [tenant_b.id],
        'confirm': 'yes',
    }, follow=True)
    assert res_exec.status_code == 200

    tenant_b.refresh_from_db()
    tenant_b.subscription.refresh_from_db()
    assert tenant_b.subscription.effective_plan == growth_plan
    assert tenant_b.max_staff == growth_plan.max_staff
    assert tenant_b.max_services == growth_plan.max_services


# =============================================================================
# 9. REAL SYNTHETIC ASSISTANT SIMULATION
# =============================================================================

@pytest.mark.django_db
def test_synthetic_assistant_simulation(auth_setup):
    tenant = auth_setup['tenant_a']

    # Seed business profile and service
    BusinessProfile.objects.create(
        tenant=tenant,
        shop_name='Alpha Tech'
    )
    Service.objects.create(
        tenant=tenant,
        name='Cloud Migration',
        description='Expert AWS and GCP cloud migrations',
        price_type=PriceType.INSPECTION_REQUIRED,
        is_active=True
    )
    FAQ.objects.create(
        tenant=tenant,
        question='What are your office hours?',
        answer='We operate Mon-Fri 9am to 6pm IST.',
        is_active=True
    )

    # Run synthetic assistant query
    sim_result = run_synthetic_assistant_test(tenant, "What services do you provide?")
    assert sim_result['success'] is True
    assert "Cloud Migration" in sim_result['response']
    assert any("Cloud Migration" in g for g in sim_result['grounding'])

    # Run FAQ query
    sim_result_faq = run_synthetic_assistant_test(tenant, "What are your office hours?")
    assert sim_result_faq['success'] is True
    assert "Alpha Tech" in sim_result_faq['response']
