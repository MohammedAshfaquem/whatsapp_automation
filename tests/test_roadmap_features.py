"""
Automated tests for Neoriz WhatsApp Automation comprehensive roadmap features:
- Sales Work Queue & Assignment
- Qualification & Explainable Lead Scoring
- Deal-linked Versioned Quotations & PDF Generator
- Workflow Automation Engine (triggers, actions, dry run, loop prevention)
- Customer Support Tickets & Post-Sale Onboarding Checklists
- Outbound Messaging Consent & Opt-out Suppression
- Integration Centre & Signed Outbound Webhooks with SSRF Protection
- Super Admin Client Provisioning Wizard & Operational Monitoring
"""
import pytest
import json
from decimal import Decimal
from django.urls import reverse
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, TenantMembership, TenantRole, PlanTier, UserSecurityProfile
from apps.chatbot.models import Customer, Conversation, ConversationStatus
from apps.crm.models import (
    Deal, DealStage, Pipeline, Company, Activity, ActivityStatus,
    Quote, QuoteItem, QuoteStatus,
    QualificationQuestion, LeadQualificationAnswer, LeadScore, LeadScorePriority,
    AutomationRule, AutomationRunLog, AutomationTrigger, AutomationActionType,
    SupportTicket, TicketNote, TicketPriority, TicketStatus,
    OnboardingChecklist, OnboardingTask,
    ContactConsent, ConsentSource, WhatsAppTemplate, Campaign,
    WebhookEndpoint, WebhookDeliveryLog
)
from apps.crm.assignment_service import assign_lead_round_robin, track_first_human_response
from apps.crm.automation_engine import dispatch_automation_event, dry_run_rule
from apps.crm.webhook_service import is_ssrf_safe_url

User = get_user_model()


@pytest.fixture
def test_setup(db):
    plan = PlanTier.objects.create(
        code='growth',
        name='Growth Plan',
        max_staff=5,
        max_contacts=5000,
        max_services=25,
        monthly_message_allowance=2500,
        monthly_price=Decimal('2999.00'),
        is_published=True
    )
    tenant = Tenant.objects.create(name='Apex Retailers', slug='apex-retailers', max_staff=5)
    
    # Superadmin
    superadmin = User.objects.create_superuser(username='ops_superadmin', email='ops@neorizsolutions.com', password='secretpassword123')
    UserSecurityProfile.objects.create(user=superadmin, email_verified=True)

    # Tenant Admin
    admin_user = User.objects.create_user(username='apex_admin', email='admin@apex.com', password='password123')
    UserSecurityProfile.objects.create(user=admin_user, email_verified=True)
    TenantMembership.objects.create(tenant=tenant, user=admin_user, role=TenantRole.ADMIN, is_active=True)

    # Sales Agent
    agent_user = User.objects.create_user(username='apex_agent', email='agent@apex.com', password='password123')
    UserSecurityProfile.objects.create(user=agent_user, email_verified=True)
    TenantMembership.objects.create(tenant=tenant, user=agent_user, role=TenantRole.STAFF, is_active=True)

    # Pipeline and stages
    pipeline = Pipeline.objects.create(tenant=tenant, name='Standard Sales', is_default=True)
    stage_new = DealStage.objects.create(pipeline=pipeline, name='New', order=1, probability=10)
    stage_won = DealStage.objects.create(pipeline=pipeline, name='Closed Won', order=6, probability=100, is_won=True)

    # Customer Contact
    contact = Customer.objects.create(
        tenant=tenant,
        name='Vikram Seth',
        phone_number='+919876543210',
        email='vikram@example.com'
    )

    # Deal
    deal = Deal.objects.create(
        tenant=tenant,
        title='Apex Omnichannel POS',
        contact=contact,
        pipeline=pipeline,
        stage=stage_new,
        amount=Decimal('85000.00'),
        owner=admin_user
    )

    return {
        'tenant': tenant,
        'superadmin': superadmin,
        'admin_user': admin_user,
        'agent_user': agent_user,
        'contact': contact,
        'deal': deal,
        'stage_new': stage_new,
        'stage_won': stage_won,
    }


