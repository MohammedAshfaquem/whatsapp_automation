"""
Comprehensive Release 3 Test Suite:
1. Super Admin SaaS Controls:
   - Least-privilege operator roles (SUPER_ADMIN, SUPPORT, BILLING, READ_ONLY) & session revocation
   - Operations health lease bug fix & one-click expired lease reclamation
   - Global & per-client outbound WhatsApp pause blocking dispatch without quota burn
   - Billing grace period & renewal reminder queuing
   - System settings bounded validation & maintenance mode (503 client, live operator/health)
   - Plan limits editing & usage threshold alerts (80% warning, 100% exceeded)
2. Client Operational Enhancements:
   - Inbox media upload/send, tenant-scoped download proxy, chat transfer, unread counter + mark-read, full-text message search
   - Contacts CSV import preview + execute, tag filtering, custom_fields & tags updates (no auto marketing consent)
   - Broadcasts tag segmentation, preview audience & per-contact variable mapping with fallbacks
   - Automation business hours + away reply cooldown, no-response follow-up task scanner, and enhanced reports
"""
from datetime import date, datetime, timedelta, timezone as py_timezone
import json
from unittest.mock import patch
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.business.models import BusinessProfile
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import (
    ChannelChoice,
    Conversation,
    ConversationStatus,
    Customer,
    Message,
    MessageDirection,
    SenderType,
)
from apps.crm.broadcasts import eligible_audience, launch, resolve_recipient_parameters, run_campaigns
from apps.crm.business_hours import is_within_business_hours, process_no_response_followups
from apps.crm.models import (
    Activity,
    BusinessEvent,
    Campaign,
    ContactConsent,
    WebhookDeliveryLog,
    WebhookEndpoint,
    WhatsAppTemplate,
)
from apps.tenants.models import (
    PlatformOperatorRole,
    PlatformServiceConfig,
    PlanTier,
    SubscriptionStatus,
    Tenant,
    TenantMembership,
    TenantMonthlyUsage,
    TenantRole,
    TenantSubscription,
    TransactionalEmail,
    UserSecurityProfile,
)
from apps.whatsapp.delivery import dispatch
from apps.whatsapp.models import WhatsAppConfig, WhatsAppDelivery

pytestmark = pytest.mark.django_db


@pytest.fixture
def r3_env(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path / 'media')
    plan = PlanTier.objects.create(
        code='growth-r3',
        name='Growth R3',
        monthly_price=2500,
        max_staff=5,
        max_contacts=10,
        max_services=10,
        max_documents=5,
        monthly_message_allowance=10,
        enabled_modules=['shared_inbox', 'contacts_companies', 'team_management', 'marketing', 'reports', 'automation', 'whatsapp_bot'],
    )
    t1 = Tenant.objects.create(name='Client R3 One', slug='client-r3-one', is_active=True, whatsapp_number='+919800010001')
    t2 = Tenant.objects.create(name='Client R3 Two', slug='client-r3-two', is_active=True, whatsapp_number='+919800020002')
    TenantSubscription.objects.create(tenant=t1, effective_plan=plan, status=SubscriptionStatus.ACTIVE, end_date=date(2027, 1, 1))
    TenantSubscription.objects.create(tenant=t2, effective_plan=plan, status=SubscriptionStatus.ACTIVE, end_date=date(2027, 1, 1))
    WhatsAppConfig.objects.create(tenant=t1, is_enabled=True, phone_number_id='111000111', business_account_id='222000222', access_token='tok_r3_1')

    sa = User.objects.create_superuser('sa_r3', 'sa_r3@example.com', 'Pass12345!')
    sup_op = User.objects.create_user('sup_r3', 'sup_r3@example.com', 'Pass12345!', is_staff=True)
    UserSecurityProfile.objects.create(user=sup_op, email_verified=True, platform_role=PlatformOperatorRole.SUPPORT)
    bill_op = User.objects.create_user('bill_r3', 'bill_r3@example.com', 'Pass12345!', is_staff=True)
    UserSecurityProfile.objects.create(user=bill_op, email_verified=True, platform_role=PlatformOperatorRole.BILLING)
    ro_op = User.objects.create_user('ro_r3', 'ro_r3@example.com', 'Pass12345!', is_staff=True)
    UserSecurityProfile.objects.create(user=ro_op, email_verified=True, platform_role=PlatformOperatorRole.READ_ONLY)

    owner1 = User.objects.create_user('owner_r3_1', 'o1@r3.example.com', 'Pass12345!', is_staff=True)
    UserSecurityProfile.objects.create(user=owner1, email_verified=True)
    TenantMembership.objects.create(tenant=t1, user=owner1, role=TenantRole.OWNER, is_active=True)

    staff1 = User.objects.create_user('staff_r3_1', 's1@r3.example.com', 'Pass12345!', is_staff=True)
    UserSecurityProfile.objects.create(user=staff1, email_verified=True)
    TenantMembership.objects.create(tenant=t1, user=staff1, role=TenantRole.STAFF, is_active=True)

    owner2 = User.objects.create_user('owner_r3_2', 'o2@r3.example.com', 'Pass12345!', is_staff=True)
    UserSecurityProfile.objects.create(user=owner2, email_verified=True)
    TenantMembership.objects.create(tenant=t2, user=owner2, role=TenantRole.OWNER, is_active=True)

    return {
        'plan': plan,
        't1': t1,
        't2': t2,
        'sa': sa,
        'sup_op': sup_op,
        'bill_op': bill_op,
        'ro_op': ro_op,
        'owner1': owner1,
        'staff1': staff1,
        'owner2': owner2,
    }


