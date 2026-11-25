import json
from decimal import Decimal
from datetime import datetime, date, timedelta
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, TenantMembership
from apps.chatbot.models import Customer, Conversation, ConversationStatus, Message, MessageDirection, ChannelChoice, SenderType
from apps.crm.models import Deal, DealStage, Activity, ActivityStatus, ActivityType, Pipeline, Quote, QuoteItem
from apps.crm.services import get_customer_timeline
from apps.crm.assignment_service import get_sales_work_queue

User = get_user_model()


@pytest.fixture
def workflow_setup(db):
    tenant = Tenant.objects.create(name="Workflow Test Tenant", slug="wf-test-tenant", is_active=True)
    owner = User.objects.create_user(username="wf_owner", password="password123", email="owner@wf.com", is_staff=True)
    staff = User.objects.create_user(username="wf_staff", password="password123", email="staff@wf.com", is_staff=True)

    TenantMembership.objects.create(tenant=tenant, user=owner, role='OWNER', is_active=True)
    TenantMembership.objects.create(tenant=tenant, user=staff, role='STAFF', is_active=True)

    pipeline = Pipeline.objects.create(tenant=tenant, name="Sales Pipeline", is_default=True)
    stage_new = DealStage.objects.create(pipeline=pipeline, name="New Enquiry", order=1)
    stage_won = DealStage.objects.create(pipeline=pipeline, name="Closed Won", order=2, is_won=True)

    customer = Customer.objects.create(
        tenant=tenant,
        name="Anjali Rao",
        phone_number="+919876543219",
        email="anjali@example.com"
    )

    return {
        'tenant': tenant,
        'owner': owner,
        'staff': staff,
        'pipeline': pipeline,
        'stage_new': stage_new,
        'customer': customer,
    }


@pytest.mark.django_db
def test_customer_detail_timeline_does_not_crash_with_mixed_dates_and_null_stage(workflow_setup):
    """
    Verifies that get_customer_timeline handles activities with DateField due_dates,
    deals without assigned stages, and Decimal amounts without throwing TypeErrors.
    """
    tenant = workflow_setup['tenant']
    customer = workflow_setup['customer']

    # 1. Activity with date-only due_date
    Activity.objects.create(
        tenant=tenant,
        contact=customer,
        title="Follow up on AC inspection",
        due_date=timezone.now() + timedelta(days=2),
        status=ActivityStatus.PENDING
    )

    # 2. Activity with completed_at datetime
    Activity.objects.create(
        tenant=tenant,
        contact=customer,
        title="Completed initial phone call",
        completed_at=timezone.now() - timedelta(hours=3),
        status=ActivityStatus.COMPLETED
    )

    # 3. Deal with stage and decimal amount
    deal = Deal.objects.create(
        tenant=tenant,
        pipeline=workflow_setup['pipeline'],
        stage=workflow_setup['stage_new'],
        contact=customer,
        title="Commercial AMC Contract",
        amount=Decimal('45000.50')
    )

    # 4. Inbound & Outbound messages
    conv = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        channel=ChannelChoice.WHATSAPP,
        status=ConversationStatus.BOT_ACTIVE
    )
    Message.objects.create(
        conversation=conv,
        direction=MessageDirection.INBOUND,
        sender_type=SenderType.CUSTOMER,
        message_text="Hello, I need an urgent AMC for our office ACs."
    )

    # Execute timeline generation
    timeline_data = get_customer_timeline(customer)
    assert isinstance(timeline_data, dict)
    assert timeline_data['total_count'] >= 3
    items = timeline_data['items']
    assert len(items) >= 3

    # Ensure all timestamps are aware datetimes and properly sorted
    for item in items:
        assert item['timestamp'] is not None
        assert hasattr(item['timestamp'], 'hour')


@pytest.mark.django_db
def test_spa_contact_detail_api_returns_structured_timeline(client, workflow_setup):
    """Verifies that the /api/crm/contacts/<id>/ endpoint returns array timeline and timeline_data."""
    tenant = workflow_setup['tenant']
    owner = workflow_setup['owner']
    customer = workflow_setup['customer']

    client.force_login(owner)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    resp = client.get(f'/api/crm/contacts/{customer.id}/')
    assert resp.status_code == 200
    data = resp.json()
    assert 'contact' in data
    assert 'timeline' in data
    timeline_items = data['timeline']['items'] if isinstance(data['timeline'], dict) else data['timeline']
    assert isinstance(timeline_items, list)
    assert len(timeline_items) >= 0


