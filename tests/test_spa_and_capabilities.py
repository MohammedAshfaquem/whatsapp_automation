import pytest
import json
from django.urls import reverse
from django.contrib.auth.models import User
from apps.tenants.models import (
    Tenant, TenantMembership, TenantRole, MembershipRole, PlanTier,
    SubscriptionStatus, TenantSubscription, UserSecurityProfile
)
from apps.services.models import Service, PriceType
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice, ConversationStatus
from apps.crm.models import Pipeline, DealStage, Deal, Activity, Company
from apps.knowledge_base.models import FAQ, KnowledgeDocument, DocumentCategory


@pytest.fixture
def spa_setup(db):
    """Sets up plans, tenants, superuser, tenant owner, and staff."""
    plan_growth, _ = PlanTier.objects.get_or_create(
        code='growth_spa',
        defaults={
            'name': 'Growth Plan',
            'max_contacts': 2500,
            'max_documents': 2,
            'max_staff': 3,
            'max_services': 10,
            'monthly_message_allowance': 5000,
            'enabled_modules': [
                'contacts_companies', 'deals_pipelines', 'tasks_followups',
                'shared_inbox', 'ai_assistant', 'team_management', 'reports'
            ]
        }
    )

    plan_pending, _ = PlanTier.objects.get_or_create(
        code='pending_spa',
        defaults={
            'name': 'Pending Plan',
            'max_contacts': 100,
            'max_documents': 5,
            'max_staff': 2,
            'max_services': 5,
            'monthly_message_allowance': 100,
            'enabled_modules': ['contacts_companies', 'shared_inbox']
        }
    )

    # Superuser
    superadmin = User.objects.create_superuser('spa_super', 'super@spa.com', 'SuperPass123!')
    UserSecurityProfile.get_or_create_for_user(superadmin)

    # Tenant 1: Active Growth Tenant
    tenant_active = Tenant.objects.create(name='Active Corp', slug='active-corp')
    sub_active, _ = TenantSubscription.objects.get_or_create(
        tenant=tenant_active,
        defaults={'effective_plan': plan_growth, 'status': SubscriptionStatus.ACTIVE}
    )

    owner_active = User.objects.create_user('active_owner', 'owner@active.com', 'OwnerPass123!')
    sec_owner = UserSecurityProfile.get_or_create_for_user(owner_active)
    sec_owner.email_verified = True
    sec_owner.save()
    TenantMembership.objects.create(tenant=tenant_active, user=owner_active, role=MembershipRole.OWNER)

    staff_active = User.objects.create_user('active_staff', 'staff@active.com', 'StaffPass123!')
    sec_staff = UserSecurityProfile.get_or_create_for_user(staff_active)
    sec_staff.email_verified = True
    sec_staff.save()
    TenantMembership.objects.create(tenant=tenant_active, user=staff_active, role=MembershipRole.STAFF)

    # Tenant 2: Pending Approval Tenant
    tenant_pending = Tenant.objects.create(name='Pending Corp', slug='pending-corp')
    sub_pending, _ = TenantSubscription.objects.get_or_create(
        tenant=tenant_pending,
        defaults={'effective_plan': plan_pending, 'status': SubscriptionStatus.PENDING_APPROVAL}
    )

    owner_pending = User.objects.create_user('pending_owner', 'owner@pending.com', 'PendingPass123!')
    sec_p = UserSecurityProfile.get_or_create_for_user(owner_pending)
    sec_p.email_verified = True
    sec_p.save()
    TenantMembership.objects.create(tenant=tenant_pending, user=owner_pending, role=MembershipRole.OWNER)

    return {
        'superadmin': superadmin,
        'tenant_active': tenant_active,
        'owner_active': owner_active,
        'staff_active': staff_active,
        'tenant_pending': tenant_pending,
        'owner_pending': owner_pending,
        'plan_growth': plan_growth,
    }