def test_operator_rbac_and_session_revocation(r3_env):
    c_ro = Client()
    c_ro.force_login(r3_env['ro_op'])
    assert c_ro.get('/api/platform/system-settings/').status_code == 200
    assert c_ro.get('/api/platform/tools/health/').status_code == 200
    assert c_ro.post('/api/platform/system-settings/', json.dumps({'maintenance_mode': True}), content_type='application/json').status_code == 403
    assert c_ro.post(f"/api/platform/tenants/{r3_env['t1'].pk}/outbound-pause/", json.dumps({'paused': True}), content_type='application/json').status_code == 403

    c_bill = Client()
    c_bill.force_login(r3_env['bill_op'])
    assert c_bill.post(
        f"/api/platform/matrix/plan/{r3_env['plan'].code}/",
        json.dumps({'max_contacts': 50}),
        content_type='application/json',
    ).status_code == 200
    r3_env['plan'].refresh_from_db()
    assert r3_env['plan'].max_contacts == 50
    assert c_bill.post('/api/platform/system-settings/', json.dumps({'maintenance_mode': True}), content_type='application/json').status_code == 403

    # Active session revocation invalidates another user's live DB session immediately
    c_target = Client()
    c_target.force_login(r3_env['staff1'])
    assert c_target.get('/api/inbox/conversations/').status_code == 200

    c_sa = Client()
    c_sa.force_login(r3_env['sa'])
    res = c_sa.post(f"/api/platform/operations/users/{r3_env['staff1'].pk}/revoke-sessions/")
    assert res.status_code == 200
    assert res.json()['revoked_sessions'] >= 1
    assert c_target.get('/api/inbox/conversations/').status_code == 401


