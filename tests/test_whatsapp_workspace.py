import json
import pytest
from datetime import timedelta
from django.utils import timezone
from django.contrib.auth.models import User
from django.test import Client

from apps.tenants.models import Tenant, TenantMembership, MembershipRole, TenantAuditLog
from apps.chatbot.models import (
    Customer, Conversation, Message, ConversationStatus,
    ChannelChoice, MessageDirection, SenderType, ProcessingStatus
)
from apps.whatsapp.models import WhatsAppConfig, WhatsAppDelivery, WhatsAppBusinessProfile
from apps.crm.models import WhatsAppTemplate
from apps.whatsapp.events import process_events


@pytest.fixture
def workspace_setup(db):
    user = User.objects.create_user(
        username='agent_rahul',
        email='rahul@example.com',
        password='AgentPassword123!',
        first_name='Rahul',
        last_name='Sharma',
        is_staff=True
    )
    other_user = User.objects.create_user(
        username='agent_priya',
        email='priya@example.com',
        password='PriyaPassword123!',
        first_name='Priya',
        last_name='Patel',
        is_staff=True
    )
    tenant = Tenant.objects.create(
        name='Apex Logistics',
        slug='apex-logistics',
        is_active=True
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=user,
        role=MembershipRole.OWNER,
        is_active=True
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=other_user,
        role=MembershipRole.STAFF,
        is_active=True
    )
    client = Client()
    client.force_login(user)

    other_client = Client()
    other_client.force_login(other_user)

    return {
        'user': user,
        'other_user': other_user,
        'tenant': tenant,
        'client': client,
        'other_client': other_client,
    }


@pytest.mark.django_db
def test_whatsapp_business_profile_api_get_and_post(workspace_setup):
    client = workspace_setup['client']

    # GET profile
    res = client.get('/api/settings/whatsapp/profile/')
    assert res.status_code == 200
    data = res.json()
    assert 'profile' in data
    assert 'meta_info' in data
    assert 'vertical_choices' in data
    assert len(data['vertical_choices']) > 0

    # POST profile with valid values
    payload = {
        'about': 'Reliable logistics and delivery tracking 24/7',
        'description': 'Apex Logistics provides domestic and international freight forwarding.',
        'address': 'Plot 42, Port Road, Navi Mumbai, India',
        'email': 'support@apexlogistics.in',
        'websites': ['https://apexlogistics.in', 'https://track.apexlogistics.in'],
        'vertical': 'PROF_SERVICES',
    }
    res_post = client.post(
        '/api/settings/whatsapp/profile/',
        data=json.dumps(payload),
        content_type='application/json'
    )
    assert res_post.status_code == 200
    post_data = res_post.json()
    assert post_data['profile']['about'] == payload['about']
    assert post_data['profile']['vertical'] == 'PROF_SERVICES'

    # Verify DB persistence
    profile = WhatsAppBusinessProfile.objects.get(tenant=workspace_setup['tenant'])
    assert profile.about == payload['about']
    assert profile.vertical == 'PROF_SERVICES'
    assert profile.websites == payload['websites']

    # Verify audit log
    assert TenantAuditLog.objects.filter(
        tenant=workspace_setup['tenant'],
        action='TENANT_STATUS_CHANGED'
    ).exists()

    # Field length validation: about > 139 chars
    bad_payload = payload.copy()
    bad_payload['about'] = 'X' * 140
    res_bad = client.post(
        '/api/settings/whatsapp/profile/',
        data=json.dumps(bad_payload),
        content_type='application/json'
    )
    assert res_bad.status_code == 400
    assert '139 characters' in res_bad.json()['error']

    # Websites limit: > 2 websites
    bad_payload = payload.copy()
    bad_payload['websites'] = ['https://site1.com', 'https://site2.com', 'https://site3.com']
    res_bad_sites = client.post(
        '/api/settings/whatsapp/profile/',
        data=json.dumps(bad_payload),
        content_type='application/json'
    )
    assert res_bad_sites.status_code == 400
    assert '2 website URLs' in res_bad_sites.json()['error']


@pytest.mark.django_db
def test_whatsapp_templates_api_auto_seeds_defaults(workspace_setup):
    client = workspace_setup['client']
    tenant = workspace_setup['tenant']

    assert WhatsAppTemplate.objects.filter(tenant=tenant).count() == 0

    res = client.get('/api/whatsapp/templates/')
    assert res.status_code == 200
    data = res.json()
    assert 'templates' in data
    assert len(data['templates']) >= 4

    names = [t['name'] for t in data['templates']]
    assert 'welcome_greeting' in names
    assert 'appointment_reminder' in names
    assert 'service_followup' in names
    assert 'account_update' in names

    # Confirm saved in DB as DRAFT (unverified local starter samples)
    assert WhatsAppTemplate.objects.filter(tenant=tenant, meta_status='DRAFT').count() >= 4


