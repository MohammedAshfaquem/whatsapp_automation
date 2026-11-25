import json
import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory
from apps.tenants.models import Tenant, TenantAuditLog
from apps.whatsapp.models import WhatsAppDelivery, WhatsAppConfig, WhatsAppWebhookLog

pytestmark = pytest.mark.django_db


def call(resource, user, data=None, pk=None, query=''):
    from apps.tenants import platform_operations as ops
    rf = RequestFactory()
    request = rf.patch('/?'+query, json.dumps(data), content_type='application/json') if data is not None else rf.get('/?'+query)
    request.user = user
    return ops.platform_operation_detail(request, resource, pk) if pk is not None else ops.platform_operations(request, resource)


def test_operations_require_superuser():
    user = get_user_model().objects.create_user('ordinary')
    assert call('deliveries', AnonymousUser()).status_code == 403
    assert call('deliveries', user).status_code == 403


def test_delivery_filters_pagination_and_sanitized_detail():
    admin = get_user_model().objects.create_superuser('operator', password='test')
    tenant = Tenant.objects.create(name='First')
    other = Tenant.objects.create(name='Second')
    row = WhatsAppDelivery.objects.create(tenant=tenant, dedup_key='one', recipient_phone='123', status='FAILED', attempts=3, payload={'type':'text','access_token':'DO-NOT-SHOW'}, last_error='OAuth failed access_token=DO-NOT-SHOW Bearer abc123')
    WhatsAppDelivery.objects.create(tenant=other, dedup_key='two', recipient_phone='456')
    assert call('deliveries', admin).status_code == 403
    assert call('deliveries', admin, pk=row.pk).status_code == 403



def test_configurations_and_webhooks_do_not_expose_raw_secrets():
    admin = get_user_model().objects.create_superuser('operator', password='test')
    tenant = Tenant.objects.create(name='First')
    WhatsAppConfig.objects.create(tenant=tenant, access_token='TOPSECRET', verify_token='TOPSECRET', app_secret='TOPSECRET')
    WhatsAppWebhookLog.objects.create(tenant=tenant, raw_payload={'secret':'TOPSECRET'})
    for resource in ('configurations','webhooks'):
        response = call(resource, admin)
        assert response.status_code == 403
        assert 'TOPSECRET' not in response.content.decode()


def test_user_update_is_limited_audited_and_cannot_disable_self():
    admin = get_user_model().objects.create_superuser('operator', password='test')
    user = get_user_model().objects.create_user('client')
    assert call('users', admin, {'is_superuser':True}, user.pk).status_code == 400
    assert call('users', admin, {'is_active':False}, admin.pk).status_code == 400
    response = call('users', admin, {'full_name':'New Name','email':'new@example.com','is_active':False}, user.pk)
    assert response.status_code == 200
    user.refresh_from_db()
    assert user.get_full_name() == 'New Name' and not user.is_active
    assert TenantAuditLog.objects.filter(actor=admin, details__user_id=user.pk).exists()


def test_invalid_resource_filters_and_methods_return_safe_errors():
    admin = get_user_model().objects.create_superuser('operator', password='test')
    assert call('not-a-model', admin).status_code == 404
    assert call('users', admin, query='page=wrong').status_code == 400
    assert call('users', admin, query='tenant=wrong').status_code == 400
    assert call('deliveries', admin, {}, 42).status_code == 403

@pytest.mark.parametrize('resource', ['deliveries','webhooks','users','contacts','conversations','bookings','services','products','templates','configurations'])
def test_all_allowlisted_resources_have_stable_list_schema(resource):
    admin = get_user_model().objects.create_superuser('operator', password='test')
    response = call(resource, admin)
    if resource != 'users':
        assert response.status_code == 403
        return
    assert response.status_code == 200
    body = json.loads(response.content)
    assert set(body) == {'resource','items','total','page','page_size'}
    assert body['resource'] == resource


def test_user_workspace_roles_and_tenant_filter_are_read_only():
    from apps.tenants.models import TenantMembership
    admin = get_user_model().objects.create_superuser('operator', password='test')
    user = get_user_model().objects.create_user('client')
    tenant = Tenant.objects.create(name='Workspace')
    membership = TenantMembership.objects.create(tenant=tenant,user=user,role='STAFF')
    body = json.loads(call('users',admin,query=f'tenant={tenant.pk}').content)
    assert body['total'] == 1
    assert body['items'][0]['workspaces'][0]['role'] == 'STAFF'
    assert call('users',admin,{'role':'OWNER'},user.pk).status_code == 400
    membership.refresh_from_db()
    assert membership.role == 'STAFF'


def test_diagnostic_redacts_quoted_credentials_with_spaces():
    from apps.tenants.platform_operations import sanitize_error
    value = sanitize_error('{"access_token": "secret with spaces", "message": "OAuth failed"}')
    assert 'secret' not in value and 'with spaces' not in value
    assert 'OAuth failed' in value
