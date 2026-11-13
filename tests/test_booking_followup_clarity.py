from unittest.mock import patch

import pytest

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.models import Customer, Conversation
from apps.services.models import Service

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat():
    customer = Customer.objects.create(name='Ashfaque', phone_number='+919999111185')
    service = Service.objects.create(name='AC repair', price_amount=500)
    conversation = Conversation.objects.create(customer=customer, service=service)
    booking = Booking.objects.create(customer=customer, service=service, service_address='House 42 Main Road')
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.AC_DETAILS,
        data={'name': 'Ashfaque', 'service_id': service.pk, 'service_name': service.name})
    return customer, conversation, booking, session


@pytest.mark.parametrize('question', ['when it will approve?', 'when will it be approved',
    'how long will confirmation take?', 'will your team contact me?'])
def test_approval_followup_answers_pending_booking_without_touching_draft(chat, question):
    customer, _, booking, session = chat
    before = dict(session.data)
    ConversationService.process_message(customer.phone_number, 'status of my last booking')
    with patch.object(GeminiChatService, 'generate_reply') as ai:
        result = ConversationService.process_message(customer.phone_number, question)
    assert f'#{booking.pk}' in result['reply']
    assert 'team' in result['reply'].lower()
    assert 'confirmation' in result['reply'].lower()
    assert 'what type of ac' not in result['reply'].lower()
    session.refresh_from_db()
    assert session.data == before
    assert session.step == BookingStep.AC_DETAILS
    assert not result['handover_required']
    ai.assert_not_called()


def test_followup_reads_updated_status_and_keeps_context_for_another_question(chat):
    customer, _, booking, _ = chat
    ConversationService.process_message(customer.phone_number, 'status of my last booking')
    first = ConversationService.process_message(customer.phone_number, 'when it will approve?')
    assert 'awaiting' in first['reply'].lower()
    booking.status = 'CONFIRMED'
    booking.save()
    result = ConversationService.process_message(customer.phone_number, 'is it approved yet?')
    assert 'confirmed' in result['reply'].lower()
    assert 'awaiting' not in result['reply'].lower()


def test_typo_requests_confirmation_instead_of_becoming_a_symptom(chat):
    customer, _, _, session = chat
    result = ConversationService.process_message(customer.phone_number, 'widow')
    assert 'did you mean' in result['reply'].lower()
    assert 'Window' in result['reply']
    session.refresh_from_db()
    assert 'problem_description' not in session.data
    assert 'ac_type' not in session.data
    result = ConversationService.process_message(customer.phone_number, 'yes')
    session.refresh_from_db()
    assert session.data['ac_type'] == 'Window AC'
    assert 'issue' in result['reply'].lower()


def test_unknown_type_asks_for_clarification_and_rejection_does_not_save_guess(chat):
    customer, _, _, session = chat
    result = ConversationService.process_message(customer.phone_number, 'xyz')
    assert 'understand' in result['reply'].lower() or 'clarify' in result['reply'].lower()
    session.refresh_from_db()
    assert 'problem_description' not in session.data
    ConversationService.process_message(customer.phone_number, 'widow')
    result = ConversationService.process_message(customer.phone_number, 'no')
    session.refresh_from_db()
    assert 'ac_type' not in session.data
    assert 'pending_ac_type' not in session.data
    assert 'understand' in result['reply'].lower() or 'clarify' in result['reply'].lower()


def test_ac_type_clarification_does_not_block_cancel_or_consume_symptoms(chat):
    customer, _, _, session = chat
    ConversationService.process_message(customer.phone_number, 'leaking')
    session.refresh_from_db()
    assert session.data['problem_description'] == 'leaking'
    result = ConversationService.process_message(customer.phone_number, 'cancel')
    assert 'cancelled' in result['reply'].lower()


def test_multi_booking_followup_asks_for_reference_and_rechecks_owner(chat):
    customer, _, booking, session = chat
    another = Booking.objects.create(customer=customer, service_address='Other House Main Road')
    stranger = Customer.objects.create(phone_number='+919999111186')
    private = Booking.objects.create(customer=stranger, service_address='Private House Main Road')
    ConversationService.process_message(customer.phone_number, 'all my bookings')
    question = ConversationService.process_message(customer.phone_number, 'when will it be approved?')
    assert 'Which booking' in question['reply']
    response = ConversationService.process_message(customer.phone_number, f'#{booking.pk}')
    assert f'#{booking.pk}' in response['reply']
    assert 'awaiting confirmation' in response['reply']
    assert f'#{another.pk}' not in response['reply']
    assert f'#{private.pk}' not in response['reply']
    session.refresh_from_db()
    assert 'ac_type' not in session.data


def test_unrelated_reply_clears_booking_followup_context(chat):
    customer, _, _, session = chat
    ConversationService.process_message(customer.phone_number, 'status of my last booking')
    ConversationService.process_message(customer.phone_number, 'Window')
    session.refresh_from_db()
    assert session.data['ac_type'] == 'Window AC'
    latest = session.conversation.messages.filter(direction='OUTBOUND').last()
    assert latest.response_data['booking_context'] is None