@pytest.mark.django_db
def test_start_conversation_phone_validation_and_duplicate_prevention(workspace_setup):
    client = workspace_setup['client']
    tenant = workspace_setup['tenant']

    # Reject invalid phone
    res_invalid = client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({'phone_number': 'not_a_phone', 'name': 'Test'}),
        content_type='application/json'
    )
    assert res_invalid.status_code == 400
    assert 'E.164' in res_invalid.json()['error']

    # Rejection when neither contact_id nor phone_number provided
    res_empty = client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({}),
        content_type='application/json'
    )
    assert res_empty.status_code == 400

    # Start new chat on simulated channel without template requirement
    res_sim = client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'phone_number': '+919876543210',
            'name': 'Anita Roy',
            'channel': ChannelChoice.SIMULATED,
            'message_text': 'Hello Anita! Welcome to Apex.',
        }),
        content_type='application/json'
    )
    assert res_sim.status_code == 200
    sim_data = res_sim.json()
    conv_id = sim_data['conversation_id']
    assert conv_id is not None

    # Verify no duplicate conversation created on repeating call
    res_repeat = client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'phone_number': '+919876543210',
            'channel': ChannelChoice.SIMULATED,
        }),
        content_type='application/json'
    )
    assert res_repeat.status_code == 200
    assert res_repeat.json()['conversation_id'] == conv_id
    assert Conversation.objects.filter(customer__phone_number='+919876543210').count() == 1


@pytest.mark.django_db
def test_start_conversation_24h_window_template_rule(workspace_setup):
    client = workspace_setup['client']
    tenant = workspace_setup['tenant']

    # Customer on WhatsApp channel has no inbound message -> 24h window closed
    customer = Customer.objects.create(
        tenant=tenant,
        name='Vikram Seth',
        phone_number='+919811122233'
    )

    # Attempting to start free-form on WhatsApp channel without template should fail
    res_fail = client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'contact_id': customer.id,
            'channel': ChannelChoice.WHATSAPP,
            'message_text': 'Free form initial outreach',
        }),
        content_type='application/json'
    )
    assert res_fail.status_code == 400
    fail_data = res_fail.json()
    assert fail_data.get('requires_template') is True
    assert 'approved Meta template' in fail_data.get('error', '')

    # Seed template
    template = WhatsAppTemplate.objects.create(
        tenant=tenant,
        name='welcome_greeting',
        category='UTILITY',
        language='en',
        body_text='Hello {{1}}, welcome to our WhatsApp support! How can our team help you today?',
        variables=['Customer Name'],
        meta_status='APPROVED'
    )

    # Starting with approved template succeeds
    res_ok = client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'contact_id': customer.id,
            'channel': ChannelChoice.WHATSAPP,
            'template_name': 'welcome_greeting',
            'template_variables': ['Vikram'],
        }),
        content_type='application/json'
    )
    assert res_ok.status_code == 200
    ok_data = res_ok.json()
    assert ok_data['conversation_id'] is not None

    conv = Conversation.objects.get(id=ok_data['conversation_id'])
    outbound_msg = conv.messages.filter(direction=MessageDirection.OUTBOUND).first()
    assert outbound_msg is not None
    assert 'Hello Vikram' in outbound_msg.message_text

    # Delivery record created with template payload
    delivery = WhatsAppDelivery.objects.filter(dedup_key=f'staff:{outbound_msg.pk}').first()
    assert delivery is not None
    assert delivery.payload['template']['name'] == 'welcome_greeting'
    assert delivery.payload['template']['parameters'] == ['Vikram']


