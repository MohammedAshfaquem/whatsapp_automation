import pytest
from django.contrib.auth.models import User

from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import Customer, Conversation, ConversationStatus, Message, SenderType

pytestmark = pytest.mark.django_db


@pytest.fixture
def support():
    customer = Customer.objects.create(phone_number='+919999111182')
    conversation = Conversation.objects.create(customer=customer, status=ConversationStatus.HUMAN_HANDOVER)
    first = User.objects.create_user('first', is_staff=True)
    second = User.objects.create_user('second', is_staff=True)
    return conversation, first, second


def action(client, conversation, name, **kwargs):
    return client.post(f'/conversations/{conversation.pk}/action/', {'action': name, **kwargs})


def test_claim_conflicts_and_owner_is_visible_only_to_staff(client, support):
    conversation, first, second = support
    client.force_login(first)
    assert action(client, conversation, 'claim').status_code == 200
    conversation.refresh_from_db()
    assert conversation.assigned_staff == first
    picked_up_at = conversation.picked_up_at
    assert picked_up_at is not None
    assert action(client, conversation, 'claim').status_code == 200
    conversation.refresh_from_db()
    assert conversation.picked_up_at == picked_up_at
    detail = client.get(f'/conversations/{conversation.pk}/messages/').json()
    assert detail['assigned_staff']['id'] == first.pk
    client.force_login(second)
    for name in ('claim', 'release', 'reply', 'resume'):
        assert action(client, conversation, name, text='Hello').status_code == 409
    assert not Message.objects.filter(sender_type=SenderType.HUMAN).exists()
    user = User.objects.create_user('customer')
    conversation.customer.user = user
    conversation.customer.save()
    client.force_login(user)
    detail = client.get(f'/conversations/{conversation.pk}/messages/').json()
    assert 'assigned_staff' not in detail
    assert action(client, conversation, 'claim').status_code == 403


def test_staff_reply_claims_unassigned_chat_and_resume_clears_owner(client, support):
    conversation, first, _ = support
    client.force_login(first)
    assert action(client, conversation, 'reply', text='How can I help?').status_code == 200
    conversation.refresh_from_db()
    assert conversation.assigned_staff == first
    assert conversation.picked_up_at
    assert action(client, conversation, 'resume').status_code == 200
    conversation.refresh_from_db()
    assert conversation.assigned_staff is None
    assert conversation.picked_up_at is None
    assert conversation.status == ConversationStatus.BOT_ACTIVE


def test_release_requeues_handover_and_customer_resume_clears_assignment(client, support):
    conversation, first, _ = support
    client.force_login(first)
    assert action(client, conversation, 'claim').status_code == 200
    assert action(client, conversation, 'release').status_code == 200
    conversation.refresh_from_db()
    assert conversation.assigned_staff is None
    assert conversation.status == ConversationStatus.HUMAN_HANDOVER
    action(client, conversation, 'claim')
    ConversationService.process_message(conversation.customer.phone_number, 'resume bot')
    conversation.refresh_from_db()
    assert conversation.assigned_staff is None
    assert conversation.picked_up_at is None


def test_claiming_active_bot_is_not_a_silent_handover(client, support):
    conversation, first, _ = support
    conversation.status = ConversationStatus.BOT_ACTIVE
    conversation.save()
    client.force_login(first)
    assert action(client, conversation, 'claim').status_code == 400
