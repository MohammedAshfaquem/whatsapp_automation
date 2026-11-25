"""Regressions for production audit D01–D07, exercised through actual APIs."""
import pytest
from django.contrib.auth.models import User
from django.test import Client, override_settings
from apps.tenants.models import Tenant, TenantMembership, TenantRole, PlanTier, TenantSubscription, UserSecurityProfile, AccountActivationToken
from apps.tenants.modules import MODULE_CATALOG
from apps.whatsapp.models import WhatsAppConfig
from apps.crm.models import Company, Deal, Activity, ActivityStatus
from apps.chatbot.models import Customer

pytestmark=pytest.mark.django_db

@pytest.fixture
def setup_acceptance():
 plan=PlanTier.objects.create(code='acceptance-plan',name='Acceptance plan',max_staff=7,max_contacts=42,enabled_modules=list(MODULE_CATALOG))
 tenant=Tenant.objects.create(name='Acceptance tenant',slug='acceptance-tenant')
 TenantSubscription.objects.create(tenant=tenant,effective_plan=plan,status='ACTIVE')
 owner=User.objects.create_user(username='acceptance-owner',password='OwnerOnly123!',is_staff=True)
 UserSecurityProfile.objects.create(user=owner,email_verified=True)
 TenantMembership.objects.create(tenant=tenant,user=owner,role=TenantRole.OWNER)
 admin=User.objects.create_superuser('acceptance-platform','platform@example.invalid','PlatformOnly123!')
 client=Client();client.force_login(owner)
 platform=Client();platform.force_login(admin)
 return tenant,owner,client,platform,plan

@override_settings(WHATSAPP_ACCESS_TOKEN='global-token',WHATSAPP_PHONE_NUMBER_ID='global-phone',META_APP_SECRET='global-secret',WHATSAPP_ENABLED=True)
@pytest.mark.parametrize('own_config',[False,True])
def test_tenant_provider_never_inherits_global_or_other_tenant(setup_acceptance,own_config):
 tenant,_,_,_,_=setup_acceptance
 other=Tenant.objects.create(name='Other provider',slug='other-provider')
 WhatsAppConfig.objects.create(tenant=other,is_enabled=True,access_token='other-token',phone_number_id='other-phone')
 if own_config: WhatsAppConfig.objects.create(tenant=tenant,is_enabled=False)
 config=WhatsAppConfig.get_settings(tenant=tenant)
 assert config['access_token']==''
 assert config['phone_number_id']==''
 assert config['app_secret']==''
 assert config['enabled'] is False

def test_inactive_tenant_cannot_enable_provider(setup_acceptance):
 tenant,_,_,_,_=setup_acceptance
 WhatsAppConfig.objects.create(tenant=tenant,is_enabled=True,access_token='own',phone_number_id='own')
 tenant.is_active=False;tenant.save()
 assert WhatsAppConfig.get_settings(tenant=tenant)['enabled'] is False

@override_settings(DEBUG=False)
def test_production_webhook_validator_rejects_private_without_test_environment_bypass():
 from apps.crm.webhook_service import validate_webhook_url
 for url in ['https://127.0.0.1/hook','https://169.254.169.254/hook','http://example.invalid/hook','https://example.invalid:invalid/hook']:
  safe,reason,_=validate_webhook_url(url)
  assert safe is False and reason

@pytest.mark.parametrize('path',['/api/platform/tenants/','/api/platform/clients/create/'])
def test_both_provisioning_routes_apply_selected_plan_and_owner(setup_acceptance,path):
 _,_,_,platform,plan=setup_acceptance
 r=platform.post(path,{'whatsapp_number':'+12025550191','name':'Provisioned acceptance','admin_email':'new-owner@example.invalid','plan':plan.code.upper(),'plan_code':plan.code},content_type='application/json')
 assert r.status_code==201
 tenant=Tenant.objects.get(name='Provisioned acceptance')
 assert tenant.subscription.effective_plan==plan
 assert tenant.subscription.status=='ACTIVE'
 assert tenant.effective_max_contacts==42
 member=tenant.memberships.get();assert member.role==TenantRole.OWNER
 assert not member.user.has_usable_password()
 assert r.json()['activation_url']
 if path.endswith('/clients/create/'):
  assert r.json()['activation_url'].startswith('/activate/')