@pytest.mark.django_db
def test_spa_bootstrap_requires_login(client):
    """Unauthenticated request to bootstrap returns 401 Unauthorized JSON."""
    res = client.get(reverse('api-bootstrap'))
    assert res.status_code == 401
    assert res.json()['error'] == 'Authentication required'


@pytest.mark.django_db
def test_spa_bootstrap_authenticated_user(client, spa_setup):
    """Authenticated tenant owner gets full bootstrap context."""
    owner = spa_setup['owner_active']
    tenant = spa_setup['tenant_active']
    client.force_login(owner)

    # Set active tenant in session
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    res = client.get(reverse('api-bootstrap'))
    assert res.status_code == 200
    data = res.json()

    assert data['user']['username'] == owner.username
    assert data['tenant']['id'] == tenant.id
    assert data['tenant']['name'] == 'Active Corp'
    assert data['membership']['role'] == 'OWNER'
    assert data['capabilities']['contacts']['allowed'] is True
    assert data['capabilities']['inbox']['allowed'] is True
    assert data['capabilities']['platform_dashboard']['allowed'] is False  # Tenant owner cannot access platform


@pytest.mark.django_db
def test_direct_route_denial_when_subscription_pending(client, spa_setup):
    """
    Direct operational routes return 403 Forbidden when subscription is PENDING_APPROVAL.
    Only onboarding/setup routes are permitted.
    """
    owner_pending = spa_setup['owner_pending']
    tenant_pending = spa_setup['tenant_pending']
    client.force_login(owner_pending)

    session = client.session
    session['active_tenant_id'] = tenant_pending.id
    session.save()

    # Bootstrap should report contacts capability disallowed with pending reason
    res_b = client.get(reverse('api-bootstrap'))
    data = res_b.json()
    assert data['capabilities']['contacts']['allowed'] is False
    assert "pending platform administrator activation" in data['capabilities']['contacts']['reason']

    # Direct GET to CRM contacts API must return 403 Forbidden
    res_crm = client.get(reverse('api-crm-contacts'))
    assert res_crm.status_code == 403
    assert "pending platform administrator activation" in res_crm.json()['reason']

    # Direct GET to Inbox API must return 403 Forbidden
    res_inbox = client.get(reverse('api-inbox-conversations'))
    assert res_inbox.status_code == 403


@pytest.mark.django_db
def test_spa_crm_contacts_api_tenant_scoping(client, spa_setup):
    """CRM contacts API strictly scopes queries to active tenant."""
    owner = spa_setup['owner_active']
    tenant = spa_setup['tenant_active']
    client.force_login(owner)

    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create 2 contacts in Active Corp
    Customer.objects.create(tenant=tenant, name='Alice Tech', phone_number='+919876543201')
    Customer.objects.create(tenant=tenant, name='Bob Corp', phone_number='+919876543202')

    # Create 1 contact in another tenant
    Customer.objects.create(tenant=spa_setup['tenant_pending'], name='Foreign Contact', phone_number='+919876543203')

    res = client.get(reverse('api-crm-contacts'))
    assert res.status_code == 200
    contacts = res.json()['contacts']
    assert len(contacts) == 2
    assert all(c['name'] != 'Foreign Contact' for c in contacts)

    # Create contact via POST
    post_res = client.post(
        reverse('api-crm-contacts'),
        data=json.dumps({
            'name': 'Charlie New',
            'phone_number': '+919876543204',
            'email': 'charlie@new.com',
            'lifecycle_stage': 'LEAD'
        }),
        content_type='application/json'
    )
    assert post_res.status_code == 201
    assert Customer.objects.filter(tenant=tenant, phone_number='+919876543204').exists()


