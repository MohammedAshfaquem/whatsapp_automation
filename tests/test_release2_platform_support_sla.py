"""
Comprehensive Release 2 Test Suite:
- Client-to-Platform SaaS Support strictly separate from CRM SupportTicket
- Setup-gated clients can open & reply to Platform Support tickets
- Cross-tenant isolation & internal platform notes completely hidden from clients
- 10-minute SLA escalation engine:
  * Follow-up client messages do NOT reset/postpone timer
  * Internal operator notes do NOT satisfy/clear SLA timer
  * Idempotent single alert per unanswered wait cycle (DB unique constraint + locks)
  * Public platform reply clears cycle; subsequent client reply starts fresh cycle
  * Pre-send recheck cancels pending alert if reply/resolve occurs before SMTP send
  * Attachment safety & tenant-scoped download
"""
from datetime import timedelta
import json
from unittest.mock import patch
import pytest
from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.utils import timezone

from apps.crm.models import SupportTicket as CrmCustomerTicket
from apps.tenants.email_service import send_email_job, unseal
from apps.tenants.models import (
    PlatformServiceConfig,
    PlatformSupportEscalation,
    PlatformSupportMessage,
    PlatformSupportTicket,
    PlatformTicketStatus,
    PlanTier,
    SubscriptionStatus,
    Tenant,
    TenantMembership,
    TenantRole,
    TenantSubscription,
    TransactionalEmail,
    UserSecurityProfile,
)
from apps.tenants.support_service import process_support_escalations

pytestmark = pytest.mark.django_db


@pytest.fixture
def support_env():
    plan = PlanTier.objects.create(
        code='basic',
        name='Basic',
        monthly_price=999,
        max_staff=5,
        enabled_modules=['shared_inbox', 'contacts_companies', 'team_management'],
    )
    t_a = Tenant.objects.create(name='Client Alpha Support', slug='client-alpha-sup', is_active=True, requires_meta_setup=True)
    t_b = Tenant.objects.create(name='Client Beta Support', slug='client-beta-sup', is_active=True, requires_meta_setup=False)
    for t in (t_a, t_b):
        TenantSubscription.objects.create(tenant=t, effective_plan=plan, status=SubscriptionStatus.ACTIVE)

    owner_a = User.objects.create_user('sup_owner_a', 'ownera@alpha-sup.com', 'StrongPass123!')
    owner_b = User.objects.create_user('sup_owner_b', 'ownerb@beta-sup.com', 'StrongPass123!')
    superadmin = User.objects.create_superuser('sup_platform', 'ops@neorizsolutions.com', 'PlatformPass123!')
    UserSecurityProfile.objects.create(user=owner_a, email_verified=True)
    UserSecurityProfile.objects.create(user=owner_b, email_verified=True)
    UserSecurityProfile.objects.create(user=superadmin, email_verified=True, is_trusted_seed=True)

    TenantMembership.objects.create(tenant=t_a, user=owner_a, role=TenantRole.OWNER, is_active=True)
    TenantMembership.objects.create(tenant=t_b, user=owner_b, role=TenantRole.OWNER, is_active=True)
    return {'t_a': t_a, 't_b': t_b, 'owner_a': owner_a, 'owner_b': owner_b, 'superadmin': superadmin}