def test_sales_work_queue_and_assignment(client, test_setup):
    """Test work queue aggregation and round-robin assignment."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    agent = test_setup['agent_user']
    contact = test_setup['contact']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create an unassigned conversation
    conv = Conversation.objects.create(
        tenant=tenant,
        customer=contact,
        status=ConversationStatus.BOT_ACTIVE,
        unresolved_count=1
    )

    resp = client.get('/api/crm/work-queue/')
    assert resp.status_code == 200
    data = resp.json()
    assert data['summary']['unanswered_count'] >= 1
    assert data['unanswered_enquiries'][0]['contact_name'] == 'Vikram Seth'

    # Test round-robin assignment
    assigned_user = assign_lead_round_robin(tenant, contact=contact, conversation=conv)
    assert assigned_user in [admin, agent]
    assert contact.owner is not None
    assert conv.assigned_staff is not None

    # Test first human response tracking
    first_resp_time = track_first_human_response(conv, agent)
    assert first_resp_time is not None
    assert conv.status == ConversationStatus.HUMAN_HANDOVER
    assert conv.unresolved_count == 0


def test_lead_qualification_and_explainable_scoring(client, test_setup):
    """Test qualification questions, answers, and deterministic score breakdown."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    contact = test_setup['contact']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create question
    q = QualificationQuestion.objects.create(
        tenant=tenant,
        field_key='budget_range',
        question_text='What is your anticipated annual budget?',
        is_required=True
    )

    # Submit answer
    payload = {
        'contact_id': contact.id,
        'question_id': q.id,
        'answer_text': 'INR 1,00,000 - 2,00,000',
        'source_message': 'Our budget is around 1.5 Lakhs'
    }
    resp = client.post('/api/crm/qualification/', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 200
    data = resp.json()
    assert data['status'] == 'saved'
    assert 'breakdown' in data
    assert data['score'] > 0

    # Retrieve score
    resp = client.get(f'/api/crm/scoring/{contact.id}/')
    assert resp.status_code == 200
    score_data = resp.json()
    assert score_data['score'] > 0
    assert 'deal_value' in score_data['breakdown']
    assert score_data['is_manual_override'] is False

    # Manual score override with required reason
    override_payload = {'score': 95, 'reason': 'Executive sponsor verbally committed at meeting'}
    resp = client.post(f'/api/crm/scoring/{contact.id}/', data=json.dumps(override_payload), content_type='application/json')
    assert resp.status_code == 200
    assert resp.json()['score'] == 95
    assert resp.json()['priority'] == 'URGENT'


def test_deal_quotations_and_pdf_generation(client, test_setup):
    """Test versioned quotation lifecycle and valid PDF generation."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    deal = test_setup['deal']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create quote with 2 line items
    quote_payload = {
        'title': 'Enterprise WhatsApp Setup + CRM',
        'discount': 5000,
        'tax_percent': 18.0,
        'terms': 'Payment 50% advance upon signing.',
        'items': [
            {'description': 'WhatsApp Cloud API Setup & Integration', 'quantity': 1, 'unit_price': 40000, 'discount_percent': 0},
            {'description': 'Sales Agent Training & Knowledge Grounding', 'quantity': 2, 'unit_price': 15000, 'discount_percent': 10}
        ]
    }
    resp = client.post(f'/api/crm/deals/{deal.id}/quotes/', data=json.dumps(quote_payload), content_type='application/json')
    assert resp.status_code == 201
    q_data = resp.json()
    quote_id = q_data['quote_id']
    assert q_data['version'] == 1

    # Verify calculation:
    # Item 1: 1 * 40000 = 40000
    # Item 2: 2 * 15000 - 10% = 30000 - 3000 = 27000
    # Subtotal = 67000
    # Discount = 5000 -> Taxable = 62000
    # Tax (18%) = 11160
    # Total = 73160
    quote = Quote.objects.get(id=quote_id)
    assert quote.subtotal == Decimal('67000.00')
    assert quote.total_amount == Decimal('73160.00')

    # Update status to APPROVED
    resp = client.post(f'/api/crm/quotes/{quote_id}/status/', data=json.dumps({'status': 'APPROVED'}), content_type='application/json')
    assert resp.status_code == 200
    quote.refresh_from_db()
    assert quote.status == QuoteStatus.APPROVED
    deal.refresh_from_db()
    assert deal.amount == Decimal('73160.00')

    # Test PDF generation endpoint
    pdf_resp = client.get(f'/api/crm/quotes/{quote_id}/pdf/')
    assert pdf_resp.status_code == 200
    assert pdf_resp['Content-Type'] == 'application/pdf'
    assert pdf_resp.content.startswith(b'%PDF-1.4')
    assert b'QUOTATION' in pdf_resp.content


def test_workflow_automation_engine_and_loop_prevention(client, test_setup):
    """Test rule creation, dry-run, event dispatching, and recursive loop termination."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    deal = test_setup['deal']
    contact = test_setup['contact']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create automation rule: When deal is won -> Create Onboarding Checklist
    rule = AutomationRule.objects.create(
        tenant=tenant,
        name='Auto Onboarding on Deal Won',
        trigger_type=AutomationTrigger.DEAL_WON,
        conditions={'stage_name': 'Closed Won'},
        action_type=AutomationActionType.CREATE_ONBOARDING,
        is_active=True
    )

    # Dry-run preview
    preview = dry_run_rule(rule, {'stage_name': 'Closed Won'})
    assert preview['matches_conditions'] is True
    assert preview['simulated_outcome']['dry_run'] is True

    # Real dispatch
    results = dispatch_automation_event(
        tenant=tenant,
        trigger_type=AutomationTrigger.DEAL_WON,
        entity_id=deal.id,
        context={'stage_name': 'Closed Won'}
    )
    assert len(results) == 1
    assert results[0]['status'] == 'SUCCESS'
    
    # Check that onboarding checklist was automatically created
    checklist = OnboardingChecklist.objects.filter(deal=deal).first()
    assert checklist is not None
    assert checklist.tasks.count() == 4

    # Test loop termination protection at depth > 3
    deep_results = dispatch_automation_event(
        tenant=tenant,
        trigger_type=AutomationTrigger.DEAL_WON,
        entity_id=deal.id,
        context={'stage_name': 'Closed Won'},
        call_depth=4
    )
    assert deep_results == []


def test_customer_support_tickets_and_notes(client, test_setup):
    """Test support ticket creation with response target hours and internal notes."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    contact = test_setup['contact']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create ticket
    payload = {
        'contact_id': contact.id,
        'subject': 'Unable to send catalog images on WhatsApp',
        'description': 'Customer reported media upload timeout error.',
        'category': 'TECHNICAL',
        'priority': 'URGENT'
    }
    resp = client.post('/api/crm/tickets/', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 201
    ticket_id = resp.json()['ticket_id']

    ticket = SupportTicket.objects.get(id=ticket_id)
    assert ticket.ticket_number.startswith('TICK-')
    assert ticket.response_target_hours == 4  # Urgent priority = 4h target
    assert ticket.status == TicketStatus.OPEN

    # Add internal ticket note
    resp = client.post(f'/api/crm/tickets/{ticket_id}/notes/', data=json.dumps({'content': 'Checked Meta API status: incident resolved.'}), content_type='application/json')
    assert resp.status_code == 201
    assert ticket.notes.count() == 1

    # Resolve ticket
    resp = client.post(f'/api/crm/tickets/{ticket_id}/status/', data=json.dumps({'status': 'RESOLVED', 'resolution_reason': 'Meta webhook restored'}), content_type='application/json')
    assert resp.status_code == 200
    ticket.refresh_from_db()
    assert ticket.status == TicketStatus.RESOLVED
    assert ticket.resolved_at is not None


def test_growth_tools_and_consent_suppression(client, test_setup):
    """Test contact consent tracking, opt-out suppression, and campaign audience filter."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    contact = test_setup['contact']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Record consent
    resp = client.post(f'/api/crm/consent/{contact.id}/', data=json.dumps({
        'is_opted_out': False,
        'source': 'WEBSITE_FORM',
        'has_consented': True,
        'marketing_allowed': True,
        'evidence_text': 'Accepted Terms and Marketing updates on consultation form'
    }), content_type='application/json')
    assert resp.status_code == 200

    # Create campaign draft
    resp = client.post('/api/crm/campaigns/', data=json.dumps({'name': 'Q4 Retail Automation Offer'}), content_type='application/json')
    assert resp.status_code == 201
    assert resp.json()['audience_count'] == 1

    # Opt customer out (Suppression active)
    resp = client.post(f'/api/crm/consent/{contact.id}/', data=json.dumps({'is_opted_out': True}), content_type='application/json')
    assert resp.status_code == 200
    assert resp.json()['is_opted_out'] is True

    # Re-calculate campaign audience: should now be 0 due to suppression
    resp = client.post('/api/crm/campaigns/', data=json.dumps({'name': 'Q4 Retail Automation Offer 2'}), content_type='application/json')
    assert resp.status_code == 201
    assert resp.json()['audience_count'] == 0


def test_signed_outbound_webhooks_and_ssrf_blocking(client, test_setup):
    """Test signed outbound webhook registration and SSRF protection."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']

    client.force_login(admin)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Verify SSRF helper rejects dangerous loopback/internal hosts
    assert is_ssrf_safe_url('http://127.0.0.1:8000/webhook') is False
    assert is_ssrf_safe_url('http://localhost:3000/api') is False
    assert is_ssrf_safe_url('http://169.254.169.254/latest/meta-data/') is False
    assert is_ssrf_safe_url('http://192.168.1.5/hook') is False
    assert is_ssrf_safe_url('http://10.0.0.1/hook') is False
    assert is_ssrf_safe_url('https://api.externalclient.com/webhook') is True

    # Attempt to register dangerous SSRF url -> rejected with 400
    resp = client.post('/api/crm/webhooks/', data=json.dumps({'target_url': 'http://127.0.0.1:8000/internal'}), content_type='application/json')
    assert resp.status_code == 400
    assert 'SSRF' in resp.json()['error']

    # Register valid public webhook endpoint
    resp = client.post('/api/crm/webhooks/', data=json.dumps({
        'target_url': 'https://api.externalclient.com/webhook',
        'subscribed_events': ['deal.won', 'ticket.created']
    }), content_type='application/json')
    assert resp.status_code == 201
    assert WebhookEndpoint.objects.filter(tenant=tenant).count() == 1


def test_superadmin_client_provisioning_and_monitoring(client, test_setup):
    """Test Super Admin client creation wizard and operational health monitoring."""
    superadmin = test_setup['superadmin']
    admin = test_setup['admin_user']

    # Non-superadmin cannot access client provisioning
    client.force_login(admin)
    resp = client.post('/api/platform/clients/create/', data=json.dumps({'name': 'Alpha Corp'}), content_type='application/json')
    assert resp.status_code == 403

    # Superadmin provisions client workspace
    client.force_login(superadmin)
    payload = {
        'name': 'Alpha Logistics',
        'whatsapp_number': '+12025550195',
        'slug': 'alpha-logistics',
        'admin_email': 'director@alphalogistics.com',
        'admin_name': 'Kareem Ahmed',
        'plan_code': 'growth',
        'timezone': 'Asia/Kolkata'
    }
    resp = client.post('/api/platform/clients/create/', data=json.dumps(payload), content_type='application/json')
    assert resp.status_code == 201
    data = resp.json()
    assert data['status'] == 'provisioned'
    assert data['activation_url'].startswith('/activate/')
    
    # Verify new tenant and membership were created
    new_tenant = Tenant.objects.get(slug='alpha-logistics')
    assert new_tenant.memberships.filter(role=TenantRole.OWNER).exists()
    assert new_tenant.max_staff == 5

    # Check Superadmin operational monitoring
    resp = client.get('/api/platform/monitoring/')
    assert resp.status_code == 200
    m_data = resp.json()
    assert 'overall_health' in m_data
    assert 'failed_deliveries_count' in m_data


def test_durable_business_event_outbox_and_idempotent_automation(test_setup):
    """Test transactional outbox persistence, atomic execution claim, and duplicate suppression."""
    tenant = test_setup['tenant']
    admin = test_setup['admin_user']
    deal = test_setup['deal']

    # Create an automation rule for deal.stage_changed
    rule = AutomationRule.objects.create(
        tenant=tenant,
        name='Follow Up on Discovery',
        trigger_type=AutomationTrigger.STAGE_CHANGED,
        conditions={'stage_name': 'New'},
        action_type=AutomationActionType.CREATE_TASK,
        action_config={'task_title': 'Call customer within 24h', 'due_days': 1},
        is_active=True,
        version=1
    )

    from apps.crm.automation_engine import record_business_event, process_business_event
    from apps.crm.models import BusinessEvent

    initial_tasks = Activity.objects.filter(tenant=tenant).count()

    # Emitting outbox event
    event = record_business_event(
        tenant=tenant,
        event_type=AutomationTrigger.STAGE_CHANGED,
        entity_type='deal',
        entity_id=deal.id,
        payload={'stage_name': 'New', 'deal_title': deal.title, 'amount': '85000.00'},
        dedup_key=f"deal:{deal.id}:test_stage_changed"
    )
    assert event.status == 'PENDING'
    assert event.event_id is not None

    # Processing event first time
    results = process_business_event(event)
    assert len(results) == 1
    assert results[0]['status'] == 'SUCCESS'

    event.refresh_from_db()
    assert event.status == 'PROCESSED'
    assert Activity.objects.filter(tenant=tenant).count() == initial_tasks + 1

    # Verifying AutomationRunLog record with stable idempotency key
    log = AutomationRunLog.objects.get(event=event, rule=rule)
    assert log.status == 'SUCCESS'
    import hashlib
    expected_key = hashlib.sha256(f"{tenant.id}:{rule.id}:{rule.version}:{event.event_id}".encode()).hexdigest()
    assert log.idempotency_key == expected_key

    # Retrying process on the exact same event -> idempotent skip, no duplicate tasks
    retry_results = process_business_event(event)
    assert len(retry_results) == 0
    assert Activity.objects.filter(tenant=tenant).count() == initial_tasks + 1


def test_automation_loop_prevention_causation_depth(test_setup):
    """Test cascading loop termination at causation_depth > 3."""
    tenant = test_setup['tenant']
    from apps.crm.automation_engine import record_business_event
    from apps.crm.models import BusinessEvent

    event = record_business_event(
        tenant=tenant,
        event_type=AutomationTrigger.STAGE_CHANGED,
        entity_type='deal',
        entity_id=1,
        payload={'loop': True},
        causation_depth=4  # Exceeds limit 3
    )
    assert event.status == 'DEAD_LETTER'
    assert 'Maximum causation depth exceeded' in event.last_error


def test_hardened_ssrf_and_dns_rebinding_guards():
    """Verify robust rejection across full forbidden address space and DNS rebinding prevention."""
    from apps.crm.webhook_service import validate_webhook_url, is_destination_ip_safe, pinned_dns_resolver
    import socket

    # 1. Embedded credentials rejected
    safe, err, _ = validate_webhook_url('https://admin:pass@api.externalclient.com/webhook')
    assert safe is False
    assert 'embedded credentials' in err.lower()

    # 2. Forbidden ports rejected
    safe, err, _ = validate_webhook_url('https://api.externalclient.com:22/webhook')
    assert safe is False
    assert 'permitted' in err.lower()

    # 3. Cloud metadata IPv4 & IPv6 rejected
    safe, err = is_destination_ip_safe('169.254.169.254')
    assert safe is False
    assert 'metadata' in err.lower() or 'link-local' in err.lower()

    safe, err = is_destination_ip_safe('fd00:ec2::254')
    assert safe is False
    assert 'metadata' in err.lower()

    # 4. IPv4-mapped IPv6 loopback & private rejected
    safe, err = is_destination_ip_safe('::ffff:127.0.0.1')
    assert safe is False
    assert 'loopback' in err.lower()

    safe, err = is_destination_ip_safe('::ffff:10.0.0.1')
    assert safe is False
    assert 'private' in err.lower()

    # 5. Multicast & Unspecified rejected
    safe, _ = is_destination_ip_safe('224.0.0.1')
    assert safe is False
    safe, _ = is_destination_ip_safe('0.0.0.0')
    assert safe is False

    # 6. Safe public IP accepted
    safe, _ = is_destination_ip_safe('93.184.216.34')
    assert safe is True

    # 7. Thread-safe Pinned DNS backend tests
    from apps.crm.webhook_service import PinnedDNSBackend
    backend = PinnedDNSBackend({'custom-host.example': '93.184.216.34'})
    assert backend.pinned_map.get('custom-host.example') == '93.184.216.34'
    with pinned_dns_resolver({'custom-host.example': '93.184.216.34'}):
        pass  # Backward compatible context manager does not raise


def test_real_deal_transition_triggers_durable_outbox_event(test_setup):
    """Test that change_deal_stage persists real outbox events inside transaction."""
    deal = test_setup['deal']
    stage_won = test_setup['stage_won']
    admin = test_setup['admin_user']

    from apps.crm.services import change_deal_stage
    from apps.crm.models import BusinessEvent

    updated_deal = change_deal_stage(deal.id, stage_won.id, user=admin, notes="Signed contract")
    assert updated_deal.stage_id == stage_won.id

    # Verify deal.stage_changed event
    stage_event = BusinessEvent.objects.filter(
        tenant=deal.tenant,
        event_type='deal.stage_changed',
        entity_id=deal.id
    ).first()
    assert stage_event is not None
    assert stage_event.payload['to_stage'] == 'Closed Won'

    # Verify deal.won event with causation link
    won_event = BusinessEvent.objects.filter(
        tenant=deal.tenant,
        event_type='deal.won',
        entity_id=deal.id
    ).first()
    assert won_event is not None
    assert won_event.causation_id == stage_event.event_id


def test_expired_lease_reclamation_across_queues(test_setup):
    """Test that expired PROCESSING leases in business events and webhooks are reclaimed."""
    from datetime import timedelta
    from django.utils import timezone
    from apps.crm.models import BusinessEvent, WebhookEndpoint, WebhookDeliveryLog
    from apps.crm.automation_engine import reclaim_expired_business_event_leases
    from apps.crm.webhook_service import reclaim_expired_webhook_leases

    tenant = test_setup['tenant']
    past_time = timezone.now() - timedelta(minutes=10)

    # 1. Business event lease recovery
    evt_recoverable = BusinessEvent.objects.create(
        tenant=tenant,
        event_id='evt_lease_1',
        event_type='test.event',
        entity_type='deal',
        entity_id=1,
        status='PROCESSING',
        attempts=1,
        lease_expires_at=past_time,
        claim_token='token123'
    )
    evt_exhausted = BusinessEvent.objects.create(
        tenant=tenant,
        event_id='evt_lease_2',
        event_type='test.event',
        entity_type='deal',
        entity_id=2,
        status='PROCESSING',
        attempts=5,
        lease_expires_at=past_time,
        claim_token='token456'
    )

    reclaimed_count = reclaim_expired_business_event_leases()
    assert reclaimed_count == 2

    evt_recoverable.refresh_from_db()
    assert evt_recoverable.status == 'PENDING'
    assert evt_recoverable.lease_expires_at is None
    assert evt_recoverable.claim_token == ''

    evt_exhausted.refresh_from_db()
    assert evt_exhausted.status == 'DEAD_LETTER'

    # 2. Webhook delivery log lease recovery
    ep = WebhookEndpoint.objects.create(
        tenant=tenant,
        target_url='https://api.externalclient.com/webhook',
        signing_secret='secret123'
    )
    wh_recoverable = WebhookDeliveryLog.objects.create(
        endpoint=ep,
        event_type='test.event',
        event_id='wh_lease_1',
        state='PROCESSING',
        attempts=1,
        max_attempts=5,
        lease_expires_at=past_time,
        claim_token='tokenwh1'
    )
    wh_exhausted = WebhookDeliveryLog.objects.create(
        endpoint=ep,
        event_type='test.event',
        event_id='wh_lease_2',
        state='PROCESSING',
        attempts=5,
        max_attempts=5,
        lease_expires_at=past_time,
        claim_token='tokenwh2'
    )

    wh_reclaimed = reclaim_expired_webhook_leases()
    assert wh_reclaimed == 2

    wh_recoverable.refresh_from_db()
    assert wh_recoverable.state == 'PENDING'
    assert wh_recoverable.lease_expires_at is None
    assert wh_recoverable.claim_token == ''

    wh_exhausted.refresh_from_db()
    assert wh_exhausted.state == 'DEAD_LETTER'


def test_failed_automation_retry_recovery(test_setup):
    """Test that failed or expired automation runs are retried up to 3 attempts."""
    from datetime import timedelta
    from django.utils import timezone
    import hashlib
    from apps.crm.models import BusinessEvent, AutomationRule, AutomationRunLog, AutomationTrigger, AutomationActionType, Activity
    from apps.crm.automation_engine import process_business_event

    tenant = test_setup['tenant']
    deal = test_setup['deal']

    rule = AutomationRule.objects.create(
        tenant=tenant,
        name='Task Creator Rule',
        trigger_type=AutomationTrigger.STAGE_CHANGED,
        conditions={},
        action_type=AutomationActionType.CREATE_TASK,
        action_config={'task_title': 'Retryable Task'},
        is_active=True,
        version=1
    )

    event = BusinessEvent.objects.create(
        tenant=tenant,
        event_id='evt_failed_retry_1',
        event_type=AutomationTrigger.STAGE_CHANGED,
        entity_type='deal',
        entity_id=deal.id,
        payload={'stage_name': 'New'},
        status='PENDING'
    )

    # Seed an earlier run log as FAILED
    idempotency_key = hashlib.sha256(
        f"{tenant.id}:{rule.id}:{rule.version}:{event.event_id}".encode()
    ).hexdigest()

    run_log = AutomationRunLog.objects.create(
        tenant=tenant,
        rule=rule,
        event=event,
        trigger_event=event.event_type,
        entity_id=deal.id,
        status='FAILED',
        details={'error': 'Simulated transient network timeout'},
        idempotency_key=idempotency_key,
        attempt_count=1,
        execution_lease_expires_at=timezone.now() - timedelta(minutes=5)
    )

    initial_tasks = Activity.objects.filter(tenant=tenant).count()

    # Re-process event: should reclaim the failed run log and succeed
    results = process_business_event(event)
    assert len(results) == 1
    assert results[0]['status'] == 'SUCCESS'

    run_log.refresh_from_db()
    assert run_log.status == 'SUCCESS'
    assert run_log.attempt_count == 2
    assert Activity.objects.filter(tenant=tenant).count() == initial_tasks + 1


def test_webhook_enqueue_deduplication(test_setup):
    """Test that repeated enqueue calls for the same event and endpoint return the same delivery without duplication."""
    from apps.crm.models import WebhookEndpoint, WebhookDeliveryLog
    from apps.crm.webhook_service import enqueue_outbound_webhooks

    tenant = test_setup['tenant']
    ep = WebhookEndpoint.objects.create(
        tenant=tenant,
        target_url='https://api.externalclient.com/webhook',
        signing_secret='secret123',
        subscribed_events=['lead.created']
    )

    deliveries_first = enqueue_outbound_webhooks(tenant, 'lead.created', 'evt_dedup_99', {'foo': 'bar'})
    assert len(deliveries_first) == 1

    deliveries_second = enqueue_outbound_webhooks(tenant, 'lead.created', 'evt_dedup_99', {'foo': 'bar'})
    assert len(deliveries_second) == 1

    assert deliveries_first[0].id == deliveries_second[0].id
    assert WebhookDeliveryLog.objects.filter(endpoint=ep, event_id='evt_dedup_99').count() == 1


def test_streaming_response_truncation_bound(test_setup, monkeypatch):
    """Test that response streaming limits read bytes to at most 2048 bytes."""
    from apps.crm.models import WebhookEndpoint, WebhookDeliveryLog
    from apps.crm.webhook_service import execute_webhook_delivery_attempt
    import io

    tenant = test_setup['tenant']
    ep = WebhookEndpoint.objects.create(
        tenant=tenant,
        target_url='https://api.externalclient.com/webhook',
        signing_secret='secret123'
    )
    delivery = WebhookDeliveryLog.objects.create(
        endpoint=ep,
        event_type='test.event',
        event_id='wh_stream_1',
        state='PENDING'
    )

    # Mock response returning a huge 50,000-character payload
    huge_data = b"X" * 50000

    class MockStreamResponse:
        status_code = 200
        def iter_bytes(self, chunk_size=1024):
            stream = io.BytesIO(huge_data)
            while True:
                chunk = stream.read(chunk_size)
                if not chunk:
                    break
                yield chunk
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass

    import httpx
    monkeypatch.setattr(httpx.Client, 'stream', lambda self, method, url, **kwargs: MockStreamResponse())

    success = execute_webhook_delivery_attempt(delivery)
    assert success is True
    delivery.refresh_from_db()
    assert len(delivery.response_body.encode('utf-8')) <= 2048


def test_unified_retry_worker_cycle(test_setup):
    """Test that the unified operational retry worker cycle executes without unhandled errors."""
    import logging
    from config.retry_worker import run_worker_cycle

    logger = logging.getLogger('test_worker')
    # Should run lease reclamation, pending business events, pending webhooks, and whatsapp retry
    run_worker_cycle(logger)