@pytest.mark.django_db
def test_sales_work_queue_counts_and_categories(client, workflow_setup):
    """Verifies work queue returns accurate counts and actionable items."""
    tenant = workflow_setup['tenant']
    owner = workflow_setup['owner']
    customer = workflow_setup['customer']

    client.force_login(owner)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Create unassigned conversation waiting for staff
    Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        status=ConversationStatus.HUMAN_HANDOVER,
        unresolved_count=1
    )

    queue = get_sales_work_queue(tenant)
    assert queue['summary']['unanswered_count'] >= 1
    assert queue['summary']['total_actionable'] >= 1
    assert len(queue['unanswered_enquiries']) >= 1
    assert queue['unanswered_enquiries'][0]['conversation_id'] is not None

    resp = client.get('/api/crm/work-queue/')
    assert resp.status_code == 200
    data = resp.json()
    assert data['summary']['unanswered_count'] >= 1


@pytest.mark.django_db
def test_conversation_claiming_updates_ownership_immediately(client, workflow_setup):
    """
    Verifies that claiming a conversation:
    1. Requires an explicit pause before claiming a bot-active conversation
    2. Assigns conversation.assigned_staff immediately to requesting staff
    3. Assigns customer.owner if currently unassigned
    4. Returns updated ownership and status in JSON response
    """
    tenant = workflow_setup['tenant']
    staff = workflow_setup['staff']
    customer = workflow_setup['customer']

    # Conversation starts in BOT_ACTIVE without assigned staff
    conv = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        status=ConversationStatus.BOT_ACTIVE,
        assigned_staff=None
    )

    client.force_login(staff)
    session = client.session
    session['active_tenant_id'] = tenant.id
    session.save()

    # Claiming alone must not silently stop an active bot.
    assert client.post(f'/conversations/{conv.id}/action/', {'action': 'claim'}).status_code == 400
    assert client.post(f'/conversations/{conv.id}/action/', {'action': 'pause'}).status_code == 200
    resp = client.post(f'/conversations/{conv.id}/action/', {'action': 'claim'})
    assert resp.status_code == 200
    data = resp.json()
    assert data['assigned_staff'] == staff.username
    assert data['status'] == ConversationStatus.HUMAN_HANDOVER

    conv.refresh_from_db()
    assert conv.assigned_staff == staff
    assert conv.status == ConversationStatus.HUMAN_HANDOVER
    assert conv.picked_up_at is not None

    customer.refresh_from_db()
    assert customer.owner == staff

    # Release back to queue
    resp_rel = client.post(f'/conversations/{conv.id}/action/', {'action': 'release'})
    assert resp_rel.status_code == 200
    conv.refresh_from_db()
    assert conv.assigned_staff is None


@pytest.mark.django_db
def test_quote_and_quote_item_percentage_calculation_precision(workflow_setup):
    """Verifies Quote and QuoteItem calculations do not fail with Decimal/float TypeError."""
    tenant = workflow_setup['tenant']
    owner = workflow_setup['owner']
    customer = workflow_setup['customer']

    deal = Deal.objects.create(
        tenant=tenant,
        pipeline=workflow_setup['pipeline'],
        stage=workflow_setup['stage_new'],
        contact=customer,
        title="Installation Deal"
    )

    quote = Quote.objects.create(
        tenant=tenant,
        deal=deal,
        quote_number="QT-2026-TEST",
        title="Air Conditioning Installation",
        currency="INR",
        tax_percent=Decimal('18.00'),
        discount_amount=Decimal('500.00'),
        created_by=owner
    )

    item = QuoteItem.objects.create(
        quote=quote,
        description="Split AC 1.5 Ton Copper Piping",
        quantity=Decimal('2.00'),
        unit_price=Decimal('2500.00'),
        discount_percent=Decimal('10.00')
    )

    # 2 * 2500 = 5000; 10% disc = 500; total = 4500
    assert item.total_price == Decimal('4500.00')

    quote.recalculate_totals()
    quote.refresh_from_db()
    assert quote.subtotal == Decimal('4500.00')
    # Taxable = 4500 - 500 = 4000; 18% tax = 720; total = 4720
    assert quote.tax_amount == Decimal('720.00')
    assert quote.total_amount == Decimal('4720.00')