def test_health_leases_outbound_pause_and_maintenance_mode(r3_env):
    t1 = r3_env['t1']
    now = timezone.now()
    # One active lease, one expired customer lease, one expired event, one expired webhook, one stale SENDING delivery
    Customer.objects.create(tenant=t1, phone_number='+919800011111', name='ActiveLease', processing_token='tok_a', processing_until=now + timedelta(minutes=5))
    c_exp = Customer.objects.create(tenant=t1, phone_number='+919800011112', name='StaleLease', processing_token='tok_b', processing_until=now - timedelta(minutes=5))
    ev = BusinessEvent.objects.create(tenant=t1, event_id='ev-stale-1', event_type='lead.created', entity_type='contact', entity_id=c_exp.pk, status='PROCESSING', lease_expires_at=now - timedelta(minutes=2), attempts=1)
    ep = WebhookEndpoint.objects.create(tenant=t1, target_url='https://example.com/hook', signing_secret='sec')
    wh = WebhookDeliveryLog.objects.create(endpoint=ep, event_type='lead.created', delivery_id='wh-stale-1', state='PROCESSING', lease_expires_at=now - timedelta(minutes=2))
    d_stale = WhatsAppDelivery.objects.create(tenant=t1, dedup_key='stale-send-1', recipient_phone='+919800011112', payload={'text': 'hi'}, status='SENDING')
    WhatsAppDelivery.objects.filter(pk=d_stale.pk).update(updated_at=now - timedelta(minutes=15))

    c_sa = Client()
    c_sa.force_login(r3_env['sa'])
    health = c_sa.get('/api/platform/tools/health/').json()
    assert health['active_processing_leases'] == 1
    assert health['expired_processing_leases'] == 4
    mon = c_sa.get('/api/platform/monitoring/').json()
    assert mon['stalled_leases_count'] == 4

    rel = c_sa.post('/api/platform/tools/health/', json.dumps({'action': 'release_expired_leases'}), content_type='application/json')
    assert rel.status_code == 200
    reclaimed = rel.json()['reclaimed']
    assert reclaimed['customer_leases_released'] == 1
    assert reclaimed['business_event_leases_reclaimed'] == 1
    assert reclaimed['webhook_leases_reclaimed'] == 1
    assert reclaimed['delivery_sending_expired'] == 1
    d_stale.refresh_from_db()
    ev.refresh_from_db()
    wh.refresh_from_db()
    assert d_stale.status == 'UNKNOWN'  # Never blindly retried
    assert ev.status == 'PENDING'
    assert wh.state == 'PENDING'

    # Outbound kill switch (per-client + global) blocks dispatch before quota burn
    d_blocked = WhatsAppDelivery.objects.create(tenant=t1, dedup_key='blk-1', recipient_phone='+919800011111', payload={'text': 'blocked'}, status='PENDING')
    res_p = c_sa.post(f'/api/platform/tenants/{t1.pk}/outbound-pause/', json.dumps({'paused': True, 'reason': 'Compliance check'}), content_type='application/json')
    assert res_p.status_code == 200
    assert dispatch(d_blocked.pk) is False
    d_blocked.refresh_from_db()
    assert d_blocked.status == 'BLOCKED'
    assert 'Compliance check' in d_blocked.last_error
    assert TenantMonthlyUsage.objects.filter(tenant=t1).count() == 0

    # Global pause blocks too even if client pause cleared
    c_sa.post(f'/api/platform/tenants/{t1.pk}/outbound-pause/', json.dumps({'paused': False}), content_type='application/json')
    c_sa.post('/api/platform/system-settings/', json.dumps({'global_outbound_paused': True, 'global_outbound_pause_reason': 'Incident window'}), content_type='application/json')
    d_blk2 = WhatsAppDelivery.objects.create(tenant=t1, dedup_key='blk-2', recipient_phone='+919800011111', payload={'text': 'blocked2'}, status='PENDING')
    assert dispatch(d_blk2.pk) is False
    d_blk2.refresh_from_db()
    assert d_blk2.status == 'BLOCKED'
    assert 'Global outbound WhatsApp pause' in d_blk2.last_error

    # Maintenance mode returns 503 to client requests while keeping operator & /health/ up
    c_sa.post('/api/platform/system-settings/', json.dumps({'maintenance_mode': True, 'maintenance_message': 'Upgrading DB'}), content_type='application/json')
    c_own = Client()
    c_own.force_login(r3_env['owner1'])
    m_res = c_own.get('/api/inbox/conversations/')
    assert m_res.status_code == 503
    assert m_res.json()['maintenance_mode'] is True
    assert c_sa.get('/health/').status_code == 200
    c_sa.post('/api/platform/system-settings/', json.dumps({'maintenance_mode': False, 'global_outbound_paused': False}), content_type='application/json')
    assert c_own.get('/api/inbox/conversations/').status_code == 200


def test_billing_grace_reminder_and_usage_alerts(r3_env):
    t1 = r3_env['t1']
    sub = t1.subscription
    sub.status = SubscriptionStatus.EXPIRED
    sub.save(update_fields=['status'])
    assert t1.is_subscription_active is False

    c_sa = Client()
    c_sa.force_login(r3_env['sa'])
    grace_day = (timezone.localdate() + timedelta(days=5)).isoformat()
    res = c_sa.post(
        '/api/platform/tools/billing/',
        json.dumps({'action': 'set_grace', 'tenant_id': t1.pk, 'grace_until': grace_day, 'grace_notes': 'Wire pending'}),
        content_type='application/json',
    )
    assert res.status_code == 200
    t1.refresh_from_db()
    assert t1.is_subscription_active is True

    rem = c_sa.post(
        '/api/platform/tools/billing/',
        json.dumps({'action': 'send_reminder', 'tenant_id': t1.pk, 'note': 'Please settle invoice'}),
        content_type='application/json',
    )
    assert rem.status_code == 201
    assert TransactionalEmail.objects.filter(tenant=t1, purpose='BILLING_REMINDER').count() == 1

    # Usage alerts at >= 80%
    now = timezone.now()
    TenantMonthlyUsage.objects.create(tenant=t1, year=now.year, month=now.month, outbound_messages_sent=9)
    c_own = Client()
    c_own.force_login(r3_env['owner1'])
    usage = c_own.get('/api/usage/overview/').json()
    assert any(a['resource'] == 'Messages' and a['level'] == 'WARNING' for a in usage['alerts'])


