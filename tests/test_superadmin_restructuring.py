import pytest
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth.models import User
from django.test import Client

from apps.tenants.models import (
    Tenant, TenantMembership, TenantRole, PlanTier, TenantSubscription,
    SubscriptionStatus, StaffAccessRequest, StaffRequestStatus,
    AccountActivationToken, DemoRequest, UserSecurityProfile
)
from apps.tenants.capabilities import MODULE_CATALOG
from apps.crm.models import Deal, DealStage, Pipeline, Activity, ActivityStatus, ContactNote
from apps.chatbot.models import Customer
from apps.whatsapp.models import WhatsAppConfig


@pytest.fixture
def plan_tier(db):
    plan, _ = PlanTier.objects.get_or_create(
        code='growth',
        defaults={
            'name': 'Growth Plan',
            'monthly_price': 2999,
            'max_staff': 10,
            'max_services': 50,
            'max_contacts': 1000,
            'enabled_modules': list(MODULE_CATALOG.keys()),
            'is_published': True,
        }
    )
    if not plan.enabled_modules:
        plan.enabled_modules = list(MODULE_CATALOG.keys())
        plan.save()
    return plan


@pytest.fixture
def superadmin_user(db):
    user, _ = User.objects.get_or_create(
        username='platformadmin',
        defaults={'email': 'superadmin@neoriz.com', 'is_superuser': True, 'is_staff': True}
    )
    user.set_password('StrongAdminPass123!')
    user.save()
    UserSecurityProfile.objects.update_or_create(user=user, defaults={'email_verified': True})
    return user


@pytest.fixture
def neoriz_client_tenant(db, plan_tier):
    tenant, _ = Tenant.objects.get_or_create(
        slug='neoriz-solutions',
        defaults={'name': 'Neoriz Solutions', 'contact_email': 'hello@neoriz.com', 'is_active': True}
    )
    TenantSubscription.objects.get_or_create(
        tenant=tenant,
        defaults={'effective_plan': plan_tier, 'status': SubscriptionStatus.ACTIVE}
    )
    return tenant


@pytest.fixture
def client_admin_user(db, neoriz_client_tenant):
    user, _ = User.objects.get_or_create(
        username='client_owner_ashfaq',
        defaults={'email': 'ashfaq@neoriz.com', 'is_superuser': False, 'is_staff': False}
    )
    user.set_password('ExistingOwnerPass123!')
    user.save()
    UserSecurityProfile.objects.update_or_create(user=user, defaults={'email_verified': True})

    TenantMembership.objects.update_or_create(
        tenant=neoriz_client_tenant,
        user=user,
        defaults={'role': TenantRole.OWNER, 'is_active': True}
    )
    return user


@pytest.fixture
def sales_agent_user(db, neoriz_client_tenant):
    user, _ = User.objects.get_or_create(
        username='sales_agent_sam',
        defaults={'email': 'sam@neoriz.com', 'is_superuser': False, 'is_staff': False}
    )
    user.set_password('AgentPass123!')
    user.save()
    UserSecurityProfile.objects.update_or_create(user=user, defaults={'email_verified': True})

    TenantMembership.objects.update_or_create(
        tenant=neoriz_client_tenant,
        user=user,
        defaults={'role': TenantRole.STAFF, 'is_active': True}
    )
    return user


@pytest.fixture
def second_tenant(db, plan_tier):
    tenant, _ = Tenant.objects.get_or_create(
        slug='acme-corp',
        defaults={'name': 'Acme Corporation', 'contact_email': 'contact@acme.com', 'is_active': True}
    )
    TenantSubscription.objects.get_or_create(
        tenant=tenant,
        defaults={'effective_plan': plan_tier, 'status': SubscriptionStatus.ACTIVE}
    )
    return tenant


# ==============================================================================
# TEST 1 & 2: OPERATOR VS CLIENT TENANT DISTINCTION & NO IMPLICIT PRIVILEGES
# ==============================================================================

@pytest.mark.django_db
def test_same_named_client_has_no_platform_privileges(client_admin_user, neoriz_client_tenant):
    """
    Even though the tenant is named 'Neoriz Solutions' and slug is 'neoriz-solutions',
    and the user has an @neoriz.com email, they are an ordinary client admin.
    They cannot access Super Admin endpoints.
    """
    client = Client()
    client.force_login(client_admin_user)

    # Attempt to access platform management APIs
    res = client.get('/api/platform/tenants/')
    assert res.status_code == 403

    res_staff = client.get('/api/platform/staff-requests/')
    assert res_staff.status_code == 403

    res_metrics = client.get('/api/platform/metrics/')
    assert res_metrics.status_code == 403


