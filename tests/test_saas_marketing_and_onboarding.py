import pytest
from django.urls import reverse
from django.contrib.auth import get_user_model
from django.utils import timezone
from apps.tenants.models import (
    Tenant, TenantMembership, TenantRole, PlanTier, TenantSubscription,
    SubscriptionStatus, EmailVerificationToken, LegalDocument, LegalDocumentType,
    LegalAcceptance, OnboardingProgress, OnboardingStep, DemoRequest
)
from apps.tenants.modules import MODULE_CATALOG, ModuleStatus
from apps.business.models import BusinessProfile
from apps.services.models import Service, PriceType
from apps.crm.models import Pipeline, DealStage, Deal, Activity
from apps.chatbot.models import Customer
from apps.whatsapp.models import WhatsAppConfig, WhatsAppDelivery

User = get_user_model()


@pytest.fixture
def basic_setup(db):
    # Ensure Neoriz Solutions tenant exists
    neoriz, _ = Tenant.objects.get_or_create(
        slug='neoriz-solutions',
        defaults={'name': 'Neoriz Solutions', 'plan': 'ENTERPRISE', 'is_active': True}
    )
    admin_user = User.objects.create_user(
        username='neoriz_admin',
        email='admin@neorizsolutions.com',
        password='StrongPassword123!',
        is_staff=True
    )
    TenantMembership.objects.get_or_create(
        tenant=neoriz,
        user=admin_user,
        defaults={'role': TenantRole.OWNER, 'is_active': True}
    )
    pipeline, _ = Pipeline.objects.get_or_create(
        tenant=neoriz,
        name='Sales Pipeline',
        defaults={'is_default': True}
    )
    stage, _ = DealStage.objects.get_or_create(
        pipeline=pipeline,
        name='Qualified',
        defaults={'order': 1, 'probability': 30}
    )

    # Ensure PlanTiers exist
    basic_plan, _ = PlanTier.objects.get_or_create(
        code='basic',
        defaults={
            'name': 'Basic',
            'price_display_mode': 'CONTACT_SALES',
            'max_staff': 2,
            'max_services': 5,
            'max_contacts': 1000,
            'is_published': True,
            'ordering': 1
        }
    )
    growth_plan, _ = PlanTier.objects.get_or_create(
        code='growth',
        defaults={
            'name': 'Growth',
            'price_display_mode': 'CONTACT_SALES',
            'max_staff': 5,
            'max_services': 15,
            'max_contacts': 5000,
            'is_published': True,
            'ordering': 2
        }
    )

    # Ensure Terms and Privacy exist
    LegalDocument.objects.get_or_create(
        doc_type=LegalDocumentType.TERMS,
        version='1.0',
        defaults={'title': 'Terms of Service', 'content': 'Sample Terms', 'status': 'PUBLISHED'}
    )
    LegalDocument.objects.get_or_create(
        doc_type=LegalDocumentType.PRIVACY,
        version='1.0',
        defaults={'title': 'Privacy Policy', 'content': 'Sample Privacy', 'status': 'PUBLISHED'}
    )

    return {
        'neoriz': neoriz,
        'admin_user': admin_user,
        'pipeline': pipeline,
        'stage': stage,
        'basic_plan': basic_plan,
        'growth_plan': growth_plan,
    }


def test_public_marketing_pages_load_for_anonymous_visitor(client, basic_setup):
    """Anonymous visitors should see the marketing landing page and subpages."""
    resp = client.get('/')
    assert resp.status_code == 200
    assert b"Manage WhatsApp conversations" in resp.content
    assert b"Request Access" in resp.content
    assert b"Neoriz" in resp.content

    features_resp = client.get('/features/')
    assert features_resp.status_code == 200
    assert b"Multi-Agent Shared Inbox" in features_resp.content

    pricing_resp = client.get('/pricing/')
    assert pricing_resp.status_code == 200
    assert b"Contact Sales" in pricing_resp.content
    assert b"WhatsApp Cloud API" in pricing_resp.content

    terms_resp = client.get('/terms/')
    assert terms_resp.status_code == 200
    assert b"Terms of Service" in terms_resp.content

    privacy_resp = client.get('/privacy/')
    assert privacy_resp.status_code == 200
    assert b"Privacy Policy" in privacy_resp.content