def test_client_platform_ticket_separation_privacy_and_isolation(support_env):
    ca = Client()
    ca.force_login(support_env['owner_a'])
    cb = Client()
    cb.force_login(support_env['owner_b'])
    cp = Client()
    cp.force_login(support_env['superadmin'])

    # Even while t_a requires_meta_setup=True, owner_a can create & view platform support!
    bad_file = SimpleUploadedFile('xss.svg', b'<svg></svg>', content_type='image/svg+xml')
    bad_res = ca.post('/api/support/tickets/', {
        'subject': 'Webhook Question',
        'category': 'META_SETUP',
        'priority': 'HIGH',
        'description': 'Need Meta webhook help.',
        'attachment': bad_file,
    })
    assert bad_res.status_code == 400

    good_file = SimpleUploadedFile('debug.txt', b'webhook log 123', content_type='text/plain')
    ok_res = ca.post('/api/support/tickets/', {
        'subject': 'Need Meta API Setup Help',
        'category': 'META_SETUP',
        'priority': 'HIGH',
        'description': 'Cannot verify permanent token.',
        'attachment': good_file,
    })
    assert ok_res.status_code == 201
    ticket_id = ok_res.json()['ticket']['id']

    # Strictly separate from CRM Customer SupportTicket
    assert CrmCustomerTicket.objects.count() == 0
    assert PlatformSupportTicket.objects.count() == 1

    # Client cannot access platform queue
    assert ca.get('/api/platform/support/tickets/').status_code == 403

    # Tenant B cannot view, reply, resolve, or download Tenant A's ticket/attachment
    assert cb.get(f'/api/support/tickets/{ticket_id}/').status_code == 404
    assert cb.post(f'/api/support/tickets/{ticket_id}/reply/', data=json.dumps({'body': 'hijack'}), content_type='application/json').status_code == 404

    # Platform operator posts an internal note -> hidden from Client A!
    note_res = cp.post(
        f'/api/platform/support/tickets/{ticket_id}/reply/',
        data=json.dumps({'body': 'Internal Root Cause: customer Meta app secret mismatch', 'is_internal_note': True}),
        content_type='application/json',
    )
    assert note_res.status_code == 201

    detail_a = ca.get(f'/api/support/tickets/{ticket_id}/')
    assert detail_a.status_code == 200
    assert 'Internal Root Cause' not in detail_a.content.decode()
    assert len(detail_a.json()['messages']) == 1

    # Attachment download permitted for owning client, forbidden (404) for Tenant B
    att_url = detail_a.json()['messages'][0]['attachment']['url']
    assert ca.get(att_url).status_code == 200
    assert cb.get(att_url).status_code == 404

    # Platform operator sees the internal note
    detail_p = cp.get(f'/api/platform/support/tickets/{ticket_id}/')
    assert detail_p.status_code == 200
    assert 'Internal Root Cause' in detail_p.content.decode()


def test_ten_minute_sla_escalation_lifecycle_followups_notes_and_multicycle(support_env):
    ca = Client()
    ca.force_login(support_env['owner_a'])
    cp = Client()
    cp.force_login(support_env['superadmin'])

    res = ca.post('/api/support/tickets/', data=json.dumps({
        'subject': 'Urgent Outbound Halt',
        'category': 'WHATSAPP_DELIVERY',
        'priority': 'URGENT',
        'description': 'Messages queued cleanly but waiting review.',
    }), content_type='application/json')
    assert res.status_code == 201
    ticket = PlatformSupportTicket.objects.get(pk=res.json()['ticket']['id'])
    t0 = ticket.sla_cycle_started_at
    assert t0 is not None

    # Client sends an impatient follow-up message 5 minutes later -> MUST NOT push back t0!
    r2 = ca.post(f'/api/support/tickets/{ticket.pk}/reply/', data=json.dumps({'body': 'Following up please check.'}), content_type='application/json')
    assert r2.status_code == 201
    ticket.refresh_from_db()
    assert ticket.sla_cycle_started_at == t0

    # Platform posts an INTERNAL note -> MUST NOT clear t0 or satisfy SLA!
    cp.post(f'/api/platform/support/tickets/{ticket.pk}/reply/', data=json.dumps({'body': 'Checking worker logs', 'is_internal_note': True}), content_type='application/json')
    ticket.refresh_from_db()
    assert ticket.sla_cycle_started_at == t0

    # At 9m59s -> NOT yet escalated
    assert process_support_escalations(now=t0 + timedelta(minutes=9, seconds=59)) == 0
    assert PlatformSupportEscalation.objects.count() == 0

    # At 10m01s -> escalates ONCE cleanly to support@neorizsolutions.com
    assert process_support_escalations(now=t0 + timedelta(minutes=10, seconds=1)) == 1
    assert PlatformSupportEscalation.objects.filter(ticket=ticket).count() == 1
    assert TransactionalEmail.objects.filter(purpose='SUPPORT_ESCALATION', recipient='support@neorizsolutions.com').count() == 1

    # Re-running worker repeatedly within the same unanswered cycle sends ZERO duplicates!
    assert process_support_escalations(now=t0 + timedelta(minutes=15)) == 0
    assert PlatformSupportEscalation.objects.filter(ticket=ticket).count() == 1
    assert TransactionalEmail.objects.filter(purpose='SUPPORT_ESCALATION').count() == 1

    # Platform posts REAL public reply -> clears SLA timer and moves to AWAITING_CLIENT
    cp.post(f'/api/platform/support/tickets/{ticket.pk}/reply/', data=json.dumps({'body': 'Checked and resumed!'}), content_type='application/json')
    ticket.refresh_from_db()
    assert ticket.status == PlatformTicketStatus.AWAITING_CLIENT
    assert ticket.sla_cycle_started_at is None
    assert ticket.current_cycle_escalated is False

    # Client replies again -> starts NEW SLA Cycle 2!
    r3 = ca.post(f'/api/support/tickets/{ticket.pk}/reply/', data=json.dumps({'body': 'Still seeing one queued item.'}), content_type='application/json')
    assert r3.status_code == 201
    ticket.refresh_from_db()
    cycle2_t0 = ticket.sla_cycle_started_at
    assert cycle2_t0 is not None and cycle2_t0 > t0
    assert ticket.status == PlatformTicketStatus.AWAITING_PLATFORM

    # Cycle 2 < 10m -> no new escalation; Cycle 2 >= 10m -> escalates once for Cycle 2!
    assert process_support_escalations(now=cycle2_t0 + timedelta(minutes=6)) == 0
    assert process_support_escalations(now=cycle2_t0 + timedelta(minutes=10, seconds=5)) == 1
    assert PlatformSupportEscalation.objects.filter(ticket=ticket).count() == 2
    assert TransactionalEmail.objects.filter(purpose='SUPPORT_ESCALATION').count() == 2