def test_inbox_media_transfer_unread_and_search(r3_env):
    t1, t2 = r3_env['t1'], r3_env['t2']
    ConversationService.process_message('+919800055555', 'UniquePineapplePhrase looking for AC', channel=ChannelChoice.WHATSAPP, tenant=t1)
    conv = Conversation.objects.get(tenant=t1, customer__phone_number='+919800055555')
    conv.refresh_from_db()
    assert conv.unread_count >= 1

    c_own = Client()
    c_own.force_login(r3_env['owner1'])
    # Full-text search hits Message body
    search_res = c_own.get('/api/inbox/conversations/?q=UniquePineapplePhrase').json()
    assert len(search_res['conversations']) == 1
    assert search_res['conversations'][0]['unread_count'] >= 1

    # Switch to human and transfer to staff1; reject cross-tenant transfer target
    c_own.post(f'/conversations/{conv.pk}/action/', {'action': 'switch_to_human'})
    bad_tr = c_own.post(f'/api/inbox/conversations/{conv.pk}/transfer/', json.dumps({'target_user_id': r3_env['owner2'].pk}), content_type='application/json')
    assert bad_tr.status_code == 404
    ok_tr = c_own.post(f'/api/inbox/conversations/{conv.pk}/transfer/', json.dumps({'target_user_id': r3_env['staff1'].pk, 'note': 'Senior agent'}), content_type='application/json')
    assert ok_tr.status_code == 200
    assert ok_tr.json()['assigned_staff'] == 'staff_r3_1'

    # Staff1 uploads media and retrieves private media; Owner2 in t2 gets 404
    c_staff = Client()
    c_staff.force_login(r3_env['staff1'])
    c_staff.post(f'/api/inbox/conversations/{conv.pk}/mark-read/')
    conv.refresh_from_db()
    assert conv.unread_count == 0

    img = SimpleUploadedFile('brochure.png', b'\x89PNG\r\n\x1a\nfakeimagedata', content_type='image/png')
    with patch('apps.whatsapp.delivery.WhatsAppClient.upload_media', return_value=(True, 'meta_m_1')), \
         patch('apps.whatsapp.delivery.WhatsAppClient.send_media_message', return_value=(True, 'wamid.out.1')):
        up = c_staff.post(f'/api/inbox/conversations/{conv.pk}/media/', {'file': img, 'caption': 'See attached brochure'})
    assert up.status_code == 201
    msg_id = up.json()['message']['id']

    dl_ok = c_staff.get(f'/api/inbox/media/{msg_id}/')
    assert dl_ok.status_code == 200
    assert dl_ok['X-Content-Type-Options'] == 'nosniff'

    c_t2 = Client()
    c_t2.force_login(r3_env['owner2'])
    assert c_t2.get(f'/api/inbox/media/{msg_id}/').status_code == 404


