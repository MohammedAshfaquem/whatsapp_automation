import json,os,threading,multiprocessing
from concurrent.futures import ThreadPoolExecutor
import pytest
from django.contrib.auth.models import User
from django.db import connection,connections
from django.test import Client
from apps.tenants.models import Tenant,TenantMembership
from apps.chatbot.models import Customer,Conversation,Message
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.delivery import dispatch
from apps.whatsapp.whatsapp_client import WhatsAppClient

pytestmark=[pytest.mark.django_db(transaction=True),pytest.mark.skipif(connection.vendor!='postgresql',reason='Requires PostgreSQL row locks; verified in isolated release database')]

@pytest.fixture
def state():
    user=User.objects.create_user('concurrency_owner',is_staff=True)
    t=Tenant.objects.create(name='Concurrency',slug='concurrency')
    TenantMembership.objects.create(tenant=t,user=user,role='OWNER')
    c=Customer.objects.create(tenant=t,phone_number='+919876500222')
    conv=Conversation.objects.create(tenant=t,customer=c,channel='WHATSAPP',status='BOT_ACTIVE')
    Message.objects.create(conversation=conv,direction='INBOUND',sender_type='CUSTOMER',message_text='Hello')
    return user,t,c,conv

def client_for(user):
    client=Client();client.force_login(user);return client

def test_takeover_waits_for_already_inflight_provider_and_then_completes(state,monkeypatch):
    u,t,c,conv=state;client=client_for(u)
    delivery=WhatsAppDelivery.objects.create(tenant=t,dedup_key='reply:serialized',recipient_phone=c.phone_number,payload={'text':'Bot','conversation_id':conv.pk,'sender_type':'BOT'})
    accepted=threading.Event();release=threading.Event();done=threading.Event();calls=[]
    def provider(**kw):
        calls.append(1);accepted.set();assert release.wait(10);return True,'wamid.stub'
    monkeypatch.setattr(WhatsAppClient,'send_text_message',provider)
    def send():
        try:return dispatch(delivery.pk)
        finally:connections.close_all()
    def takeover():
        try:return client.post(f'/conversations/{conv.pk}/action/',{'action':'switch_to_human'}).status_code
        finally:done.set();connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:
        sending=pool.submit(send);assert accepted.wait(10)
        human=pool.submit(takeover)
        try:
            assert not done.wait(.4),'Takeover committed while provider dispatch held the gate'
        finally:release.set()
        assert sending.result(timeout=15);assert human.result(timeout=15)==200
    conv.refresh_from_db();delivery.refresh_from_db()
    assert conv.status=='HUMAN_HANDOVER';assert delivery.status=='SENT';assert len(calls)==1

def test_simultaneous_new_chat_resolves_one_conversation(state):
    u,t,c,conv=state
    clients=[client_for(u),client_for(u)];barrier=threading.Barrier(2)
    def create(client):
        try:
            barrier.wait(timeout=10)
            return client.post('/api/inbox/conversations/start/',json.dumps({'contact_id':c.pk,'channel':'SIMULATED'}),content_type='application/json').status_code
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(create,clients))
    assert statuses==[200,200]
    assert Conversation.objects.filter(tenant=t,customer=c,channel='SIMULATED').count()==1

def test_simultaneous_retry_sends_only_once(state,monkeypatch):
    u,t,c,conv=state;conv.status='HUMAN_HANDOVER';conv.assigned_staff=u;conv.save()
    delivery=WhatsAppDelivery.objects.create(tenant=t,dedup_key='retry:serialized',recipient_phone=c.phone_number,status='FAILED',attempts=1,payload={'text':'Human','conversation_id':conv.pk,'sender_type':'HUMAN'})
    calls=[];monkeypatch.setattr(WhatsAppClient,'send_text_message',lambda **kw:(calls.append(1) or (True,'wamid.stub')))
    clients=[client_for(u),client_for(u)];barrier=threading.Barrier(2)
    def retry(client):
        try:barrier.wait(timeout=10);return client.post(f'/api/inbox/delivery/{delivery.pk}/retry/').status_code
        finally:connections.close_all()
    with ThreadPoolExecutor(max_workers=2) as pool:statuses=list(pool.map(retry,clients))
    assert statuses.count(200)==1;assert all(code in [200,400,409] for code in statuses)
    delivery.refresh_from_db();assert delivery.attempts==2;assert len(calls)==1

def test_worker_exit_after_acceptance_leaves_durable_unknown_send(state,monkeypatch):
    u,t,c,conv=state
    delivery=WhatsAppDelivery.objects.create(tenant=t,dedup_key='reply:crash',recipient_phone=c.phone_number,payload={'text':'Bot','conversation_id':conv.pk,'sender_type':'BOT'})
    ctx=multiprocessing.get_context('fork');accepted=ctx.Event()
    def provider(**kw):accepted.set();os._exit(91)
    monkeypatch.setattr(WhatsAppClient,'send_text_message',provider)
    def child():connections.close_all();dispatch(delivery.pk)
    connections.close_all();process=ctx.Process(target=child);process.start();process.join(15)
    if process.is_alive():process.terminate();process.join();pytest.fail('Crash simulation timed out')
    assert accepted.is_set();assert process.exitcode==91
    delivery.refresh_from_db();assert delivery.status=='SENDING';assert delivery.attempts==1;assert delivery.quota_reserved
    monkeypatch.setattr(WhatsAppClient,'send_text_message',lambda **kw:pytest.fail('Ambiguous accepted send must not be repeated'))
    assert not dispatch(delivery.pk)