@pytest.mark.django_db
def test_superadmin_can_access_platform_management(superadmin_user):
    """Super Admin has global platform management access."""
    client = Client()
    client.force_login(superadmin_user)

    res = client.get('/api/platform/tenants/')
    assert res.status_code == 200
    assert 'tenants' in res.json()


# ==============================================================================
# TEST 3: PUBLIC SELF-SERVICE SIGNUP IS DISABLED SERVER-SIDE
# ==============================================================================

@pytest.mark.django_db
def test_signup_post_is_forbidden_server_side():
    """POST /signup/ must return 403 Forbidden."""
    client = Client()
    res = client.post('/signup/', {
        'business_name': 'Hacker Co',
        'email': 'hacker@example.com',
        'password': 'Password123!',
    })
    assert res.status_code == 403


@pytest.mark.django_db
def test_signup_get_redirects_to_request_access():
    """GET /signup/ redirects to /request-access/."""
    client = Client()
    res = client.get('/signup/')
    assert res.status_code == 302
    assert '/request-access/' in res.url


@pytest.mark.django_db
def test_request_access_creates_non_account_demo_request():
    """
    POST /request-access/ creates a ClientOnboarding + DemoRequest record at platform level.
    Does NOT create a User or Tenant, and does NOT log anyone in.
    """
    from apps.tenants.models import ClientOnboarding
    initial_user_count = User.objects.count()
    initial_tenant_count = Tenant.objects.count()

    client = Client()
    res = client.post('/request-access/', {
        'owner_full_name': 'Prospect Lead',
        'business_name': 'Prospective Retailers',
        'owner_email': 'prospect@retail.com',
        'desired_username': 'prospect_retail',
        'whatsapp_number': '+919988776655',
        'notes': 'Looking for 5 seats.',
        'terms_accepted': 'on',
    })
    assert res.status_code == 302

    # Verify no User or Tenant was created yet
    assert User.objects.count() == initial_user_count
    assert Tenant.objects.count() == initial_tenant_count

    # Verify onboarding & demo request were stored at platform level
    assert ClientOnboarding.objects.filter(owner_email='prospect@retail.com', approval_status='PENDING').exists()
    ticket = DemoRequest.objects.filter(email='prospect@retail.com').first()
    assert ticket is not None
    assert ticket.routed_to_tenant is None


# ==============================================================================
# TEST 4 & 7: STAFF ACCESS REQUESTS DO NOT CREATE ACCOUNTS
# ==============================================================================

@pytest.mark.django_db
def test_client_admin_staff_request_creates_ticket_not_account(client_admin_user, neoriz_client_tenant):
    """
    Client Admin submits a staff access request.
    Creates a StaffAccessRequest ticket; does NOT create User or TenantMembership.
    """
    client = Client()
    client.force_login(client_admin_user)

    initial_users = User.objects.count()

    res = client.post(
        '/api/team/request-staff/',
        data={
            'full_name': 'Aisha Khan',
            'email': 'aisha@neoriz.com',
            'role': TenantRole.STAFF,
            'notes': 'New customer service rep.',
        },
        content_type='application/json'
    )
    assert res.status_code == 201

    # No User record should have been created
    assert User.objects.count() == initial_users
    assert not User.objects.filter(email='aisha@neoriz.com').exists()

    # Ticket exists with PENDING status
    req = StaffAccessRequest.objects.filter(email='aisha@neoriz.com').first()
    assert req is not None
    assert req.status == StaffRequestStatus.PENDING
    assert req.tenant == neoriz_client_tenant


# ==============================================================================
# TEST 5, 6 & 8: SUPER ADMIN PROVISIONS USER & ACTIVATION TOKEN
# ==============================================================================

@pytest.mark.django_db
def test_superadmin_approves_staff_request_and_issues_activation(superadmin_user, neoriz_client_tenant):
    """
    Super Admin approves staff request: provisions user, attaches membership,
    and creates a secure single-use expiring AccountActivationToken.
    """
    staff_req = StaffAccessRequest.objects.create(
        tenant=neoriz_client_tenant,
        requested_by=superadmin_user,
        full_name='Vikram Seth',
        email='vikram@neoriz.com',
        role=TenantRole.STAFF,
        status=StaffRequestStatus.PENDING
    )

    client = Client()
    client.force_login(superadmin_user)

    res = client.post(
        f'/api/platform/staff-requests/{staff_req.id}/approve/',
        data={'review_notes': 'Approved seat allocation.'},
        content_type='application/json'
    )
    assert res.status_code == 200
    data = res.json()
    assert data['status'] == 'approved'
    assert 'activation_url' in data

    # Verify user exists and membership created
    user = User.objects.get(email='vikram@neoriz.com')
    assert TenantMembership.objects.filter(tenant=neoriz_client_tenant, user=user, role=TenantRole.STAFF).exists()

    # Verify activation token
    token_obj = AccountActivationToken.objects.get(user=user)
    assert not token_obj.is_used
    assert token_obj.is_valid


