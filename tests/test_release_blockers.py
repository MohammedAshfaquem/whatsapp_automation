import json
import pytest
from datetime import timedelta
from unittest.mock import patch, MagicMock
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
from apps.whatsapp.delivery import dispatch


@pytest.fixture
def blocker_setup(db):
    owner = User.objects.create_user(
        username='owner_alice',
        email='alice@example.com',
        password='Password123!',
        first_name='Alice',
        last_name='Owner',
        is_staff=True
    )
    staff = User.objects.create_user(
        username='staff_bob',
        email='bob@example.com',
        password='Password123!',
        first_name='Bob',
        last_name='Staff',
        is_staff=True
    )
    other_staff = User.objects.create_user(
        username='staff_charlie',
        email='charlie@example.com',
        password='Password123!',
        first_name='Charlie',
        last_name='Other',
        is_staff=True
    )
    tenant = Tenant.objects.create(
        name='Blocker Test Logistics',
        slug='blocker-logistics',
        is_active=True
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=owner,
        role=MembershipRole.OWNER,
        is_active=True
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=staff,
        role=MembershipRole.STAFF,
        is_active=True
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=other_staff,
        role=MembershipRole.STAFF,
        is_active=True
    )

    owner_client = Client()
    owner_client.force_login(owner)

    staff_client = Client()
    staff_client.force_login(staff)

    other_staff_client = Client()
    other_staff_client.force_login(other_staff)

    return {
        'owner': owner,
        'staff': staff,
        'other_staff': other_staff,
        'tenant': tenant,
        'owner_client': owner_client,
        'staff_client': staff_client,
        'other_staff_client': other_staff_client,
    }


# =========================================================================
# 1. Business Profile API Defect Reproduction
# =========================================================================
@pytest.mark.django_db
def test_business_profile_api_unknown_metadata_and_meta_error_propagation(blocker_setup):
    owner_client = blocker_setup['owner_client']
    staff_client = blocker_setup['staff_client']
    tenant = blocker_setup['tenant']

    # 1. Non-admin/owner staff must NOT be able to edit business profile (role enforcement)
    res_staff = staff_client.post(
        '/api/settings/whatsapp/profile/',
        data=json.dumps({'about': 'Unauthorized update'}),
        content_type='application/json'
    )
    assert res_staff.status_code == 403, "Staff without owner/admin role must be denied profile update"

    # 2. When Meta metadata is missing/unconnected, API must return UNKNOWN / UNAVAILABLE,
    # NOT invented 'GREEN' or 'TIER_1K' or 'VERIFIED'
    res_get = owner_client.get('/api/settings/whatsapp/profile/')
    assert res_get.status_code == 200
    meta = res_get.json().get('meta_info', {})
    assert meta.get('quality_rating') == 'UNKNOWN', "Missing quality rating must be UNKNOWN, not invented GREEN"
    assert meta.get('messaging_limit_tier') == 'UNKNOWN', "Missing tier must be UNKNOWN, not invented TIER_1K"
    assert meta.get('code_verification_status') == 'UNKNOWN', "Missing verification must be UNKNOWN, not invented VERIFIED"

    # 3. Upload implementation is available; runtime readiness is reported by the media endpoint.
    assert res_get.json().get('profile_picture_upload_supported') is True

    # 4. When Meta credentials are configured but Meta API fails, must expose error and mark meta_synced=False
    WhatsAppConfig.objects.create(
        tenant=tenant,
        is_enabled=True,
        phone_number_id='100000000001',
        business_account_id='200000000002',
        access_token='invalid_mock_token'
    )

    with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.update_business_profile') as mock_update:
        mock_update.return_value = (False, "Meta API Error: (#100) Invalid access token")
        res_post = owner_client.post(
            '/api/settings/whatsapp/profile/',
            data=json.dumps({
                'about': 'Apex Support 24/7',
                'vertical': 'PROF_SERVICES',
            }),
            content_type='application/json'
        )
        assert res_post.status_code == 200
        data = res_post.json()
        assert data.get('meta_synced') is False
        assert data.get('status') == 'LOCAL_SAVED'
        assert 'Meta API Error' in str(data.get('meta_warning', ''))