def test_authenticated_user_visiting_root_routes_to_dashboard(client, basic_setup):
    """An authenticated workspace member visiting '/' should land on their dashboard."""
    client.force_login(basic_setup['admin_user'])
    resp = client.get('/')
    assert resp.status_code == 302
    assert resp.url == '/app/dashboard'
    bootstrap = client.get(reverse('api-bootstrap'))
    assert bootstrap.status_code == 200
    assert bootstrap.json()['user']['id'] == basic_setup['admin_user'].id
    assert bootstrap.json()['tenant']['id'] == basic_setup['neoriz'].id


def test_demo_request_routes_to_platform_level(client, basic_setup):
    """
    Public demo inquiries are stored at the platform operator level.
    They NEVER automatically create CRM deals or contacts in client tenant (including Neoriz Solutions).
    """
    payload = {
        'name': 'Aditya Verma',
        'email': 'aditya@retailplus.com',
        'phone': '+919876543210',
        'company_name': 'RetailPlus Stores',
        'team_size': '6-15',
        'primary_interest': 'whatsapp_crm',
        'notes': 'Looking to automate retail enquiries.',
    }
    resp = client.post('/book-demo/', payload)
    assert resp.status_code == 200
    assert b"Demo Request Received!" in resp.content

    # Check DemoRequest in database at platform level
    req = DemoRequest.objects.filter(email='aditya@retailplus.com').first()
    assert req is not None
    assert req.routed_to_tenant is None
    assert req.company_name == 'RetailPlus Stores'

    # Verify no CRM Deal automatically leaked into Neoriz Solutions client workspace
    deal = Deal.objects.filter(tenant=basic_setup['neoriz'], contact__email='aditya@retailplus.com').first()
    assert deal is None


def test_self_service_signup_is_forbidden_server_side(client, basic_setup):
    """Direct self-service signup POST is rejected server-side with 403 Forbidden."""
    payload = {
        'full_name': 'Kavya Menon',
        'email': 'kavya@innovatelabs.io',
        'password': 'SecurePassword88!',
        'confirm_password': 'SecurePassword88!',
        'business_name': 'Innovate Labs',
        'phone': '+919840012345',
        'plan': basic_setup['growth_plan'].id,
        'terms_accepted': True,
        'marketing_consent': False,
    }
    resp = client.post('/signup/', payload)
    assert resp.status_code == 403
    assert not User.objects.filter(email='kavya@innovatelabs.io').exists()
    assert not Tenant.objects.filter(name='Innovate Labs').exists()


def test_email_verification_token_lifecycle(client, basic_setup):
    """Test verification token validation, expiry, and single-use protection."""
    user = User.objects.create_user('verifyuser', 'verify@test.com', 'Pass123!')
    token = EmailVerificationToken.generate_for_user(user, hours=24)

    assert token.is_valid

    # GET shows scanner-safe confirmation page without consuming token
    resp_get = client.get(f'/verify-email/{token.token}/')
    assert resp_get.status_code == 200
    assert b"Confirm" in resp_get.content
    token.refresh_from_db()
    assert not token.is_used

    # Explicit POST confirms verification atomically
    resp = client.post(f'/verify-email/{token.token}/')
    assert resp.status_code == 200
    assert b"Email Verified!" in resp.content

    token.refresh_from_db()
    assert token.is_used
    assert not token.is_valid

    # Re-use should fail
    resp2 = client.get(f'/verify-email/{token.token}/')
    assert resp2.status_code == 410
    assert b"Expired or Invalid" in resp2.content


def test_seat_limit_enforcement_prevents_excess_invitations(client, basic_setup):
    """A tenant on a plan with max_staff=2 cannot exceed that seat limit."""
    tenant = Tenant.objects.create(name='Small Shop', slug='small-shop', max_staff=2)
    owner = User.objects.create_user('shopowner', 'owner@shop.com', 'Pass123!')
    TenantMembership.objects.create(tenant=tenant, user=owner, role=TenantRole.OWNER)

    # 1 member currently (the owner). Limit is 2.
    assert tenant.can_add_staff()

    # Add second member
    staff1 = User.objects.create_user('staff1', 'staff1@shop.com', 'Pass123!')
    TenantMembership.objects.create(tenant=tenant, user=staff1, role=TenantRole.STAFF)

    # 2 members now. Limit reached!
    assert not tenant.can_add_staff()

    # Attempting to invite a third staff via tenant_invite_view should be blocked
    client.force_login(owner)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    resp = client.post('/team/invite/', {'email': 'staff2@shop.com', 'role': 'STAFF'})
    assert resp.status_code == 302
    # Verify no invitation was created
    assert not tenant.invitations.filter(email='staff2@shop.com').exists()


