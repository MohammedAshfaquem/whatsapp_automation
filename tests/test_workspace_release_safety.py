import json
import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.utils import timezone
from apps.tenants.models import Tenant,TenantMembership
from apps.chatbot.models import Customer,Conversation,Message,ConversationStatus,ChannelChoice
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.delivery import dispatch

@pytest.fixture
def setup(db,client):
    user=User.objects.create_user('release_owner',is_staff=True)
    other=User.objects.create_user('release_other',is_staff=True)
    tenant=Tenant.objects.create(name='Release safety',slug='release-safety')
    TenantMembership.objects.create(tenant=tenant,user=user,role='OWNER')
    TenantMembership.objects.create(tenant=tenant,user=other,role='STAFF')
    client.force_login(user)
    customer=Customer.objects.create(tenant=tenant,phone_number='+919876500111')
    conv=Conversation.objects.create(tenant=tenant,customer=customer,channel='WHATSAPP',status='HUMAN_HANDOVER',assigned_staff=user)
    Message.objects.create(conversation=conv,direction='INBOUND',sender_type='CUSTOMER',message_text='Hello')
    return client,tenant,user,other,customer,conv

def delivery(tenant,customer,conv,**kw):
    fields=dict(tenant=tenant,recipient_phone=customer.phone_number,dedup_key='release:1',payload={'text':'Hello','conversation_id':conv.pk,'sender_type':'HUMAN'},status='FAILED',attempts=1)
    fields.update(kw)
    return WhatsAppDelivery.objects.create(**fields)

@pytest.mark.django_db
def test_retry_rejects_orphan_without_sending(setup):
    client,t,u,o,c,conv=setup
    d=delivery(t,c,conv,payload={'text':'Hello'},recipient_phone='+919999888777')
    assert client.post(f'/api/inbox/delivery/{d.pk}/retry/').status_code==400
    d.refresh_from_db();assert d.status=='FAILED'

@pytest.mark.django_db
def test_retry_cannot_send_another_agents_delivery(setup):
    client,t,u,o,c,conv=setup
    conv.assigned_staff=o;conv.save()
    d=delivery(t,c,conv)
    assert client.post(f'/api/inbox/delivery/{d.pk}/retry/').status_code==409

@pytest.mark.django_db
def test_retry_cannot_rewrite_exhausted_attempt_history(setup):
    client,t,u,o,c,conv=setup
    d=delivery(t,c,conv,attempts=7)
    assert client.post(f'/api/inbox/delivery/{d.pk}/retry/').status_code==400
    d.refresh_from_db();assert d.attempts==7

@pytest.mark.django_db
def test_new_chat_cannot_bypass_explicit_human_takeover(setup):
    client,t,u,o,c,conv=setup
    conv.status='BOT_ACTIVE';conv.assigned_staff=None;conv.save()
    r=client.post('/api/inbox/conversations/start/',json.dumps({'contact_id':c.pk,'message_text':'Bypass'}),content_type='application/json')
    assert r.status_code==409
    conv.refresh_from_db();assert conv.status=='BOT_ACTIVE'
    assert not conv.messages.filter(direction='OUTBOUND').exists()

@pytest.mark.django_db(transaction=True)
def test_provider_call_remains_inside_serialized_dispatch_gate(setup,monkeypatch):
    client,t,u,o,c,conv=setup
    from apps.whatsapp.whatsapp_client import WhatsAppClient
    observed=[]
    monkeypatch.setattr(WhatsAppClient,'send_text_message',lambda **kw:(observed.append(connection.in_atomic_block) or (True,'wamid.mock')))
    d=delivery(t,c,conv,status='PENDING')
    assert dispatch(d.pk)
    assert observed==[True]

@pytest.mark.django_db
def test_bot_dispatch_fails_closed_for_unresolvable_origin(setup,monkeypatch):
    client,t,u,o,c,conv=setup
    from apps.whatsapp.whatsapp_client import WhatsAppClient
    def forbidden(**kw):raise AssertionError('must not call provider')
    monkeypatch.setattr(WhatsAppClient,'send_text_message',forbidden)
    d=delivery(t,c,conv,status='PENDING',dedup_key='reply:missing',payload={'text':'Bot','conversation_id':999999,'sender_type':'BOT'})
    assert not dispatch(d.pk)
    d.refresh_from_db();assert d.status=='BLOCKED'