def test_presend_recheck_cancels_alert_if_answered_or_resolved_and_smtp_dispatch(support_env):
    from apps.tenants.email_service import seal
    PlatformServiceConfig.objects.update_or_create(
        pk=1,
        defaults={
            'smtp_enabled': True,
            'smtp_host': 'smtp-relay.brevo.com',
            'smtp_port': 587,
            'smtp_username': 'u@neorizsolutions.com',
            'smtp_from_email': 'support@neorizsolutions.com',
            'smtp_security': 'TLS',
            'encrypted_secrets': seal({'smtp_password': 'smtp-test-secret-not-real'}),
            'support_alert_email': 'support@neorizsolutions.com',
            'support_escalation_minutes': 10,
        },
    )
    ca = Client()
    ca.force_login(support_env['owner_a'])
    cp = Client()
    cp.force_login(support_env['superadmin'])

    t1 = PlatformSupportTicket.objects.create(
        ticket_number='SUP-PRESEND1',
        tenant=support_env['t_a'],
        created_by=support_env['owner_a'],
        subject='Race test',
        status=PlatformTicketStatus.OPEN,
        sla_cycle_started_at=timezone.now() - timedelta(minutes=11),
    )
    # Escalate without letting process_support_escalations send SMTP yet
    with patch('apps.tenants.support_service.smtp_ready', return_value=False):
        assert process_support_escalations() == 1
    esc = PlatformSupportEscalation.objects.get(ticket=t1)
    job = esc.email_job
    assert esc.status == 'PENDING' and job.status == 'PENDING'

    # Platform resolves ticket BEFORE send_email_job dispatches -> job MUST cancel without SMTP call!
    cp.post(f'/api/platform/support/tickets/{t1.pk}/update/', data=json.dumps({'status': 'RESOLVED'}), content_type='application/json')
    with patch('apps.tenants.email_service.validate_smtp_host'), patch('apps.tenants.email_service.EmailMessage.send') as mock_send:
        assert send_email_job(job.pk) is False
        assert mock_send.call_count == 0
    esc.refresh_from_db(); job.refresh_from_db()
    assert esc.status == 'CANCELLED'
    assert job.status == 'EXPIRED'

    # Unanswered ticket dispatches cleanly via SMTP when still pending
    t2 = PlatformSupportTicket.objects.create(
        ticket_number='SUP-SEND2',
        tenant=support_env['t_a'],
        created_by=support_env['owner_a'],
        subject='Unanswered SLA alert',
        status=PlatformTicketStatus.OPEN,
        sla_cycle_started_at=timezone.now() - timedelta(minutes=12),
    )
    with patch('apps.tenants.email_service.validate_smtp_host'), patch('apps.tenants.email_service.EmailMessage.send', return_value=1) as mock_send:
        assert process_support_escalations() == 1
        assert mock_send.call_count == 1
    esc2 = PlatformSupportEscalation.objects.get(ticket=t2)
    assert esc2.status == 'SENT' and esc2.sent_at is not None
