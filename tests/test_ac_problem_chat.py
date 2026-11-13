"""Reported AC symptoms must not become unrelated-topic or price-only replies."""
from unittest.mock import patch

import pytest

from apps.bookings.models import BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.intent_service import IntentService, IntentType
from apps.chatbot.models import Customer, Conversation
from apps.services.models import Service, PriceType


pytestmark = pytest.mark.django_db
REPORTED_MESSAGE = 'i have a problem on my ac.didnt get any cool whenthe temparture in 16'


@pytest.fixture
def repair():
    return Service.objects.create(name='AC repair', price_type=PriceType.INSPECTION_REQUIRED)


@pytest.mark.parametrize('message', [
    REPORTED_MESSAGE,
    "My AC doesn't get cold even at 16",
    'The air conditioner is not giving cool air',
    'AC is blowing hot air',
    'my ac is not cooling',
])
def test_cooling_complaints_offer_actual_repair_without_ai(repair, message):
    with patch.object(GeminiChatService, 'generate_reply') as ai:
        result = ConversationService.process_message('+919999111150', message)
    assert 'cooling' in result['reply'].lower()
    assert 'inspect' in result['reply'].lower()
    assert repair.name in result['reply']
    assert 'only help' not in result['reply'].lower()
    assert 'gas leak' not in result['reply'].lower()
    assert 'gas filling' not in result['reply'].lower()
    assert f'book_service_{repair.pk}' in {option['id'] for option in result['options']}
    assert result['handover_required'] is False
    ai.assert_not_called()


def test_clarified_symptom_does_not_trigger_unknown_message_escalation(repair):
    customer = Customer.objects.create(phone_number='+919999111151', name='Ashfaque')
    conversation = Conversation.objects.create(customer=customer, unresolved_count=1)
    result = ConversationService.process_message(customer.phone_number, REPORTED_MESSAGE)
    conversation.refresh_from_db()
    assert result['handover_required'] is False
    assert conversation.unresolved_count == 0


def test_missing_repair_service_offers_team_without_inventing_a_service():
    result = ConversationService.process_message('+919999111152', REPORTED_MESSAGE)
    assert 'only help' not in result['reply'].lower()
    assert 'cooling' in result['reply'].lower()
    assert 'team' in result['reply'].lower()
    assert all(not option['id'].startswith('book_service_') for option in result['options'])


def test_generic_ac_problem_asks_for_symptoms(repair):
    result = ConversationService.process_message('+919999111153', 'I have an issue with my AC')
    assert 'issue' in result['reply'].lower() or 'problem' in result['reply'].lower()
    assert '?' in result['reply']
    assert 'only help' not in result['reply'].lower()


def test_complaint_during_address_collection_does_not_replace_the_address(repair):
    customer = Customer.objects.create(phone_number='+919999111154', name='Ashfaque')
    conversation = Conversation.objects.create(customer=customer, service=repair)
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.ADDRESS,
        data={'name': 'Ashfaque', 'service_id': repair.pk, 'service_name': repair.name,
              'ac_type': 'Window AC', 'problem_description': 'Not cooling'})
    result = ConversationService.process_message(customer.phone_number, REPORTED_MESSAGE)
    session.refresh_from_db()
    assert session.step == BookingStep.ADDRESS
    assert 'service_address' not in session.data
    assert 'only help' not in result['reply'].lower()


def test_explicit_cooling_price_question_still_returns_the_configured_quote(repair):
    result = ConversationService.process_message('+919999111155', 'My AC is not cooling, what is the repair price?')
    assert 'after' in result['reply'].lower() and 'inspect' in result['reply'].lower()
    assert repair.name in result['reply']


@pytest.mark.parametrize('price_word', ['vila', 'ethraya', 'വില', 'कीमत'])
def test_multilingual_price_question_keeps_priority_over_symptom_reply(repair, price_word):
    intent, service = IntentService.detect_intent(f'My AC is not cooling {price_word}')
    assert intent == IntentType.SERVICE_PRICE
    assert service == repair