@pytest.mark.django_db
def test_profile_sync_cannot_report_provider_failure_as_success(setup,monkeypatch):
    client,t,u,o,c,conv=setup
    from apps.whatsapp.models import WhatsAppConfig
    from apps.whatsapp.whatsapp_client import WhatsAppClient
    WhatsAppConfig.objects.create(tenant=t,is_enabled=True,phone_number_id='123',access_token='test-not-real')
    monkeypatch.setattr(WhatsAppClient,'get_business_profile',lambda **kw:{'configured':True,'live':False,'error':'Provider unavailable'})
    response=client.get('/api/settings/whatsapp/profile/?sync=true')
    assert response.status_code==502
    assert 'error' in response.json()

@pytest.mark.django_db
def test_legacy_contact_composer_cannot_bypass_owner_or_mode(setup):
    client,t,u,o,c,conv=setup
    conv.status='BOT_ACTIVE';conv.assigned_staff=o;conv.save()
    response=client.post(f'/crm/contacts/{c.pk}/send_message/',{'text':'Unsafe bypass'})
    assert response.status_code==302
    assert response.url=='/app/inbox'
    assert not conv.messages.filter(direction='OUTBOUND').exists()

@pytest.mark.django_db(transaction=True)
def test_claim_is_durable_before_provider_acceptance(setup,monkeypatch):
    client,t,u,o,c,conv=setup
    from apps.whatsapp.whatsapp_client import WhatsAppClient
    observed=[]
    d=delivery(t,c,conv,status='PENDING',attempts=0)
    def provider(**kw):
        observer=connection.copy(alias='independent_observer')
        try:
            with observer.cursor() as cur:
                cur.execute('SELECT status, attempts FROM whatsapp_whatsappdelivery WHERE id=%s',[d.pk])
                observed.append(cur.fetchone())
        finally:observer.close()
        return True,'wamid.mock'
    monkeypatch.setattr(WhatsAppClient,'send_text_message',provider)
    assert dispatch(d.pk)
    assert observed==[('SENDING',1)]

@pytest.mark.django_db
def test_inbox_owner_identity_is_username_even_with_display_name(setup):
    client,t,u,o,c,conv=setup
    u.first_name='Actual';u.last_name='Owner';u.save()
    response=client.get('/api/inbox/conversations/')
    row=next(row for row in response.json()['conversations'] if row['id']==conv.pk)
    assert row['assigned_staff']==u.username
    assert row['assigned_staff_name']=='Actual Owner'

@pytest.mark.django_db(transaction=True)
def test_human_takeover_cancels_claimed_bot_even_if_bot_resumed_before_gate(setup,monkeypatch):
    from contextlib import contextmanager
    import apps.whatsapp.delivery as delivery_module
    from apps.whatsapp.whatsapp_client import WhatsAppClient
    client,t,u,o,c,conv=setup
    conv.status='BOT_ACTIVE';conv.assigned_staff=None;conv.save()
    d=delivery(t,c,conv,status='PENDING',attempts=0,dedup_key='reply:claim-gap',payload={'text':'Old bot reply','conversation_id':conv.pk,'sender_type':'BOT'})
    original=delivery_module.locked_delivery;calls=[]
    monkeypatch.setattr(WhatsAppClient,'send_text_message',lambda **kw:(calls.append(1) or (True,'wamid.stub')))
    @contextmanager
    def takeover_before_gate(delivery_id):
        assert client.post(f'/conversations/{conv.pk}/action/',{'action':'switch_to_human'}).status_code==200
        assert client.post(f'/conversations/{conv.pk}/action/',{'action':'resume'}).status_code==200
        with original(delivery_id) as value:yield value
    monkeypatch.setattr(delivery_module,'locked_delivery',takeover_before_gate)
    assert not dispatch(d.pk)
    assert calls==[]
    d.refresh_from_db();assert d.status=='UNKNOWN';assert d.quota_reserved

@pytest.mark.django_db
def test_takeover_cannot_turn_ambiguous_sending_into_retryable_failure(setup):
    client,t,u,o,c,conv=setup
    conv.status='BOT_ACTIVE';conv.assigned_staff=None;conv.save()
    assert t.reserve_monthly_message_slot()
    d=delivery(t,c,conv,status='SENDING',attempts=1,quota_reserved=True,dedup_key='reply:accepted-crash',payload={'text':'Possibly accepted','conversation_id':conv.pk,'sender_type':'BOT'})
    assert client.post(f'/conversations/{conv.pk}/action/',{'action':'switch_to_human'}).status_code==200
    d.refresh_from_db();assert d.status=='UNKNOWN';assert d.quota_reserved
    assert client.post(f'/conversations/{conv.pk}/action/',{'action':'resume'}).status_code==200
    assert client.post(f'/api/inbox/delivery/{d.pk}/retry/').status_code==400