# =========================================================================
# 2. Template Approval and Server-Side Validation Defect Reproduction
# =========================================================================
@pytest.mark.django_db
def test_starter_templates_created_as_draft_and_require_server_validation(blocker_setup):
    owner_client = blocker_setup['owner_client']
    tenant = blocker_setup['tenant']

    # 1. When templates API seeds default samples, they must be DRAFT, NOT APPROVED
    res = owner_client.get('/api/whatsapp/templates/')
    assert res.status_code == 200
    templates = res.json().get('templates', [])
    for tpl in templates:
        assert tpl['status'] == 'DRAFT', f"Unverified local template {tpl['name']} must have status DRAFT, not APPROVED"

    # 2. A DRAFT template must NOT be permitted to start a conversation outside the 24h window
    customer = Customer.objects.create(
        tenant=tenant,
        name='Vikram Draft Test',
        phone_number='+919811122299'
    )
    draft_template = WhatsAppTemplate.objects.filter(tenant=tenant, name='welcome_greeting').first()
    assert draft_template.meta_status == 'DRAFT'

    res_send_draft = owner_client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'contact_id': customer.id,
            'channel': ChannelChoice.WHATSAPP,
            'template_name': 'welcome_greeting',
            'template_variables': ['Vikram'],
        }),
        content_type='application/json'
    )
    assert res_send_draft.status_code == 400
    assert 'not approved by meta' in res_send_draft.json().get('error', '').lower()

    # 3. Server-side variable count and non-empty validation on APPROVED template
    draft_template.meta_status = 'APPROVED'
    draft_template.body_text = 'Hello {{1}}, your booking for {{2}} is confirmed.'
    draft_template.save()

    # Sending with missing or empty variables must fail with 400
    res_bad_vars = owner_client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'contact_id': customer.id,
            'channel': ChannelChoice.WHATSAPP,
            'template_name': 'welcome_greeting',
            'template_variables': ['Vikram', '   '],  # 2nd variable is empty whitespace
        }),
        content_type='application/json'
    )
    assert res_bad_vars.status_code == 400
    assert 'variable' in res_bad_vars.json().get('error', '').lower()


# =========================================================================
# 3. Delivery Retry Safety Defect Reproduction
# =========================================================================
@pytest.mark.django_db
def test_delivery_retry_atomically_rejects_sending_and_unknown(blocker_setup):
    owner_client = blocker_setup['owner_client']
    tenant = blocker_setup['tenant']

    # 1. SENDING record must NOT be allowed to be reset/retried (currently in flight)
    sending_delivery = WhatsAppDelivery.objects.create(
        tenant=tenant,
        recipient_phone='+919876543210',
        status='SENDING',
        dedup_key='release-sending',
        attempts=1,
        payload={'text': 'In flight message'}
    )
    res_sending = owner_client.post(f'/api/inbox/delivery/{sending_delivery.id}/retry/')
    assert res_sending.status_code in (400, 409), "SENDING in-flight delivery must be rejected from retry"

    # 2. UNKNOWN record must NOT be automatically retried (ambiguous timeout requires inspection)
    unknown_delivery = WhatsAppDelivery.objects.create(
        tenant=tenant,
        recipient_phone='+919876543210',
        status='UNKNOWN',
        dedup_key='release-unknown',
        attempts=1,
        last_error='Socket timeout: connection dropped',
        payload={'text': 'Ambiguous timeout message'}
    )
    res_unknown = owner_client.post(f'/api/inbox/delivery/{unknown_delivery.id}/retry/')
    assert res_unknown.status_code == 400
    assert 'inspection' in res_unknown.json().get('error', '').lower()

    # 3. A retry must be tied to the current agent's real conversation/window.
    customer = Customer.objects.create(tenant=tenant, phone_number='+919876543210')
    conv = Conversation.objects.create(tenant=tenant, customer=customer, channel='WHATSAPP', status='HUMAN_HANDOVER', assigned_staff=blocker_setup['owner'])
    Message.objects.create(conversation=conv, direction='INBOUND', sender_type='CUSTOMER', message_text='Please help')
    # Attempt count must be preserved (not reset to 0).
    failed_delivery = WhatsAppDelivery.objects.create(
        tenant=tenant,
        recipient_phone='+919876543210',
        status='FAILED',
        dedup_key='release-failed',
        attempts=2,
        last_error='500 Internal error from provider',
        payload={'text': 'Failed text message'}
    )
    with patch('apps.whatsapp.delivery.dispatch') as mock_dispatch:
        mock_dispatch.return_value = True
        res_retry = owner_client.post(f'/api/inbox/delivery/{failed_delivery.id}/retry/')
        assert res_retry.status_code == 200
        failed_delivery.refresh_from_db()
        assert failed_delivery.attempts >= 2, "Attempts count must not be wiped out to 0"