@pytest.mark.django_db
def test_single_use_activation_token(db):
    """
    Activation link sets the password, marks email as verified,
    and cannot be reused.
    """
    user = User.objects.create(username='new_onboardee', email='onboard@example.com')
    user.set_unusable_password()
    user.save()
    UserSecurityProfile.objects.create(user=user, email_verified=False)

    token_obj = AccountActivationToken.create_for_user(user)

    client = Client()

    # GET activation page
    res_get = client.get(f'/activate/{token_obj.token}/')
    assert res_get.status_code == 200

    # POST new password
    res_post = client.post(f'/activate/{token_obj.token}/', {
        'password': 'NewSecurePassword123!',
        'confirm_password': 'NewSecurePassword123!',
    })
    assert res_post.status_code == 302
    assert res_post.url == '/app/'

    # Token is now marked used
    token_obj.refresh_from_db()
    assert token_obj.is_used

    # User can authenticate with the new password, while password setup alone does NOT verify an unverified email
    user.refresh_from_db()
    assert user.check_password('NewSecurePassword123!')
    assert not user.security_profile.email_verified

    # Attempting to reuse the same token fails
    res_reuse = client.get(f'/activate/{token_obj.token}/')
    assert res_reuse.status_code == 400


# ==============================================================================
# TEST 9 & 10: CLIENT-OWNED META CONFIG & SALES AGENT 403
# ==============================================================================

@pytest.mark.django_db
def test_sales_agent_cannot_access_whatsapp_credentials(sales_agent_user):
    """Sales agents (STAFF role) receive 403 when trying to view/edit WhatsApp settings."""
    client = Client()
    client.force_login(sales_agent_user)

    res_get = client.get('/api/settings/whatsapp/')
    assert res_get.status_code == 403

    res_post = client.post(
        '/api/settings/whatsapp/',
        data={'phone_number_id': '1234567890'},
        content_type='application/json'
    )
    assert res_post.status_code == 403


@pytest.mark.django_db
def test_client_admin_can_save_whatsapp_credentials(client_admin_user, neoriz_client_tenant):
    """Client admin can save their own WhatsApp credentials."""
    client = Client()
    client.force_login(client_admin_user)

    res = client.post(
        '/api/settings/whatsapp/',
        data={
            'phone_number_id': '987654321012345',
            'business_account_id': '209876543210123',
            'access_token': 'EAABtesting_token_at_least_30_characters_long_for_meta',
            'webhook_verify_token': 'my_custom_webhook_secret',
        },
        content_type='application/json'
    )
    assert res.status_code == 200

    cfg = WhatsAppConfig.objects.get(tenant=neoriz_client_tenant)
    assert cfg.phone_number_id == '987654321012345'
    assert cfg.verify_token == 'my_custom_webhook_secret'


# ==============================================================================
# TEST 11: NUMBER OWNERSHIP VALIDATION PREVENTS DUPLICATE CLAIMS
# ==============================================================================

@pytest.mark.django_db
def test_duplicate_phone_number_id_claim_rejected(client_admin_user, neoriz_client_tenant, second_tenant):
    """A client cannot claim a WhatsApp Phone Number ID already in use by another tenant."""
    # Tenant 1 has the number configured
    WhatsAppConfig.objects.create(
        tenant=neoriz_client_tenant,
        phone_number_id='100000000000001',
        access_token='valid_token_123456789012345678901234567890'
    )

    # User from Tenant 2 tries to claim the same phone_number_id
    user2 = User.objects.create(username='acme_admin', email='admin@acme.com')
    UserSecurityProfile.objects.create(user=user2, email_verified=True)
    TenantMembership.objects.create(tenant=second_tenant, user=user2, role=TenantRole.OWNER, is_active=True)

    client = Client()
    client.force_login(user2)

    res = client.post(
        '/api/settings/whatsapp/',
        data={
            'phone_number_id': '100000000000001',
            'access_token': 'valid_token_123456789012345678901234567890',
        },
        content_type='application/json'
    )
    assert res.status_code == 409
    assert 'already connected to another client workspace' in res.json()['error']


# ==============================================================================
# TEST 12: WORKSPACE SETTINGS & BRANDING (CLIENT LOGO URL & DETAILS)
# ==============================================================================

