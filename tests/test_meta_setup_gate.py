import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from apps.tenants.models import Tenant, TenantSubscription, SubscriptionStatus
from apps.whatsapp.models import WhatsAppConfig

pytestmark = pytest.mark.django_db

def test_new_workspace_requires_actual_verified_meta():
    from apps.tenants.meta_setup import meta_setup_state
    tenant = Tenant.objects.create(name='New', slug='new', requires_meta_setup=True, whatsapp_number='+919876543210')
    assert meta_setup_state(tenant)['ready'] is False
    TenantSubscription.objects.create(tenant=tenant, status=SubscriptionStatus.ACTIVE)
    config = WhatsAppConfig.objects.create(tenant=tenant, is_enabled=True, phone_number_id='1234567890', business_account_id='9876543210', access_token='token', verify_token='verify', app_id='123', app_secret='secret')
    assert meta_setup_state(tenant)['ready'] is False

def test_legacy_workspace_does_not_require_setup():
    from apps.tenants.meta_setup import meta_setup_state
    tenant = Tenant.objects.create(name='Legacy', slug='legacy')
    assert meta_setup_state(tenant)['required'] is False

def test_verification_checks_waba_membership_and_expected_number(monkeypatch):
    from apps.tenants.meta_setup import verify_meta_connection, meta_setup_state
    tenant = Tenant.objects.create(name='Verified', slug='verified', requires_meta_setup=True, whatsapp_number='+919876543210')
    TenantSubscription.objects.create(tenant=tenant, status=SubscriptionStatus.ACTIVE)
    config = WhatsAppConfig.objects.create(tenant=tenant, is_enabled=True, phone_number_id='1234567890', business_account_id='9876543210', access_token='token', verify_token='verify', app_id='123', app_secret='secret')
    class Response:
        status_code = 200
        def __init__(self, data): self.data = data
        def json(self): return self.data
    responses = iter([Response({'id': config.phone_number_id, 'display_phone_number': '+91 98765 43210'}), Response({'data': [{'id': config.phone_number_id}]})])
    monkeypatch.setattr('apps.tenants.meta_setup.requests.get', lambda *a, **k: next(responses))
    verify_meta_connection(tenant, config)
    config.refresh_from_db()
    assert config.connection_verified_at
    assert meta_setup_state(tenant)['ready'] is True
    config.access_token = 'changed'
    config.save()
    assert config.connection_verified_at is None
@pytest.mark.parametrize('phone,waba_rows', [('+91 11111 11111', [{'id': '1234567890'}]), ('+91 98765 43210', [{'id': 'other'}])])
def test_verification_rejects_wrong_number_or_account(monkeypatch, phone, waba_rows):
    from apps.tenants.meta_setup import verify_meta_connection
    tenant = Tenant.objects.create(name='Mismatch', slug='mismatch', requires_meta_setup=True, whatsapp_number='+919876543210')
    TenantSubscription.objects.create(tenant=tenant, status=SubscriptionStatus.ACTIVE)
    config = WhatsAppConfig.objects.create(tenant=tenant, is_enabled=True, phone_number_id='1234567890', business_account_id='9876543210', access_token='token', verify_token='verify', app_id='123', app_secret='secret')
    class Response:
        status_code = 200
        def __init__(self, data): self.data = data
        def json(self): return self.data
    responses = iter([Response({'id': config.phone_number_id, 'display_phone_number': phone}), Response({'data': waba_rows})])
    monkeypatch.setattr('apps.tenants.meta_setup.requests.get', lambda *a, **k: next(responses))
    with pytest.raises(ValueError): verify_meta_connection(tenant, config)
    config.refresh_from_db()
    assert config.connection_verified_at is None

@pytest.mark.parametrize('path,blocked', [('/api/crm/overview/', True), ('/dashboard/', True), ('/app/inbox', True), ('/api/settings/whatsapp/', False), ('/api/auth/bootstrap/', False), ('/api/onboarding/status/', False), ('/api/whatsapp/webhook/', False), ('/app/account', False), ('/admin/password_change/', False)])
def test_setup_gate_blocks_modules_and_preserves_setup(path, blocked):
    from apps.tenants.middleware import TenantMiddleware
    request = RequestFactory().get(path)
    request.user = User.objects.create_user(username='owner')
    request.tenant = Tenant.objects.create(name='Gated', slug='gated', requires_meta_setup=True)
    response = TenantMiddleware(lambda r: None).process_view(request, lambda r: None, (), {})
    assert (response is not None) is blocked
    if blocked:
        assert response.status_code == (403 if path.startswith('/api/') else 302)

@pytest.mark.parametrize('number', ['', '919876543210', '+01234567890', 'invalid'])
def test_provisioning_rejects_missing_or_invalid_whatsapp_number(number):
    import json
    from apps.tenants.spa_api import platform_tenants_api
    request = RequestFactory().post('/api/platform/tenants/', data=json.dumps({'name':'Client', 'whatsapp_number':number}), content_type='application/json')
    request.user = User.objects.create_superuser(username='super', email='super@example.com', password='secret')
    response = platform_tenants_api(request)
    assert response.status_code == 400
    assert not Tenant.objects.filter(name='Client').exists()
