import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
import pytest
from django.db import connection,connections
from apps.tenants.models import Tenant
from apps.chatbot.models import Customer
from apps.crm.models import Campaign,CampaignRecipient,ContactConsent,WhatsAppTemplate
from apps.crm.broadcasts import launch,run_campaigns
from apps.whatsapp.delivery import dispatch
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.whatsapp_client import WhatsAppClient
pytestmark=[pytest.mark.django_db(transaction=True),pytest.mark.skipif(connection.vendor!='postgresql',reason='Requires PostgreSQL row locks')]

@pytest.fixture
def state():
 t=Tenant.objects.create(name='Broadcast concurrency',slug='broadcast-concurrency')
 contact=Customer.objects.create(tenant=t,phone_number='+919876500222')
 ContactConsent.objects.create(tenant=t,contact=contact,has_consented=True,utility_allowed=True,evidence_text='Order updates requested')
 tpl=WhatsAppTemplate.objects.create(tenant=t,name='order_ready',body_text='Order ready',meta_status='APPROVED')
 c=Campaign.objects.create(tenant=t,name='Order ready',template=tpl)
 return t,contact,c

@pytest.fixture(autouse=True)
def config():
 with patch('apps.whatsapp.models.WhatsAppConfig.get_settings',return_value={'enabled':True,'access_token':'test','phone_number_id':'123','business_account_id':'456'}):yield

def test_simultaneous_campaign_launch_snapshot_once(state):
 t,contact,c=state;barrier=threading.Barrier(2)
 def start():
  try:
   barrier.wait(10)
   try:launch(c.pk,t);return 'launched'
   except ValueError:return 'rejected'
  finally:connections.close_all()
 with ThreadPoolExecutor(max_workers=2) as p:results=list(p.map(lambda _:start(),range(2)))
 assert sorted(results)==['launched','rejected']
 assert CampaignRecipient.objects.filter(campaign=c).count()==1

def test_pause_serializes_with_provider_transmission(state,monkeypatch):
 t,contact,c=state;launch(c.pk,t);run_campaigns();delivery=WhatsAppDelivery.objects.get()
 entered=threading.Event();release=threading.Event();paused=threading.Event()
 def provider(*a,**kw):entered.set();assert release.wait(10);return True,'wamid.campaign'
 monkeypatch.setattr(WhatsAppClient,'send_template_message',provider)
 def send():
  try:return dispatch(delivery.pk)
  finally:connections.close_all()
 def pause():
  try:
   from django.db import transaction
   with transaction.atomic():
    record=Campaign.objects.select_for_update().get(pk=c.pk);record.status='PAUSED';record.save()
  finally:paused.set();connections.close_all()
 with ThreadPoolExecutor(max_workers=2) as p:
  sent=p.submit(send);assert entered.wait(10);waiting=p.submit(pause)
  try:assert not paused.wait(.3),'Pause completed during provider I/O'
  finally:release.set()
  assert sent.result(15);waiting.result(15)
 c.refresh_from_db();delivery.refresh_from_db();assert c.status=='PAUSED' and delivery.status=='SENT'