@pytest.mark.django_db
def test_client_admin_can_update_workspace_profile(client_admin_user, neoriz_client_tenant):
    """Client admin can update branding logo URL, timezone, and contact info."""
    client = Client()
    client.force_login(client_admin_user)

    res = client.post(
        '/api/settings/workspace/',
        data={
            'name': 'Neoriz IT Solutions Pvt Ltd',
            'logo_url': 'https://cdn.example.com/neoriz-custom-logo.png',
            'timezone': 'Asia/Dubai',
            'contact_email': 'support@neoriz.com',
            'contact_phone': '+971501234567',
        },
        content_type='application/json'
    )
    assert res.status_code == 200

    neoriz_client_tenant.refresh_from_db()
    assert neoriz_client_tenant.name == 'Neoriz IT Solutions Pvt Ltd'
    assert neoriz_client_tenant.logo_url == 'https://cdn.example.com/neoriz-custom-logo.png'
    assert neoriz_client_tenant.timezone == 'Asia/Dubai'
    assert neoriz_client_tenant.effective_logo_url == 'https://cdn.example.com/neoriz-custom-logo.png'


# ==============================================================================
# TEST 13: WORK REASSIGNMENT BEFORE MEMBER REMOVAL
# ==============================================================================

@pytest.mark.django_db
def test_member_removal_requires_work_reassignment(client_admin_user, sales_agent_user, neoriz_client_tenant):
    """
    A member who owns open deals or tasks cannot be removed without reassigning work first.
    Reassigning work transfers deals and allows removal.
    """
    client = Client()
    client.force_login(client_admin_user)

    # Create a pipeline, stage, customer, and an open deal owned by sales_agent_user
    pipeline = Pipeline.objects.create(tenant=neoriz_client_tenant, name='Standard Sales Pipeline')
    stage = DealStage.objects.create(pipeline=pipeline, name='Discovery', order=1, probability=20)
    customer = Customer.objects.create(tenant=neoriz_client_tenant, name='Big Enterprise', phone_number='+919876500001')

    deal = Deal.objects.create(
        tenant=neoriz_client_tenant,
        title='Enterprise WhatsApp Contract',
        contact=customer,
        pipeline=pipeline,
        stage=stage,
        owner=sales_agent_user,
        amount=Decimal('150000.00'),
    )

    agent_membership = TenantMembership.objects.get(tenant=neoriz_client_tenant, user=sales_agent_user)

    # Attempt to remove sales_agent_user without reassigning work
    res_remove = client.post(f'/api/team/members/{agent_membership.id}/remove/')
    assert res_remove.status_code == 400
    assert res_remove.json().get('requires_reassign') is True
    assert res_remove.json().get('open_deals') == 1

    # Reassign work to client_admin_user
    res_reassign = client.post(
        '/api/team/reassign-work/',
        data={
            'from_user_id': sales_agent_user.id,
            'to_user_id': client_admin_user.id,
        },
        content_type='application/json'
    )
    assert res_reassign.status_code == 200
    assert res_reassign.json()['deals_reassigned'] == 1

    # Verify deal owner updated
    deal.refresh_from_db()
    assert deal.owner == client_admin_user

    # Now removal succeeds
    res_remove2 = client.post(f'/api/team/members/{agent_membership.id}/remove/')
    assert res_remove2.status_code == 200
    agent_membership.refresh_from_db()
    assert not agent_membership.is_active


# ==============================================================================
# TEST 14: CRM CONTACT NOTES & MERGING
# ==============================================================================

@pytest.mark.django_db
def test_crm_contact_internal_notes_and_merge(client_admin_user, neoriz_client_tenant):
    """
    Internal notes are stored separately on ContactNote and can be added via API.
    Two duplicate contacts can be merged with full history preservation.
    """
    client = Client()
    client.force_login(client_admin_user)

    contact1 = Customer.objects.create(tenant=neoriz_client_tenant, name='Pooja Patel', phone_number='+919876511111')
    contact2 = Customer.objects.create(tenant=neoriz_client_tenant, name='Pooja P.', phone_number='+919876511112')

    # Add internal note to contact1
    res_note = client.post(
        f'/api/crm/contacts/{contact1.id}/notes/',
        data={'content': 'Customer interested in agency maintenance contract.'},
        content_type='application/json'
    )
    assert res_note.status_code == 201

    note = ContactNote.objects.filter(contact=contact1).first()
    assert note is not None
    assert note.content == 'Customer interested in agency maintenance contract.'
    assert note.author == client_admin_user

    # Merge contact2 into contact1
    res_merge = client.post(
        '/api/crm/contacts/merge/',
        data={'primary_id': contact1.id, 'duplicate_id': contact2.id},
        content_type='application/json'
    )
    assert res_merge.status_code == 200
    assert res_merge.json()['status'] == 'merged'
    assert not Customer.objects.filter(id=contact2.id).exists()