# =========================================================================
# 4. Bot/Human Dispatch Race Defect Reproduction
# =========================================================================
@pytest.mark.django_db
def test_bot_human_dispatch_race_and_takeover_suppression(blocker_setup):
    tenant = blocker_setup['tenant']
    owner_client = blocker_setup['owner_client']
    phone = '+919876543299'

    customer = Customer.objects.create(tenant=tenant, name='Race Condition Customer', phone_number=phone)
    conversation = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        channel=ChannelChoice.WHATSAPP,
        status=ConversationStatus.BOT_ACTIVE
    )

    # A bot reply is queued in PENDING state
    bot_delivery = WhatsAppDelivery.objects.create(
        tenant=tenant,
        recipient_phone=phone,
        status='PENDING',
        dedup_key=f'reply:{tenant.id}:msg_race_1',
        payload={'text': 'Automated Bot Reply', 'sender_type': 'BOT', 'conversation_id': conversation.id}
    )

    # Human agent takes over before dispatch runs
    res_takeover = owner_client.post(f'/conversations/{conversation.id}/action/', data={'action': 'switch_to_human'})
    assert res_takeover.status_code == 200

    # Pending bot deliveries for this conversation must be cancelled / marked BLOCKED
    bot_delivery.refresh_from_db()
    assert bot_delivery.status == 'BLOCKED'
    assert 'takeover' in bot_delivery.last_error.lower() or 'human' in bot_delivery.last_error.lower()

    # Even if dispatch() is invoked on a bot delivery while conversation is in HUMAN_HANDOVER,
    # dispatch() must recheck conversation mode and NOT call Meta
    with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_text_message') as mock_send:
        # Reset to pending to simulate direct dispatch invocation
        bot_delivery.status = 'PENDING'
        bot_delivery.save()
        ok = dispatch(bot_delivery.id)
        assert ok is False
        assert mock_send.called is False
        bot_delivery.refresh_from_db()
        assert bot_delivery.status == 'BLOCKED'


# =========================================================================
# 5. New Chat Ownership Bypass Defect Reproduction
# =========================================================================
@pytest.mark.django_db
def test_new_chat_ownership_conflict_and_bot_mode_preservation(blocker_setup):
    owner = blocker_setup['owner']
    staff = blocker_setup['staff']
    other_staff_client = blocker_setup['other_staff_client']
    tenant = blocker_setup['tenant']

    customer = Customer.objects.create(tenant=tenant, name='Exclusive Lead', phone_number='+919822233344')

    # Conversation already exists and is claimed by Staff Bob in HUMAN_HANDOVER
    conversation = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        channel=ChannelChoice.SIMULATED,
        status=ConversationStatus.HUMAN_HANDOVER,
        assigned_staff=staff,
        picked_up_at=timezone.now()
    )

    # Agent Charlie attempts "New Chat" with the same contact
    res_conflict = other_staff_client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'contact_id': customer.id,
            'channel': ChannelChoice.SIMULATED,
            'message_text': 'Hijacked chat?',
        }),
        content_type='application/json'
    )
    assert res_conflict.status_code == 409
    assert staff.username in res_conflict.json().get('error', '')
    conversation.refresh_from_db()
    assert conversation.assigned_staff == staff, "Ownership must NOT be reassigned silently"

    # Conversation in BOT_ACTIVE mode must NOT silently switch to HUMAN_HANDOVER on opening
    customer2 = Customer.objects.create(tenant=tenant, name='Bot Active Customer', phone_number='+919833344455')
    bot_conv = Conversation.objects.create(
        tenant=tenant,
        customer=customer2,
        channel=ChannelChoice.SIMULATED,
        status=ConversationStatus.BOT_ACTIVE
    )
    res_open = other_staff_client.post(
        '/api/inbox/conversations/start/',
        data=json.dumps({
            'contact_id': customer2.id,
            'channel': ChannelChoice.SIMULATED,
        }),
        content_type='application/json'
    )
    assert res_open.status_code == 200
    bot_conv.refresh_from_db()
    assert bot_conv.status == ConversationStatus.BOT_ACTIVE, "Opening existing chat must NOT silently hijack bot mode"