@pytest.mark.django_db
def test_bot_vs_human_mode_lifecycle_and_composer_guard(workspace_setup):
    client = workspace_setup['client']
    other_client = workspace_setup['other_client']
    user = workspace_setup['user']
    other_user = workspace_setup['other_user']
    tenant = workspace_setup['tenant']

    customer = Customer.objects.create(
        tenant=tenant,
        name='Aarav Mehta',
        phone_number='+919800011122'
    )
    conversation = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        channel=ChannelChoice.SIMULATED,
        status=ConversationStatus.BOT_ACTIVE,
        last_message_at=timezone.now()
    )

    # In BOT_ACTIVE mode, manual reply attempt is rejected with 400
    res_blocked = client.post(
        f'/conversations/{conversation.id}/action/',
        data={'action': 'reply', 'text': 'Manual staff reply should be blocked in bot mode'}
    )
    assert res_blocked.status_code == 400
    assert 'Bot Mode' in res_blocked.json()['error']

    # Switch to Human mode
    res_switch = client.post(
        f'/conversations/{conversation.id}/action/',
        data={'action': 'switch_to_human'}
    )
    assert res_switch.status_code == 200
    conversation.refresh_from_db()
    assert conversation.status == ConversationStatus.HUMAN_HANDOVER
    assert conversation.assigned_staff == user
    assert conversation.picked_up_at is not None

    # Now staff can reply
    res_reply = client.post(
        f'/conversations/{conversation.id}/action/',
        data={'action': 'reply', 'text': 'Hello Aarav, I am taking over your chat.'}
    )
    assert res_reply.status_code == 200
    msg = conversation.messages.filter(direction=MessageDirection.OUTBOUND).first()
    assert msg is not None
    assert msg.response_data.get('author_username') == user.username

    # Another staff member cannot reply while claimed by Rahul
    res_conflict = other_client.post(
        f'/conversations/{conversation.id}/action/',
        data={'action': 'reply', 'text': 'Conflicting reply'}
    )
    assert res_conflict.status_code == 409

    # Release chat to team queue
    res_release = client.post(
        f'/conversations/{conversation.id}/action/',
        data={'action': 'release'}
    )
    assert res_release.status_code == 200
    conversation.refresh_from_db()
    assert conversation.assigned_staff is None

    # Resume bot
    res_resume = client.post(
        f'/conversations/{conversation.id}/action/',
        data={'action': 'resume'}
    )
    assert res_resume.status_code == 200
    conversation.refresh_from_db()
    assert conversation.status == ConversationStatus.BOT_ACTIVE
    assert conversation.assigned_staff is None


@pytest.mark.django_db
def test_concurrency_guard_suppresses_bot_reply_if_switched_to_human(workspace_setup, monkeypatch):
    tenant = workspace_setup['tenant']
    phone = '+919988776655'

    # Customer sends inbound message
    customer = Customer.objects.create(
        tenant=tenant,
        name='Siddharth Rao',
        phone_number=phone
    )
    conv = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        channel=ChannelChoice.WHATSAPP,
        status=ConversationStatus.HUMAN_HANDOVER  # Human mode is active!
    )

    # Mock ConversationService.process_message to simulate return of a reply
    from apps.chatbot.conversation_service import ConversationService
    def mock_process(*args, **kwargs):
        return {
            'reply': 'Automated bot response',
            'conversation_id': conv.id,
        }
    monkeypatch.setattr(ConversationService, 'process_message', mock_process)

    # Inbound webhook event
    payload = {
        'entry': [{
            'changes': [{
                'value': {
                    'messages': [{
                        'id': 'wamid_12345678',
                        'from': phone.lstrip('+'),
                        'type': 'text',
                        'text': {'body': 'Need urgent assistance'},
                        'timestamp': str(int(timezone.now().timestamp()))
                    }]
                }
            }]
        }]
    }

    result = process_events(payload, tenant=tenant)
    assert result['processed'] == 1

    # Verify delivery record was NOT created because conversation was in HUMAN_HANDOVER mode
    assert WhatsAppDelivery.objects.filter(
        recipient_phone=phone,
        payload__text='Automated bot response'
    ).count() == 0


@pytest.mark.django_db
def test_delivery_retry_api_behavior(workspace_setup):
    client = workspace_setup['client']
    tenant = workspace_setup['tenant']

    delivery = WhatsAppDelivery.objects.create(
        tenant=tenant,
        recipient_phone='+919876543210',
        status='FAILED',
        attempts=3,
        last_error='Network timeout',
        payload={'text': 'Test retry'}
    )

    # Exhausted and ambiguous deliveries require inspection, never counter reset.
    res = client.post(f'/api/inbox/delivery/{delivery.id}/retry/')
    assert res.status_code == 400
    delivery.refresh_from_db()
    assert delivery.attempts == 3
    assert delivery.last_error == 'Network timeout'

    # Already delivered message cannot be retried
    delivery.status = 'DELIVERED'
    delivery.save()
    res_bad = client.post(f'/api/inbox/delivery/{delivery.id}/retry/')
    assert res_bad.status_code == 400
    assert 'already reached status' in res_bad.json()['error']
