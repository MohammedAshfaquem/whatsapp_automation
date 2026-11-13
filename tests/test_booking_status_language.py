"""Buttons and natural status questions must read the same customer-owned records."""
from unittest.mock import patch

import pytest

from apps.bookings.models import Booking, BookingSession
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.intent_service import IntentService, IntentType
from apps.chatbot.models import Customer, Conversation
from apps.services.models import Service


pytestmark = pytest.mark.django_db


@pytest.fixture
def customer_booking():
    customer = Customer.objects.create(phone_number='+919999111160', name='Ashfaque')
    service = Service.objects.create(name='AC repair', price_amount=500)
    booking = Booking.objects.create(customer=customer, service=service,
        service_address='Maliyekkal House, VK Padi, 676306', preferred_time_slot='evening')
    return customer, booking


@pytest.mark.parametrize('question', [
    'what is the current status my last booming',
    'what is the current status of my last booking',
    'What is my booking current status?',
    'Any update on my appointment?',
    'Can I get an update about my last booking?',
    'status of my latest boking',
    'what is the status of my bokking?',
    'Check Status',
])
def test_natural_status_questions_use_the_same_lookup_as_the_button(customer_booking, question):
    customer, booking = customer_booking
    with patch.object(GeminiChatService, 'generate_reply') as ai:
        button = ConversationService.process_message(customer.phone_number, 'booking status')
        typed = ConversationService.process_message(customer.phone_number, question)
    assert typed['reply'] == button['reply']
    assert f'#{booking.pk}' in typed['reply']
    assert 'Pending Confirmation' in typed['reply']
    assert typed['handover_required'] is False
    assert not BookingSession.objects.exists()
    assert Booking.objects.count() == 1
    ai.assert_not_called()


def test_typo_status_question_does_not_trigger_unknown_escalation(customer_booking):
    customer, booking = customer_booking
    conversation = Conversation.objects.create(customer=customer, unresolved_count=1)
    result = ConversationService.process_message(customer.phone_number, 'what is the current status my last booming')
    conversation.refresh_from_db()
    assert result['handover_required'] is False
    assert f'#{booking.pk}' in result['reply']
    assert conversation.unresolved_count == 0


def test_status_response_reads_current_status_and_only_this_customers_bookings(customer_booking):
    customer, booking = customer_booking
    booking.status = 'CONFIRMED'
    booking.save(update_fields=['status'])
    other = Customer.objects.create(phone_number='+919999111161')
    private = Booking.objects.create(customer=other, service_address='PRIVATE ADDRESS', status='REJECTED')
    result = ConversationService.process_message(customer.phone_number, 'Any update on my last booking?')
    assert f'#{booking.pk}' in result['reply']
    assert 'Confirmed' in result['reply']
    assert f'#{private.pk}' not in result['reply']
    assert 'PRIVATE' not in result['reply']


@pytest.mark.parametrize('message', [
    'I want to book an appointment',
    'My AC repair is not cooling',
    'What is the status of my cooking?',
    'The area is booming, do you provide AC service?',
])
def test_typo_tolerance_is_limited_to_booking_status_context(message):
    assert IntentService.detect_intent(message)[0] != IntentType.BOOKING_STATUS


@pytest.mark.parametrize('message', [
    'I want to book an appointment and get confirmation',
    'Please create a booking and send me confirmation',
    'I want to book an appointment with email updates',
])
def test_new_booking_requests_are_not_mistaken_for_status_questions(message):
    assert IntentService.detect_intent(message)[0] == IntentType.BOOKING_START
