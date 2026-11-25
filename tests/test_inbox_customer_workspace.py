import json
from datetime import timedelta
import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from apps.tenants.models import Tenant, TenantMembership
from apps.chatbot.models import (
    Customer, Conversation, ConversationStatus, Message, MessageDirection,
    ChannelChoice, SenderType
)
from apps.crm.models import (
    Deal, DealStage, Activity, ActivityStatus, ActivityType, ActivityPriority,
    Pipeline, ContactNote, LeadScore
)
from apps.whatsapp.models import WhatsAppDelivery

User = get_user_model()


@pytest.fixture
def inbox_workspace_setup(db):
    tenant = Tenant.objects.create(name="Inbox Workspace Tenant", slug="inbox-wf-tenant", is_active=True)
    other_tenant = Tenant.objects.create(name="Other Tenant", slug="other-tenant", is_active=True)

    owner = User.objects.create_user(username="inbox_owner", password="password123", email="owner@inbox.com", is_staff=True)
    staff = User.objects.create_user(username="inbox_staff", password="password123", email="staff@inbox.com", is_staff=True)
    other_staff = User.objects.create_user(username="other_staff", password="password123", email="other@tenant.com", is_staff=True)

    TenantMembership.objects.create(tenant=tenant, user=owner, role='OWNER', is_active=True)
    TenantMembership.objects.create(tenant=tenant, user=staff, role='STAFF', is_active=True)
    TenantMembership.objects.create(tenant=other_tenant, user=other_staff, role='STAFF', is_active=True)

    customer = Customer.objects.create(
        tenant=tenant,
        name="Priya Sharma",
        phone_number="+919876543210",
        email="priya@example.com",
        owner=staff,
        lifecycle_status="PROSPECT"
    )

    score = LeadScore.objects.create(
        tenant=tenant,
        contact=customer,
        score=82,
        priority="HIGH",
        score_breakdown={'recency': 40, 'budget': 42}
    )

    conv = Conversation.objects.create(
        tenant=tenant,
        customer=customer,
        channel=ChannelChoice.SIMULATED,
        status=ConversationStatus.HUMAN_HANDOVER,
        handoff_summary="Customer inquired about WhatsApp enterprise licensing and SLA.",
        last_message_at=timezone.now()
    )

    Message.objects.create(
        conversation=conv,
        sender_type=SenderType.CUSTOMER,
        direction=MessageDirection.INBOUND,
        message_text="Can we discuss custom onboarding?"
    )

    pipeline = Pipeline.objects.create(tenant=tenant, name="Primary Pipeline", is_default=True)
    stage = DealStage.objects.create(pipeline=pipeline, name="Qualified", order=1)
    deal = Deal.objects.create(
        tenant=tenant,
        pipeline=pipeline,
        title="Enterprise Annual Subscription",
        contact=customer,
        stage=stage,
        amount=150000,
        currency="INR"
    )

    activity = Activity.objects.create(
        tenant=tenant,
        contact=customer,
        title="Follow up on SLA agreement",
        activity_type=ActivityType.FOLLOW_UP,
        priority=ActivityPriority.HIGH,
        due_date=timezone.now() + timedelta(days=2),
        assigned_to=staff
    )

    return {
        'tenant': tenant,
        'other_tenant': other_tenant,
        'owner': owner,
        'staff': staff,
        'other_staff': other_staff,
        'customer': customer,
        'conversation': conv,
        'deal': deal,
        'activity': activity,
        'score': score
    }


@pytest.mark.django_db
def test_conversations_list_api_exposes_customer_id_and_handoff_summary(client, inbox_workspace_setup):
    data = inbox_workspace_setup
    client.force_login(data['staff'])

    session = client.session
    session['active_tenant_id'] = data['tenant'].id
    session.save()

    response = client.get('/api/inbox/conversations/')
    assert response.status_code == 200
    res_data = response.json()
    assert 'conversations' in res_data
    assert len(res_data['conversations']) >= 1

    conv_item = res_data['conversations'][0]
    assert conv_item['id'] == data['conversation'].id
    assert conv_item.get('customer_id') == data['customer'].id
    assert conv_item.get('handoff_summary') == "Customer inquired about WhatsApp enterprise licensing and SLA."


@pytest.mark.django_db
def test_conversation_messages_api_exposes_customer_id(client, inbox_workspace_setup):
    data = inbox_workspace_setup
    client.force_login(data['staff'])

    session = client.session
    session['active_tenant_id'] = data['tenant'].id
    session.save()

    response = client.get(f"/conversations/{data['conversation'].id}/messages/")
    assert response.status_code == 200
    res_data = response.json()
    assert res_data['customer_id'] == data['customer'].id
    assert res_data['handoff_summary'] == "Customer inquired about WhatsApp enterprise licensing and SLA."


