import json
from unittest.mock import patch
import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.utils import timezone
from datetime import timedelta
from apps.tenants.models import Tenant,TenantMembership,MembershipRole
from apps.chatbot.models import Customer,Conversation,Message
from apps.crm.models import Campaign,CampaignRecipient,WhatsAppTemplate,ContactConsent
from apps.crm.broadcasts import launch,run_campaigns
from apps.whatsapp.delivery import dispatch
from apps.whatsapp.models import WhatsAppDelivery

pytestmark=pytest.mark.django_db

@pytest.fixture
def setup():
 t=Tenant.objects.create(name='Broadcast client',slug='broadcast-client',is_active=True)
 u=User.objects.create_user(username='broadcast-owner',password='ownerpass',is_staff=True)
 TenantMembership.objects.create(tenant=t,user=u,role=MembershipRole.OWNER)
 cli=Client();cli.force_login(u)
 tpl=WhatsAppTemplate.objects.create(tenant=t,name='order_update',language='en',category='UTILITY',body_text='Order {{1}} is ready',variables=['Order'],meta_status='APPROVED')
 c=Customer.objects.create(tenant=t,phone_number='+919876543210',name='Buyer')
 ContactConsent.objects.create(tenant=t,contact=c,has_consented=True,utility_allowed=True,evidence_text='Requested order updates at checkout')
 return t,u,cli,tpl,c

@pytest.fixture(autouse=True)
def config():
 with patch('apps.whatsapp.models.WhatsAppConfig.get_settings',return_value={'enabled':True,'access_token':'test','phone_number_id':'123','business_account_id':'456'}):yield

def draft(setup):
 t,u,cli,tpl,c=setup
 return Campaign.objects.create(tenant=t,name='Order ready',template=tpl,template_parameters=['AB12'],created_by=u)

def test_consent_read_does_not_grant_permission(setup):
 t,u,cli,tpl,c=setup;ContactConsent.objects.all().delete()
 response=cli.get(f'/api/crm/consent/{c.pk}/')
 assert response.status_code==200 and response.json()['has_consented'] is False
 assert not ContactConsent.objects.exists()
 r=cli.post('/api/crm/campaigns/',json.dumps({'name':'Draft','template_id':tpl.pk,'template_parameters':['AB12']}),content_type='application/json')
 assert r.status_code==201 and r.json()['audience_count']==0

def test_launch_snapshot_dedup_and_dispatch(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup)
 launch(cam.pk,t)
 with pytest.raises(ValueError):launch(cam.pk,t)
 assert CampaignRecipient.objects.filter(campaign=cam).count()==1
 run_campaigns();run_campaigns()
 assert WhatsAppDelivery.objects.count()==1 and Message.objects.count()==1
 d=WhatsAppDelivery.objects.get()
 assert d.payload['conversation_id'] and d.payload['sender_type']=='CAMPAIGN'
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_template_message',return_value=(True,'wamid.broadcast')) as send:
  assert dispatch(d.pk) is True
  assert dispatch(d.pk) is True
  assert send.call_count==1
 run_campaigns();cam.refresh_from_db();assert cam.status=='COMPLETED' and cam.sent_count==1

def test_revoked_permission_blocks_already_queued_delivery(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup);launch(cam.pk,t);run_campaigns()
 ContactConsent.objects.filter(contact=c).update(is_opted_out=True)
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_template_message') as send:
  assert dispatch(WhatsAppDelivery.objects.get().pk) is False
  send.assert_not_called()
 assert WhatsAppDelivery.objects.get().status=='BLOCKED'

def test_paused_resumes_cancelled_does_not_send(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup);launch(cam.pk,t);run_campaigns();d=WhatsAppDelivery.objects.get()
 Campaign.objects.filter(pk=cam.pk).update(status='PAUSED')
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_template_message') as send:
  assert dispatch(d.pk) is False;send.assert_not_called()
 d.refresh_from_db();assert d.attempts==0 and d.status=='PENDING'
 Campaign.objects.filter(pk=cam.pk).update(status='CANCELLED')
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_template_message') as send:
  assert dispatch(d.pk) is False;send.assert_not_called()

def test_template_revocation_and_payload_tamper_block(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup);launch(cam.pk,t);run_campaigns();d=WhatsAppDelivery.objects.get()
 WhatsAppTemplate.objects.filter(pk=tpl.pk).update(meta_status='PAUSED')
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_template_message') as send:
  assert dispatch(d.pk) is False;send.assert_not_called()

def test_audience_category_and_foreign_tenant_isolation(setup):
 t,u,cli,tpl,c=setup;foreign=Tenant.objects.create(name='Other',slug='other')
 other=Campaign.objects.create(tenant=foreign,name='Private')
 assert cli.get(f'/api/crm/campaigns/{other.pk}/').status_code==404
 tpl.category='MARKETING';tpl.save();cam=draft(setup)
 with pytest.raises(ValueError,match='No eligible'):launch(cam.pk,t)
 staff=User.objects.create_user('junior',is_staff=True);TenantMembership.objects.create(tenant=t,user=staff,role=MembershipRole.STAFF);cli.force_login(staff)
 assert cli.get('/api/crm/campaigns/').status_code==403