def test_contacts_csv_import_tags_custom_fields_and_broadcast_mapping(r3_env):
    t1 = r3_env['t1']
    c_own = Client()
    c_own.force_login(r3_env['owner1'])

    csv_data = (
        'phone_number,name,email,tags,city\n'
        '+919800090001,Rohan,rohan@example.com,"vip,warm",Kochi\n'
        '+919800090002,,nocity@example.com,vip,\n'
        'invalid_phone,Bad,,vip,Delhi\n'
    )
    prev = c_own.post('/api/crm/contacts/import-preview/', json.dumps({'csv_text': csv_data}), content_type='application/json')
    assert prev.status_code == 200
    assert prev.json()['valid_new_count'] == 2
    assert prev.json()['invalid_count'] == 1

    imp = c_own.post('/api/crm/contacts/import/', json.dumps({'csv_text': csv_data}), content_type='application/json')
    assert imp.status_code == 201
    assert imp.json()['created_count'] == 2

    # Tag filter works and marketing consent is NOT auto-granted
    vip_list = c_own.get('/api/crm/contacts/?tag=warm').json()['contacts']
    assert len(vip_list) == 1
    assert vip_list[0]['custom_fields']['city'] == 'Kochi'
    rohan = Customer.objects.get(tenant=t1, phone_number='+919800090001')
    assert ContactConsent.objects.filter(contact=rohan).exists() is False

    # PATCH updates lifecycle_status cleanly
    patch_res = c_own.patch(f'/api/crm/contacts/{rohan.pk}/', json.dumps({'lifecycle_stage': 'CUSTOMER', 'tags': ['vip', 'warm', 'loyal']}), content_type='application/json')
    assert patch_res.status_code == 200
    rohan.refresh_from_db()
    assert rohan.lifecycle_status == 'CUSTOMER'
    assert 'loyal' in rohan.tags

    # Broadcast tag segmentation + per-contact variable mapping & fallback
    no_city = Customer.objects.get(tenant=t1, phone_number='+919800090002')
    ContactConsent.objects.create(tenant=t1, contact=rohan, has_consented=True, marketing_allowed=True, evidence_text='Signed card')
    ContactConsent.objects.create(tenant=t1, contact=no_city, has_consented=True, marketing_allowed=True, evidence_text='Signed card')
    tpl = WhatsAppTemplate.objects.create(tenant=t1, name='promo_city', category='MARKETING', language='en', body_text='Hi {{1}}, offer in {{2}}!', variables=['1', '2'], meta_status='APPROVED')

    camp_res = c_own.post('/api/crm/campaigns/', json.dumps({
        'name': 'City VIP Promo',
        'template_id': tpl.pk,
        'target_tags': ['warm'],
        'variable_mapping': [
            {'source': 'contact.name', 'fallback': 'Friend'},
            {'source': 'custom.city', 'fallback': 'your area'},
        ],
    }), content_type='application/json')
    assert camp_res.status_code == 201
    camp = Campaign.objects.get(pk=camp_res.json()['campaign_id'])
    assert list(eligible_audience(camp)) == [rohan]
    assert resolve_recipient_parameters(camp, rohan) == ['Rohan', 'Kochi']
    assert resolve_recipient_parameters(camp, no_city) == ['Contact 0002', 'your area']

    with patch('apps.crm.broadcasts.WhatsAppConfig.get_settings', return_value={'enabled': True, 'access_token': 'x', 'phone_number_id': 'y'}):
        launch(camp.pk, t1)
        run_campaigns()
    msg_rohan = Message.objects.filter(conversation__customer=rohan, direction=MessageDirection.OUTBOUND).order_by('-pk').first()
    assert msg_rohan.message_text == 'Hi Rohan, offer in Kochi!'


def test_automations_business_hours_followup_and_reports(r3_env):
    t1 = r3_env['t1']
    c_own = Client()
    c_own.force_login(r3_env['owner1'])

    # Configure business hours open ONLY Monday 09:00-10:00 Asia/Kolkata
    res = c_own.post('/api/crm/automations/settings/', json.dumps({
        'business_hours': {
            'enabled': True,
            'timezone': 'Asia/Kolkata',
            'days': {d: {'enabled': d == 'mon', 'start': '09:00', 'end': '10:00'} for d in ('mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun')},
        },
        'after_hours_auto_reply': 'We are currently closed. Expect a reply by 9 AM!',
        'no_response_followup_minutes': 10,
        'auto_assign_inbound': True,
    }), content_type='application/json')
    assert res.status_code == 200
    profile = BusinessProfile.objects.get(tenant=t1)
    # Sunday at noon IST -> closed
    sun_noon_utc = datetime(2026, 11, 22, 6, 30, tzinfo=py_timezone.utc)
    assert is_within_business_hours(profile, sun_noon_utc) is False

    # Simulated message during closed window -> away auto-reply once
    with patch('apps.chatbot.conversation_service.timezone.now', return_value=sun_noon_utc):
        r_away = ConversationService.process_message('+919800077777', 'Hello?', channel=ChannelChoice.WHATSAPP, tenant=t1)
    assert 'currently closed' in r_away['reply']

    # Overdue human handover without response -> follow-up task created
    conv = Conversation.objects.get(tenant=t1, customer__phone_number='+919800077777')
    Conversation.objects.filter(pk=conv.pk).update(
        status=ConversationStatus.HUMAN_HANDOVER,
        last_inbound_at=timezone.now() - timedelta(minutes=25),
        first_human_response_at=None,
        followup_alert_sent_at=None,
    )
    created = process_no_response_followups()
    assert created == 1
    assert Activity.objects.filter(tenant=t1, contact=conv.customer).exists()

    rep = c_own.get('/api/reports/overview/')
    assert rep.status_code == 200
    rep_json = rep.json()
    assert rep_json['conversations']['unanswered_inbound'] >= 1
    assert 'agents' in rep_json
    assert 'campaigns' in rep_json