@pytest.mark.django_db
def test_contact_detail_api_exposes_owner_lead_score_and_rich_activities(client, inbox_workspace_setup):
    data = inbox_workspace_setup
    client.force_login(data['staff'])

    session = client.session
    session['active_tenant_id'] = data['tenant'].id
    session.save()

    response = client.get(f"/api/crm/contacts/{data['customer'].id}/")
    assert response.status_code == 200
    res_data = response.json()

    # Contact details
    contact = res_data['contact']
    assert contact['id'] == data['customer'].id
    assert contact['name'] == "Priya Sharma"
    assert contact['owner'] is not None
    assert contact['owner']['username'] == "inbox_staff"
    assert contact['lead_score'] == 82
    assert contact['lifecycle_stage'] == "PROSPECT"

    # Deals
    assert len(res_data['deals']) == 1
    assert res_data['deals'][0]['title'] == "Enterprise Annual Subscription"
    assert res_data['deals'][0]['status'] == "OPEN"

    # Activities
    assert len(res_data['activities']) == 1
    act = res_data['activities'][0]
    assert act['title'] == "Follow up on SLA agreement"
    assert act['priority'] == "HIGH"
    assert act['activity_type'] == "FOLLOW_UP"
    assert 'is_overdue' in act


@pytest.mark.django_db
def test_internal_note_creation_no_external_send(client, inbox_workspace_setup):
    data = inbox_workspace_setup
    client.force_login(data['staff'])

    session = client.session
    session['active_tenant_id'] = data['tenant'].id
    session.save()

    initial_delivery_count = WhatsAppDelivery.objects.count()

    response = client.post(
        f"/api/crm/contacts/{data['customer'].id}/notes/",
        data=json.dumps({'content': 'Client requested quote with 99.9% uptime SLA.'}),
        content_type='application/json'
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data['status'] == 'created'
    assert res_data['note']['content'] == 'Client requested quote with 99.9% uptime SLA.'

    # Verify no WhatsAppDelivery was created
    assert WhatsAppDelivery.objects.count() == initial_delivery_count

    # Check note appears in contact detail
    detail_res = client.get(f"/api/crm/contacts/{data['customer'].id}/")
    notes = detail_res.json()['notes']
    assert any(n['content'] == 'Client requested quote with 99.9% uptime SLA.' for n in notes)


@pytest.mark.django_db
def test_create_and_complete_follow_up_task(client, inbox_workspace_setup):
    data = inbox_workspace_setup
    client.force_login(data['staff'])

    session = client.session
    session['active_tenant_id'] = data['tenant'].id
    session.save()

    # Create task
    create_res = client.post(
        '/api/crm/activities/',
        data=json.dumps({
            'contact_id': data['customer'].id,
            'title': 'Call customer regarding proposal',
            'activity_type': 'CALL',
            'priority': 'HIGH',
            'due_date': (timezone.now() + timedelta(days=1)).isoformat(),
            'notes': 'Discuss timeline and pilot user count.'
        }),
        content_type='application/json'
    )
    assert create_res.status_code == 201
    act_id = create_res.json()['activity']['id']

    # Complete the task
    complete_res = client.post(f"/api/crm/activities/{act_id}/complete/")
    assert complete_res.status_code == 200

    # Verify activity is completed
    act = Activity.objects.get(id=act_id)
    assert act.status == ActivityStatus.COMPLETED
    assert act.completed_at is not None


@pytest.mark.django_db
def test_foreign_tenant_isolation_denies_access(client, inbox_workspace_setup):
    data = inbox_workspace_setup
    # Login as other_staff who belongs to other_tenant
    client.force_login(data['other_staff'])

    session = client.session
    session['active_tenant_id'] = data['other_tenant'].id
    session.save()

    # Accessing customer of another tenant must be 404
    detail_res = client.get(f"/api/crm/contacts/{data['customer'].id}/")
    assert detail_res.status_code == 404

    # Adding note to customer of another tenant must be 404
    note_res = client.post(
        f"/api/crm/contacts/{data['customer'].id}/notes/",
        data=json.dumps({'content': 'Malicious cross-tenant note'}),
        content_type='application/json'
    )
    assert note_res.status_code == 404

    # Completing activity of another tenant must be 404
    complete_res = client.post(f"/api/crm/activities/{data['activity'].id}/complete/")
    assert complete_res.status_code == 404
