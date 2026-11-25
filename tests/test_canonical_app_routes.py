import pytest
from django.contrib.auth.models import User
from apps.tenants.models import Tenant,TenantMembership

@pytest.fixture
def identities(db):
    owner=User.objects.create_user('route_owner',password='RouteOwner123!',is_staff=True)
    root=User.objects.create_superuser('route_root','root@example.test','RouteRoot123!')
    tenant=Tenant.objects.create(name='Route client',slug='route-client')
    TenantMembership.objects.create(user=owner,tenant=tenant,role='OWNER')
    return owner,root,tenant

def test_login_routes_to_one_role_specific_app(client,identities):
    for user,password,url in [(identities[0],'RouteOwner123!','/app/dashboard'),(identities[1],'RouteRoot123!','/app/platform/dashboard')]:
        client.logout();response=client.post('/login/',{'username':user.username,'password':password})
        assert response.status_code==302 and response.url==url

@pytest.mark.parametrize('path,target',[('/dashboard/','/app/dashboard'),('/','/app/dashboard'),('/crm/contacts/','/app/contacts'),('/crm/deals/','/app/deals'),('/crm/settings/','/app/settings')])
def test_client_old_pages_redirect_without_rendering_old_dashboard(client,identities,path,target):
    client.force_login(identities[0]);response=client.get(path)
    assert response.status_code==302 and response.url==target

@pytest.mark.parametrize('path,target',[('/dashboard/','/app/platform/dashboard'),('/','/app/platform/dashboard'),('/platform/','/app/platform/dashboard'),('/platform/tenants/','/app/platform/tenants'),('/platform/access-matrix/','/app/platform/matrix'),('/platform/audit/','/app/platform/audit')])
def test_super_admin_old_pages_use_one_console(client,identities,path,target):
    client.force_login(identities[1]);response=client.get(path)
    assert response.status_code==302 and response.url==target

def test_cross_role_next_and_external_next_are_not_login_destinations(client,identities):
    for next_path in ['/app/platform/dashboard','https://evil.example/steal','/admin/']:
        client.logout();response=client.post('/login/?next='+next_path,{'username':identities[0].username,'password':'RouteOwner123!'})
        assert response.url=='/app/dashboard'

def test_public_home_has_no_provider_badge_or_admin_menu(client,db):
    response=client.get('/')
    assert response.status_code==200
    assert b'Official Meta Cloud API &amp; Gemini AI Workspace' not in response.content
    assert b'Official Meta Cloud API & Gemini AI Workspace' not in response.content
    assert b'href="/admin/"' not in response.content


def test_login_get_exits_stale_operator_inspection(client,identities):
    client.force_login(identities[1])
    session=client.session;session['active_tenant_id']=identities[2].pk;session['inspecting_tenant_id']=identities[2].pk;session.save()
    response=client.get('/login/')
    assert response.url=='/app/platform/dashboard'
    assert 'inspecting_tenant_id' not in client.session and 'active_tenant_id' not in client.session
@pytest.mark.django_db
def test_consumer_portal_login_preserved(client):
    from apps.chatbot.models import Customer
    user=User.objects.create_user('portal_route_user',password='PortalRoute!Pass123')
    Customer.objects.create(user=user,name='Portal consumer',phone_number='+12025550178')
    response=client.post('/login/',{'username':user.username,'password':'PortalRoute!Pass123'})
    assert response.status_code==302 and response.url=='/dashboard/'
    assert client.get('/login/').url=='/dashboard/'
@pytest.mark.django_db
def test_unverified_onboarding_and_account_keep_canonical_access(client,identities):
    from apps.tenants.models import UserSecurityProfile
    user=identities[0];profile=UserSecurityProfile.get_or_create_for_user(user);profile.email_verified=False;profile.save()
    client.force_login(user)
    assert client.get('/app/onboarding').status_code==200
    assert client.get('/app/account').status_code==200
    assert client.get('/api/auth/bootstrap/').status_code==200
    assert client.get('/crm/contacts/').status_code==302
def test_authenticated_client_login_uses_canonical_entry(client,identities):
    client.force_login(identities[0]);response=client.get('/login/')
    assert response.status_code==302 and response.url=='/app/dashboard'