@pytest.mark.parametrize('path',['/api/platform/tenants/','/api/platform/clients/create/'])
def test_invalid_plan_creates_no_tenant_or_user(setup_acceptance,path):
 _,_,_,platform,_=setup_acceptance
 before=Tenant.objects.count(),User.objects.count()
 r=platform.post(path,{'whatsapp_number':'+12025550192','name':'Invalid plan tenant','admin_email':'invalid-plan@example.invalid','plan':'nonexistent','plan_code':'nonexistent'},content_type='application/json')
 assert r.status_code==400
 assert (Tenant.objects.count(),User.objects.count())==before

def test_provision_existing_identity_preserves_password_without_activation(setup_acceptance):
 _,owner,_,platform,plan=setup_acceptance
 owner.email='existing@example.invalid';owner.save()
 before=owner.password
 r=platform.post('/api/platform/clients/create/',{'whatsapp_number':'+12025550193','name':'Existing identity workspace','admin_email':owner.email,'plan_code':plan.code},content_type='application/json')
 assert r.status_code==201
 owner.refresh_from_db();assert owner.password==before
 assert not AccountActivationToken.objects.filter(user=owner).exists()
 assert not r.json().get('activation_url')

def test_company_creation_accepts_supported_fields(setup_acceptance):
 tenant,_,client,_,_=setup_acceptance
 r=client.post('/api/crm/companies/',{'name':'Acceptance company','domain':'example.invalid'},content_type='application/json')
 assert r.status_code==201
 assert Company.objects.get(id=r.json()['company']['id']).tenant==tenant

def test_deal_creation_foreign_contact_denial_and_stage_transition(setup_acceptance):
 tenant,owner,client,_,_=setup_acceptance
 contact=Customer.objects.create(tenant=tenant,name='Own contact',phone_number='+12025550101')
 other=Tenant.objects.create(name='Foreign tenant',slug='foreign-tenant')
 foreign=Customer.objects.create(tenant=other,name='Foreign contact',phone_number='+12025550102')
 r=client.post('/api/crm/deals/',{'title':'Own deal','contact_id':contact.id,'value':'125.50'},content_type='application/json')
 assert r.status_code==201
 deal=Deal.objects.get(id=r.json()['deal']['id']);assert str(deal.amount)=='125.50'
 denied=client.post('/api/crm/deals/',{'title':'Bad deal','contact_id':foreign.id},content_type='application/json')
 assert denied.status_code==404
 board=client.get('/api/crm/deals/');assert board.status_code==200
 won=next(x for x in board.json()['stages'] if x['is_won'])
 r=client.post(f'/api/crm/deals/{deal.id}/stage/',{'stage_id':won['id']},content_type='application/json')
 assert r.status_code==200
 deal.refresh_from_db();assert deal.stage.is_won
 timeline=client.get(f'/api/crm/contacts/{contact.id}/')
 assert timeline.status_code==200
 assert any(x['event_type']=='stage_change' for x in timeline.json()['timeline']['items'])

def test_activity_completion_persists_status(setup_acceptance):
 tenant,owner,client,_,_=setup_acceptance
 activity=Activity.objects.create(tenant=tenant,title='Acceptance task',assigned_to=owner)
 r=client.post(f'/api/crm/activities/{activity.id}/complete/',{},content_type='application/json')
 assert r.status_code==200
 activity.refresh_from_db();assert activity.status==ActivityStatus.COMPLETED and activity.completed_at

def test_alternate_provisioning_preserves_requested_slug_and_contact(setup_acceptance):
 _,_,_,platform,plan=setup_acceptance
 r=platform.post('/api/platform/clients/create/',{'whatsapp_number':'+12025550194','name':'Alternate compatibility','slug':'requested-client-slug','admin_email':'alternate@example.invalid','plan_code':plan.code},content_type='application/json')
 assert r.status_code==201
 tenant=Tenant.objects.get(id=r.json()['tenant_id'])
 assert tenant.slug=='requested-client-slug'
 assert tenant.contact_email=='alternate@example.invalid'

def test_scored_contact_list_and_detail_return_numeric_score(setup_acceptance):
 from apps.crm.models import LeadScore
 tenant,_,client,_,_=setup_acceptance
 contact=Customer.objects.create(tenant=tenant,name='Scored contact',phone_number='+12025550103')
 LeadScore.objects.create(tenant=tenant,contact=contact,score=35)
 detail=client.get(f'/api/crm/contacts/{contact.id}/')
 assert detail.status_code==200 and detail.json()['contact']['lead_score']==35
 listing=client.get('/api/crm/contacts/')
 assert listing.status_code==200
 assert listing.json()['contacts'][0]['lead_score']==35