@pytest.mark.parametrize('route', ['api-platform-tenants', 'api-platform-clients-create'])
def test_new_client_provisioning_requires_unique_number_and_client_owner(client, route):
    from django.urls import reverse
    from apps.tenants.models import PlanTier
    PlanTier.objects.get_or_create(code='basic', defaults={'name':'Basic'})
    superuser = User.objects.create_superuser(username='super', email='super@example.com', password='secret')
    client.force_login(superuser)
    payload = {'name':'Client', 'admin_email':'client@example.com', 'whatsapp_number':'+919876543210'}
    response = client.post(reverse(route), payload, content_type='application/json')
    assert response.status_code == 201
    tenant = Tenant.objects.get(name='Client')
    assert tenant.requires_meta_setup is True
    assert tenant.whatsapp_number == payload['whatsapp_number']
    payload.update(name='Duplicate', admin_email='other@example.com')
    assert client.post(reverse(route), payload, content_type='application/json').status_code == 409
    payload.update(name='Bad owner', whatsapp_number='+919876543211', admin_email='super@example.com')
    assert client.post(reverse(route), payload, content_type='application/json').status_code == 400
    assert not Tenant.objects.filter(name='Bad owner').exists()

def test_verify_checks_paginated_waba_number_list(monkeypatch):
    from apps.tenants.meta_setup import verify_meta_connection
    tenant = Tenant.objects.create(name='Paged', slug='paged', requires_meta_setup=True, whatsapp_number='+919876543210')
    TenantSubscription.objects.create(tenant=tenant, status=SubscriptionStatus.ACTIVE)
    config = WhatsAppConfig.objects.create(tenant=tenant, is_enabled=True, phone_number_id='1234567890', business_account_id='9876543210', access_token='token', verify_token='verify', app_id='123', app_secret='secret')
    class Response:
        status_code = 200
        def __init__(self, data): self.data = data
        def json(self): return self.data
    responses = iter([Response({'id': config.phone_number_id, 'display_phone_number': '+91 98765 43210'}), Response({'data': [], 'paging': {'next':'https://untrusted.example/?token=secret', 'cursors': {'after':'cursor'}}}), Response({'data': [{'id':config.phone_number_id}]})])
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return next(responses)
    monkeypatch.setattr('apps.tenants.meta_setup.requests.get', get)
    assert verify_meta_connection(tenant, config)['ready'] is True
    assert calls[-1][0].startswith('https://graph.facebook.com/')
    assert calls[-1][1]['params']['after'] == 'cursor'
    assert all(call[1]['allow_redirects'] is False for call in calls)


def test_unverified_new_client_cannot_enable_worker_sends():
    tenant = Tenant.objects.create(name='Worker', slug='worker', requires_meta_setup=True)
    TenantSubscription.objects.create(tenant=tenant, status=SubscriptionStatus.ACTIVE)
    WhatsAppConfig.objects.create(tenant=tenant, is_enabled=True, phone_number_id='123', access_token='token')
    assert WhatsAppConfig.get_settings(tenant)['enabled'] is False

def test_verification_does_not_stamp_changed_credentials(monkeypatch):
    from apps.tenants.meta_setup import verify_meta_connection
    tenant = Tenant.objects.create(name='Race', slug='race', requires_meta_setup=True, whatsapp_number='+919876543210')
    TenantSubscription.objects.create(tenant=tenant, status=SubscriptionStatus.ACTIVE)
    config = WhatsAppConfig.objects.create(tenant=tenant, is_enabled=True, phone_number_id='1234567890', business_account_id='9876543210', access_token='token', verify_token='verify', app_id='123', app_secret='secret')
    class Response:
        status_code = 200
        def __init__(self, data): self.data = data
        def json(self): return self.data
    def get(url, **kwargs):
        if url.endswith('/phone_numbers'):
            WhatsAppConfig.objects.filter(pk=config.pk).update(access_token='changed-concurrently')
            return Response({'data': [{'id':config.phone_number_id}]})
        return Response({'id':config.phone_number_id, 'display_phone_number':'+919876543210'})
    monkeypatch.setattr('apps.tenants.meta_setup.requests.get', get)
    with pytest.raises(ValueError, match='changed'): verify_meta_connection(tenant, config)
    config.refresh_from_db()
    assert config.connection_verified_at is None
    assert config.access_token == 'changed-concurrently'

def test_database_rejects_duplicate_assigned_whatsapp_numbers():
    from django.db import IntegrityError, transaction
    Tenant.objects.create(name='First number', slug='first-number', whatsapp_number='+919876543210')
    with pytest.raises(IntegrityError), transaction.atomic():
        Tenant.objects.create(name='Duplicate number', slug='duplicate-number', whatsapp_number='+919876543210')
    Tenant.objects.create(name='Blank one', slug='blank-one')
    Tenant.objects.create(name='Blank two', slug='blank-two')

@pytest.mark.parametrize('field', ['phone_number_id', 'business_account_id'])
def test_database_rejects_duplicate_provider_claims(field):
    from django.db import IntegrityError, transaction
    first = Tenant.objects.create(name='First provider', slug='first-provider')
    second = Tenant.objects.create(name='Second provider', slug='second-provider')
    WhatsAppConfig.objects.create(tenant=first, **{field:'123456789'})
    with pytest.raises(IntegrityError), transaction.atomic():
        WhatsAppConfig.objects.create(tenant=second, **{field:'123456789'})

def test_provisioning_integrity_race_returns_conflict_without_partial_client(client, monkeypatch):
    from django.db import IntegrityError
    from django.urls import reverse
    from apps.tenants.models import PlanTier
    PlanTier.objects.get_or_create(code='basic', defaults={'name':'Basic'})
    superuser = User.objects.create_superuser(username='super-race', email='super-race@example.com', password='secret')
    client.force_login(superuser)
    def race(**kwargs): raise IntegrityError('concurrent unique claim')
    monkeypatch.setattr(Tenant.objects, 'create', race)
    response = client.post(reverse('api-platform-tenants'), {'name':'Raced client', 'admin_email':'raced@example.com', 'whatsapp_number':'+919876543210'}, content_type='application/json')
    assert response.status_code == 409
    assert not Tenant.objects.filter(name='Raced client').exists()
    assert not User.objects.filter(email='raced@example.com').exists()