@pytest.mark.django_db
def test_spa_knowledge_document_limit_enforcement(client, spa_setup):
    """
    Enforces tenant.effective_max_documents on uploaded KnowledgeDocument records.
    max_documents for plan_growth is 2.
    """
    owner = spa_setup['owner_active']
    tenant = spa_setup['tenant_active']
    client.force_login(owner)

    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Upload Doc 1
    res1 = client.post(
        reverse('api-knowledge-doc-create'),
        data=json.dumps({'title': 'Policy 1', 'content': 'Refund policy details...'}),
        content_type='application/json'
    )
    assert res1.status_code == 201

    # Upload Doc 2
    res2 = client.post(
        reverse('api-knowledge-doc-create'),
        data=json.dumps({'title': 'Policy 2', 'content': 'Warranty terms details...'}),
        content_type='application/json'
    )
    assert res2.status_code == 201

    # Attempting to upload Doc 3 when limit is 2 must be blocked
    res3 = client.post(
        reverse('api-knowledge-doc-create'),
        data=json.dumps({'title': 'Policy 3', 'content': 'Excess document...'}),
        content_type='application/json'
    )
    assert res3.status_code == 400
    assert "Document limit reached" in res3.json()['error']


@pytest.mark.django_db
def test_platform_apis_require_superuser(client, spa_setup):
    """Non-superuser tenant members are denied access to platform administration APIs."""
    owner = spa_setup['owner_active']
    client.force_login(owner)

    res = client.get(reverse('api-platform-metrics'))
    assert res.status_code == 403

    # Superuser can access platform metrics
    superadmin = spa_setup['superadmin']
    client.force_login(superadmin)
    res_super = client.get(reverse('api-platform-metrics'))
    assert res_super.status_code == 200
    assert 'total_tenants' in res_super.json()


@pytest.mark.django_db
def test_spa_app_shell_serves_html(client, spa_setup):
    """GET /app/ and /app/<path> renders React container with CSRF token and assets."""
    owner = spa_setup['owner_active']
    client.force_login(owner)

    res = client.get('/app/dashboard')
    assert res.status_code == 200
    content = res.content.decode()
    assert 'id="root"' in content
    assert 'Neoriz WhatsApp Automation' in content
    assert 'dist/assets/index.js' in content
    assert 'dist/assets/index.css' in content


@pytest.mark.django_db
def test_platform_matrix_apis_full_lifecycle(client, spa_setup):
    """Test platform matrix list, plan editing, bundle copy, tenant overrides, and bulk assign."""
    superadmin = spa_setup['superadmin']
    tenant = spa_setup['tenant_active']
    client.force_login(superadmin)

    # 1. GET matrix
    res = client.get(reverse('api-platform-matrix'))
    assert res.status_code == 200
    data = res.json()
    assert 'plans' in data
    assert 'capabilities' in data
    assert 'tenants' in data
    plan_codes = [p['code'] for p in data['plans']]
    assert 'growth_spa' in plan_codes

    # 2. Update plan bundle
    update_res = client.post(
        reverse('api-platform-plan-bundle', kwargs={'plan_code': 'growth_spa'}),
        data=json.dumps({
            'enabled_modules': ['contacts_companies', 'deals_pipelines', 'reports'],
            'max_contacts': 3000,
            'max_staff': 4,
        }),
        content_type='application/json'
    )
    assert update_res.status_code == 200
    plan_growth = PlanTier.objects.get(code='growth_spa')
    assert plan_growth.max_contacts == 3000
    assert 'reports' in plan_growth.enabled_modules

    # 3. Copy bundle to another plan
    plan_target = PlanTier.objects.create(code='target_copy_plan', name='Target Copy Plan')
    copy_res = client.post(
        reverse('api-platform-copy-bundle'),
        data=json.dumps({
            'source_plan_code': 'growth_spa',
            'target_plan_code': 'target_copy_plan',
        }),
        content_type='application/json'
    )
    assert copy_res.status_code == 200
    plan_target.refresh_from_db()
    assert plan_target.max_contacts == 3000

    # 4. Tenant overrides (ALLOW/DENY/INHERIT)
    ov_get = client.get(reverse('api-platform-tenant-overrides', kwargs={'tenant_id': tenant.id}))
    assert ov_get.status_code == 200
    assert 'overrides' in ov_get.json()

    ov_post = client.post(
        reverse('api-platform-tenant-overrides', kwargs={'tenant_id': tenant.id}),
        data=json.dumps({
            'overrides': {
                'reports': {'override': 'ALLOW', 'reason': 'Special customer trial'}
            }
        }),
        content_type='application/json'
    )
    assert ov_post.status_code == 200
    assert tenant.get_feature_override('reports') == 'ALLOW'

    # 5. Bulk assign preview & execution
    preview_res = client.post(
        reverse('api-platform-bulk-assign-preview'),
        data=json.dumps({
            'target_plan_code': 'target_copy_plan',
            'tenant_ids': [tenant.id],
        }),
        content_type='application/json'
    )
    assert preview_res.status_code == 200
    assert len(preview_res.json()['impact']) == 1

    exec_res = client.post(
        reverse('api-platform-bulk-assign'),
        data=json.dumps({
            'target_plan_code': 'target_copy_plan',
            'tenant_ids': [tenant.id],
            'confirm': True,
        }),
        content_type='application/json'
    )
    assert exec_res.status_code == 200
    assert exec_res.json()['updated_count'] == 1


