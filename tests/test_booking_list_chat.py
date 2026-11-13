from unittest.mock import patch

import pytest

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.intent_service import IntentService, IntentType
from apps.chatbot.models import Conversation, Customer, Message
from apps.services.models import Service

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat():
    customer = Customer.objects.create(phone_number='+919999111183', name='Ashfaque')
    service = Service.objects.create(name='AC gas filling', price_amount=500)
    conversation = Conversation.objects.create(customer=customer, service=service)
    bookings = [Booking.objects.create(customer=customer, service=service, service_address='House 42 Main Road')
                for _ in range(4)]
    return customer, conversation, bookings


@pytest.mark.parametrize('message', ['booking list please', 'i want all my bookings',
    'show my bookings', 'my bookings', 'appointment history', 'list my appointments'])
def test_list_requests_show_customer_history_without_starting_booking(chat, message):
    customer, conversation, bookings = chat
    with patch.object(GeminiChatService, 'generate_reply') as ai:
        result = ConversationService.process_message(customer.phone_number, message)
    assert IntentService.detect_intent(message)[0] == IntentType.BOOKING_STATUS
    assert all(f'#{booking.pk}' in result['reply'] for booking in bookings)
    assert not BookingSession.objects.filter(conversation=conversation).exists()
    assert 'what type of ac' not in result['reply'].lower()
    ai.assert_not_called()


def test_reported_sequence_preserves_draft_without_appending_unrelated_question(chat):
    customer, conversation, bookings = chat
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.AC_DETAILS,
        data={'name': customer.name, 'service_id': conversation.service_id, 'service_name': 'AC gas filling'})
    original = dict(session.data)
    with patch.object(GeminiChatService, 'interpret_booking_turn') as interpret:
        for message in ('booking list please', 'i want all my bookings', 'what is the status of my last booking?'):
            result = ConversationService.process_message(customer.phone_number, message)
            assert f'#{bookings[-1].pk}' in result['reply']
            assert 'what type of ac' not in result['reply'].lower()
            assert not any(option['id'].startswith('service_') for option in result['options'])
    session.refresh_from_db()
    assert session.data == original
    assert session.step == BookingStep.AC_DETAILS
    interpret.assert_not_called()


def test_last_booking_means_only_the_most_recent_booking(chat):
    customer, _, bookings = chat
    result = ConversationService.process_message(customer.phone_number, 'what is the status of my last booking?')
    assert f'#{bookings[-1].pk}' in result['reply']
    assert all(f'#{booking.pk}' not in result['reply'] for booking in bookings[:-1])


def test_history_pages_never_expose_another_customers_bookings(chat):
    customer, _, bookings = chat
    bookings.extend(Booking.objects.create(customer=customer, service_address='House 42 Main Road') for _ in range(3))
    other = Customer.objects.create(phone_number='+919999111184')
    private = Booking.objects.create(customer=other, service_address='PRIVATE ADDRESS')
    first = ConversationService.process_message(customer.phone_number, 'all my bookings')
    next_page = next(option for option in first['options'] if option['title'] == 'Older bookings')
    second = ConversationService.process_message(customer.phone_number, next_page['id'])
    combined = first['reply'] + second['reply']
    assert all(f'#{booking.pk}' in combined for booking in bookings)
    assert f'#{private.pk}' not in combined
    assert 'PRIVATE' not in combined
    assert not BookingSession.objects.exists()


@pytest.mark.parametrize('message', ['book another AC service', 'create a booking for my friend',
    'I want to book all my ACs', 'cancel my booking', 'reschedule my appointment'])
def test_creation_and_change_requests_are_not_history(message):
    assert IntentService.detect_intent(message)[0] != IntentType.BOOKING_STATUS


def test_history_lookup_does_not_generate_a_memory_summary_when_one_is_due(chat):
    customer, conversation, _ = chat
    Message.objects.bulk_create([Message(conversation=conversation, direction='INBOUND', sender_type='CUSTOMER',
        message_text=f'Earlier message {index}') for index in range(10)])
    with patch.object(GeminiChatService, 'generate_reply') as generate:
        result = ConversationService.process_message(customer.phone_number, 'all my bookings')
    assert 'Booking #' in result['reply']
    generate.assert_not_called()


def test_empty_history_does_not_create_a_draft(chat):
    customer, conversation, _ = chat
    Booking.objects.filter(customer=customer).delete()
    result = ConversationService.process_message(customer.phone_number, 'booking list please')
    assert "don't have any bookings" in result['reply']
    assert not BookingSession.objects.filter(conversation=conversation).exists()
