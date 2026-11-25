import pytest
from django.contrib.auth.models import User
from django.test import Client
from apps.tenants.models import Tenant,TenantMembership,AccountActivationToken
pytestmark=pytest.mark.django_db

@pytest.fixture
def state():
 owner=User.objects.create_user('pending_owner',email='client@example.com',is_staff=True);owner.set_unusable_password();owner.save()
 tenant=Tenant.objects.create(name='Activation Client',slug='activation-client')
 TenantMembership.objects.create(tenant=tenant,user=owner,role='OWNER')
 admin=User.objects.create_superuser('activation_super',email='admin@example.com',password='AdminStrong123!')
 client=Client();client.force_login(admin)
 return owner,tenant,admin,client

def test_public_and_signed_in_activation_are_standalone(state):
 owner,tenant,admin,client=state;token=AccountActivationToken.create_for_user(owner)
 for c in [Client(),client]:
  r=c.get(f'/activate/{token.token}/');assert r.status_code==200
  assert b'Activate Your Account' in r.content and b'workspace-navigation' not in r.content and b'Welcome back' not in r.content and b'Platform Superadmin' not in r.content
  assert 'no-store' in r['Cache-Control']

def test_invalid_activation_has_no_dashboard(state):
 r=state[3].get('/activate/not-a-token/');assert r.status_code==400
 assert b'Activation Link Invalid' in r.content and b'Welcome back' not in r.content

def test_superadmin_generates_fresh_full_link_and_invalidates_old(state):
 owner,tenant,admin,client=state;old=AccountActivationToken.create_for_user(owner)
 response=client.post(f'/api/platform/tenants/{tenant.pk}/activation/')
 assert response.status_code==200 and response.json()['activation_url'].startswith('http://testserver/activate/')
 old.refresh_from_db();assert old.is_used and AccountActivationToken.objects.filter(user=owner,is_used=False).count()==1
 assert 'no-store' in response['Cache-Control']

def test_client_cannot_generate_activation_or_reset_active_owner(state):
 owner,tenant,admin,client=state
 outsider=User.objects.create_user('other_client',is_staff=True);TenantMembership.objects.create(tenant=tenant,user=outsider,role='STAFF');c=Client();c.force_login(outsider)
 assert c.post(f'/api/platform/tenants/{tenant.pk}/activation/').status_code==403
 owner.set_password('ExistingOwner123!');owner.save()
 assert client.post(f'/api/platform/tenants/{tenant.pk}/activation/').status_code==409
 assert not AccountActivationToken.objects.exists()

def test_admin_setting_client_password_preserves_admin_session(state):
 owner,tenant,admin,client=state;token=AccountActivationToken.create_for_user(owner)
 response=client.post(f'/activate/{token.token}/',{'password':'ClientChosenPassword981!','confirm_password':'ClientChosenPassword981!'})
 assert response.status_code==200 and b'Client account activated' in response.content
 assert int(client.session['_auth_user_id'])==admin.pk
 owner.refresh_from_db();assert owner.check_password('ClientChosenPassword981!')
 assert client.post(f'/activate/{token.token}/',{'password':'DifferentPassword123!','confirm_password':'DifferentPassword123!'}).status_code==400

def test_activation_rejects_common_password_without_consuming_token(state):
 owner,tenant,admin,client=state;token=AccountActivationToken.create_for_user(owner)
 response=Client().post(f'/activate/{token.token}/',{'password':'password','confirm_password':'password'})
 assert response.status_code==200
 token.refresh_from_db();owner.refresh_from_db();assert not token.is_used and not owner.has_usable_password()

@pytest.mark.parametrize('failure', ['missing_referer', 'bad_origin', 'bad_token'])
def test_https_activation_enforces_csrf_before_consuming_link(state,failure):
 import re
 from django.test import override_settings
 owner,tenant,admin,_=state;token=AccountActivationToken.create_for_user(owner)
 client=Client(enforce_csrf_checks=True);path=f'/activate/{token.token}/'
 with override_settings(ALLOWED_HOSTS=['testserver']):
  page=client.get(path,secure=True)
  assert b'name="referrer" content="same-origin"' in page.content
  csrf=re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"',page.content.decode()).group(1)
  payload={'csrfmiddlewaretoken':csrf,'password':'ClientChosenStrong963!','confirm_password':'ClientChosenStrong963!'}
  headers={'HTTP_REFERER':'https://testserver'+path}
  if failure=='missing_referer':headers={}
  if failure=='bad_origin':headers['HTTP_ORIGIN']='https://foreign.example'
  if failure=='bad_token':payload['csrfmiddlewaretoken']='x'*64
  result=client.post(path,payload,secure=True,**headers)
  assert result.status_code==403
  token.refresh_from_db();owner.refresh_from_db();assert not token.is_used and not owner.has_usable_password()
  payload['csrfmiddlewaretoken']=csrf
  good=client.post(path,payload,secure=True,HTTP_REFERER='https://testserver'+path)
  assert good.status_code==302
  token.refresh_from_db();owner.refresh_from_db();assert token.is_used and owner.check_password('ClientChosenStrong963!')