@pytest.mark.django_db
def test_onboarding_reports_usage_and_whatsapp_verification(client, spa_setup):
    """Test tenant onboarding, synthetic test, reports overview, usage, and whatsapp verification."""
    owner = spa_setup['owner_active']
    tenant = spa_setup['tenant_active']
    client.force_login(owner)

    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # 1. Onboarding status
    onb_res = client.get(reverse('api-onboarding-status'))
    assert onb_res.status_code == 200
    assert 'steps' in onb_res.json()

    # 2. Synthetic Assistant Test
    test_res = client.post(
        reverse('api-onboarding-test-assistant'),
        data=json.dumps({'query': 'Do you offer IT consulting?'}),
        content_type='application/json'
    )
    assert test_res.status_code == 200
    assert test_res.json()['result']['success'] is True

    # 3. Reports Overview
    rep_res = client.get(reverse('api-reports-overview'))
    assert rep_res.status_code == 200
    assert 'conversations' in rep_res.json()
    assert 'deals' in rep_res.json()

    # 4. Usage Overview
    use_res = client.get(reverse('api-usage-overview'))
    assert use_res.status_code == 200
    assert 'messages' in use_res.json()
    assert 'documents' in use_res.json()

    # 5. WhatsApp Settings & Verification
    wa_get = client.get(reverse('api-whatsapp-settings'))
    assert wa_get.status_code == 200
    assert 'credentials_present' in wa_get.json()
    assert 'webhook_verified' in wa_get.json()

    # Save credentials
    wa_post = client.post(
        reverse('api-whatsapp-settings'),
        data=json.dumps({
            'phone_number_id': '109876543210123',
            'business_account_id': '209876543210123',
            'access_token': 'EAAGtesttokenwithsufficientlengthgreaterthanthirtycharacters',
            'webhook_verify_token': 'myverifytoken123',
            'app_id': '12345678901',
            'app_secret': 'mock-app-secret',
            'is_enabled': True,
        }),
        content_type='application/json'
    )
    assert wa_post.status_code == 200

    # Safe verification test
    from unittest.mock import Mock, patch
    responses=[Mock(status_code=200,json=lambda:{'id':'109876543210123','display_phone_number':'+12025550196'}),Mock(status_code=200,json=lambda:{'data':[{'id':'109876543210123'}]})]
    with patch('apps.tenants.meta_setup.requests.get',side_effect=responses):
        wa_verify = client.post(reverse('api-whatsapp-verify'))
    assert wa_verify.status_code == 200
    assert wa_verify.json()['provider_status'] == 'VERIFIED'