def test_pending_activation_blocks_live_outbound_whatsapp_delivery(basic_setup):
    """Workspaces with PENDING_APPROVAL subscription status cannot send live outbound messages."""
    tenant = Tenant.objects.create(name='Pending Co', slug='pending-co', is_active=True)
    plan = basic_setup['basic_plan']
    TenantSubscription.objects.create(
        tenant=tenant,
        requested_plan=plan,
        effective_plan=plan,
        status=SubscriptionStatus.PENDING_APPROVAL
    )

    delivery = WhatsAppDelivery.objects.create(
        tenant=tenant,
        recipient_phone='+919999900011',
        payload={'text': 'Hello customer'},
        status='PENDING'
    )

    from apps.whatsapp.delivery import dispatch
    result = dispatch(delivery.id)
    assert result is False

    delivery.refresh_from_db()
    assert delivery.status == 'BLOCKED'
    assert 'pending platform activation' in delivery.last_error.lower()


def test_onboarding_wizard_step_flow_and_completion(client, basic_setup):
    """Test full execution of the 8-step onboarding wizard."""
    tenant = Tenant.objects.create(name='Wizard Test Corp', slug='wizard-test-corp', is_active=True)
    owner = User.objects.create_user('wizowner', 'wiz@test.com', 'Pass123!', is_staff=True)
    TenantMembership.objects.create(tenant=tenant, user=owner, role=TenantRole.OWNER)
    TenantSubscription.objects.create(
        tenant=tenant,
        requested_plan=basic_setup['growth_plan'],
        effective_plan=basic_setup['growth_plan'],
        status=SubscriptionStatus.ACTIVE
    )

    client.force_login(owner)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Step 1: Profile POST
    resp1 = client.post('/onboarding/?step=profile', {
        'shop_name': 'Wizard Test Corp Store',
        'contact_phone': '+919988776655',
        'contact_email': 'contact@wizcorp.com',
        'website': 'https://wizcorp.com',
        'business_hours': '9 AM - 6 PM',
    })
    assert resp1.status_code == 302
    assert 'step=plan' in resp1.url

    # Check BusinessProfile created
    bp = BusinessProfile.objects.filter(tenant=tenant).first()
    assert bp is not None
    assert bp.shop_name == 'Wizard Test Corp Store'

    # Step 2: Plan POST
    resp2 = client.post('/onboarding/?step=plan')
    assert resp2.status_code == 302
    assert 'step=whatsapp' in resp2.url

    # Step 3: WhatsApp credentials POST
    resp3 = client.post('/onboarding/?step=whatsapp', {
        'phone_number_id': '1000999888',
        'business_account_id': '2000999888',
        'verify_token': 'mySecretToken',
        'app_secret': 'sec123',
        'access_token': 'EAABCTest',
        'is_active': True,
    })
    assert resp3.status_code == 302
    assert 'step=knowledge' in resp3.url

    # Step 4: Knowledge POST
    resp4 = client.post('/onboarding/?step=knowledge', {
        'service_name': 'Digital Marketing',
        'service_description': 'SEO & Ads',
        'faq_question': 'How much do you charge?',
        'faq_answer': 'Contact us for a quote.',
    })
    assert resp4.status_code == 302
    assert 'step=team' in resp4.url

    # Step 6: Workspace pipeline POST
    resp6 = client.post('/onboarding/?step=workspace', {
        'pipeline_name': 'Sales Pipeline',
    })
    assert resp6.status_code == 302
    assert 'step=test' in resp6.url

    # Step 7: Test simulation POST
    resp7 = client.post('/onboarding/?step=test')
    assert resp7.status_code == 302
    assert 'step=readiness' in resp7.url

    # Step 8: Readiness review POST -> Marks completed & enters dashboard
    resp8 = client.post('/onboarding/?step=readiness')
    assert resp8.status_code == 302
    assert resp8.url == '/dashboard/'

    prog = OnboardingProgress.objects.filter(tenant=tenant).first()
    assert prog.is_completed
    assert prog.current_step == 'completed'
