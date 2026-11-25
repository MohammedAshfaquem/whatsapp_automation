import json
import pytest
from django.contrib.auth.models import User
from apps.tenants.models import Tenant,TenantMembership

@pytest.mark.django_db
def test_platform_context_cannot_read_client_configuration_without_inspection(client):
    user=User.objects.create_superuser('separated_root','root@example.com','test-password')
    client.force_login(user)
    assert client.get('/api/settings/whatsapp/').status_code == 403

@pytest.mark.django_db
def test_client_cannot_access_platform_pages_or_apis(client):
    user=User.objects.create_user('separated_owner',is_staff=True)
    tenant=Tenant.objects.create(name='Separated',slug='separated')
    TenantMembership.objects.create(user=user,tenant=tenant,role='OWNER')
    client.force_login(user)
    assert client.get('/api/platform/metrics/').status_code==403
    response=client.get('/app/platform/dashboard')
    assert response.status_code in (302,403)

@pytest.mark.django_db
def test_account_profile_edits_only_authenticated_identity(client):
    user=User.objects.create_user('account_owner',email='old@example.com',is_staff=True)
    tenant=Tenant.objects.create(name='Account',slug='account')
    TenantMembership.objects.create(user=user,tenant=tenant,role='OWNER')
    client.force_login(user)
    response=client.post('/api/auth/profile/',json.dumps({'full_name':'Neoriz Solutions','email':'neorizsolutions@gmail.com','is_superuser':True}),content_type='application/json')
    assert response.status_code==400
    response=client.post('/api/auth/profile/',json.dumps({'full_name':'Neoriz Solutions','email':'neorizsolutions@gmail.com'}),content_type='application/json')
    assert response.status_code==200
    user.refresh_from_db();assert user.get_full_name()=='Neoriz Solutions'
    assert user.email=='neorizsolutions@gmail.com' and not user.is_superuser
    from apps.tenants.models import UserSecurityProfile
    assert not UserSecurityProfile.objects.get(user=user).email_verified
    assert response.json()['email_verification_required'] is True
@pytest.mark.django_db
def test_operations_accepts_empty_optional_tenant_filter(client):
    user=User.objects.create_superuser('blank_filter_root','r@example.com','test-password')
    client.force_login(user)
    assert client.get('/api/platform/operations/users/?tenant_id=&status=&q=').status_code==200
@pytest.mark.django_db
def test_client_can_save_meta_app_fields_without_reading_secret(client):
    from apps.whatsapp.models import WhatsAppConfig
    user=User.objects.create_user('meta_app_owner',is_staff=True)
    tenant=Tenant.objects.create(name='Meta app',slug='meta-app')
    TenantMembership.objects.create(user=user,tenant=tenant,role='OWNER')
    client.force_login(user)
    response=client.post('/api/settings/whatsapp/',json.dumps({'phone_number_id':'123456','app_id':'1802551157753417','app_secret':'private-test-secret','is_enabled':False}),content_type='application/json')
    assert response.status_code==200
    cfg=WhatsAppConfig.objects.get(tenant=tenant)
    assert cfg.app_id=='1802551157753417' and cfg.app_secret=='private-test-secret' and not cfg.is_enabled
    data=client.get('/api/settings/whatsapp/').json()
    assert data['app_id']=='1802551157753417' and data['app_secret_present'] is True
    assert 'private-test-secret' not in json.dumps(data)