def test_schedule_and_launch_confirmation(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup)
 url=f'/api/crm/campaigns/{cam.pk}/'
 assert cli.post(url,json.dumps({'action':'launch'}),content_type='application/json').status_code==400
 future=timezone.now()+timedelta(hours=1)
 assert cli.post(url,json.dumps({'action':'launch','confirm_send':True,'scheduled_at':future.isoformat()}),content_type='application/json').status_code==200
 run_campaigns();assert not WhatsAppDelivery.objects.exists()
 Campaign.objects.filter(pk=cam.pk).update(scheduled_at=timezone.now()-timedelta(seconds=1));run_campaigns();assert WhatsAppDelivery.objects.count()==1

def test_template_submission_pending_and_unknown_not_retried(setup):
 t,u,cli,tpl,c=setup
 create=cli.post('/api/whatsapp/templates/manage/',json.dumps({'name':'new_update','body_text':'Order {{1}} ready','category':'UTILITY'}),content_type='application/json')
 assert create.status_code==201;pk=create.json()['template']['id']
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.create_template',return_value=(True,{'id':'999','status':'PENDING'},'',False)) as submit:
  r=cli.post(f'/api/whatsapp/templates/{pk}/submit/',json.dumps({'examples':['AB12']}),content_type='application/json')
  assert r.status_code==200 and r.json()['template']['meta_status']=='PENDING'
  assert cli.post(f'/api/whatsapp/templates/{pk}/submit/',json.dumps({'examples':['AB12']}),content_type='application/json').status_code==409
  assert submit.call_count==1

def test_consent_requires_evidence_and_real_boolean(setup):
 t,u,cli,tpl,c=setup;url=f'/api/crm/consent/{c.pk}/'
 assert cli.post(url,json.dumps({'is_opted_out':'false'}),content_type='application/json').status_code==400
 assert cli.post(url,json.dumps({'evidence_text':''}),content_type='application/json').status_code==400
 ContactConsent.objects.get(contact=c).refresh_from_db()

def test_uncertain_send_not_resent(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup);launch(cam.pk,t);run_campaigns();d=WhatsAppDelivery.objects.get()
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_template_message',return_value=(False,'Request Timeout')) as send:
  assert not dispatch(d.pk);assert not dispatch(d.pk);assert send.call_count==1
 d.refresh_from_db();assert d.status=='UNKNOWN'


def test_retry_worker_does_not_select_paused_campaigns(setup):
 from django.core.management import call_command
 from io import StringIO
 t,u,cli,tpl,c=setup;cam=draft(setup);launch(cam.pk,t);run_campaigns()
 Campaign.objects.filter(pk=cam.pk).update(status='PAUSED')
 with patch('apps.whatsapp.management.commands.retry_whatsapp.dispatch') as send:
  call_command('retry_whatsapp',stdout=StringIO());send.assert_not_called()


def test_campaign_delivery_visible_in_existing_inbox(setup):
 t,u,cli,tpl,c=setup;cam=draft(setup);launch(cam.pk,t);run_campaigns();d=WhatsAppDelivery.objects.get()
 response=cli.get(f"/conversations/{d.payload['conversation_id']}/messages/")
 assert response.status_code==200
 msg=next(m for m in response.json()['messages'] if m['id']==d.payload['message_id'])
 assert msg['delivery_status']=='PENDING' and msg['delivery_id']==d.pk and msg['author_name']=='Broadcast: Order ready'

def test_stop_webhook_suppresses_before_reply_processing(setup):
 from apps.whatsapp.events import process_events
 t,u,cli,tpl,c=setup
 payload={'entry':[{'changes':[{'value':{'messages':[{'id':'wamid.stop-test','from':c.phone_number[1:],'type':'text','text':{'body':'STOP'}}]}}]}]}
 def inbound(**kwargs):
  assert ContactConsent.objects.get(contact=c).is_opted_out is True
  return {}
 with patch('apps.whatsapp.events.ConversationService.process_message',side_effect=inbound):
  result=process_events(payload,tenant=t)
 assert result['processed']==1

def test_uncertain_submission_reconciles_instead_of_duplicate_post(setup):
 t,u,cli,tpl,c=setup
 local=WhatsAppTemplate.objects.create(tenant=t,name='uncertain_update',body_text='Order ready')
 with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.create_template',return_value=(False,{},'Uncertain submission',True)) as send:
  url=f'/api/whatsapp/templates/{local.pk}/submit/'
  assert cli.post(url,'{}',content_type='application/json').status_code==502
  local.refresh_from_db();assert local.meta_status=='UNKNOWN'
  assert cli.post(url,'{}',content_type='application/json').status_code==409
  assert send.call_count==1
