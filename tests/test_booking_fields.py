from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.models import Customer, Conversation
from apps.services.models import Service

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat():
    customer = Customer.objects.create(phone_number='+919999111181', name='Ashfaque')
    service = Service.objects.create(name='AC repair', price_amount=500)
    conversation = Conversation.objects.create(customer=customer, service=service)
    return customer, conversation, service


def send(chat, message, fields, recipient='unspecified', kind='answer', reply='', clear_fields=None):
    result = {'kind': kind, 'recipient': recipient, 'reply': reply, 'fields': fields,
              'clear_fields': clear_fields or []}
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=result):
        return ConversationService.process_message(chat[0].phone_number, message)


def test_initial_friend_request_keeps_all_explicit_details(chat):
    response = send(chat, "Book AC repair for my friend John, Window AC isn't cooling, tomorrow evening",
        {'service_name': 'AC repair', 'recipient_name': 'John', 'ac_type': 'Window AC',
         'problem_description': "isn't cooling", 'preferred_date': 'tomorrow', 'preferred_time_slot': 'evening'},
        recipient='other')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.ADDRESS
    assert session.data['recipient_name'] == 'John'
    assert session.data['ac_type'] == 'Window AC'
    assert session.data['preferred_date'] == (timezone.localdate() + timedelta(days=1)).isoformat()
    assert 'address' in response['reply'].lower()
    chat[0].refresh_from_db()
    assert chat[0].name == 'Ashfaque'
    assert not Booking.objects.exists()


def complete_draft(chat):
    return BookingSession.objects.create(conversation=chat[1], step=BookingStep.REVIEW, data={
        'name': 'Ashfaque', 'service_id': chat[2].pk, 'service_name': 'AC repair',
        'ac_type': 'Window AC', 'problem_description': 'not cooling',
        'service_address': 'House 42 Main Road Kerala 676306',
        'preferred_date': (timezone.localdate() + timedelta(days=1)).isoformat(),
        'preferred_time_slot': 'evening'})


def test_free_text_correction_at_review_revalidates_and_never_submits(chat):
    session = complete_draft(chat)
    response = send(chat, 'Actually Split AC, and the day after tomorrow instead',
                    {'ac_type': 'Split AC', 'preferred_date': 'day after tomorrow'})
    session.refresh_from_db()
    assert session.data['ac_type'] == 'Split AC'
    assert session.data['preferred_date'] == (timezone.localdate() + timedelta(days=2)).isoformat()
    assert 'preferred_time_slot' not in session.data
    assert session.step == BookingStep.SCHEDULE
    assert session.data['problem_description'] == 'not cooling'
    assert response['booking_id'] is None


def test_conversation_with_fields_answers_question_and_asks_only_missing_field(chat):
    BookingSession.objects.create(conversation=chat[1], step=BookingStep.AC_DETAILS,
        data={'name': 'Ashfaque', 'service_id': chat[2].pk, 'service_name': 'AC repair'})
    response = send(chat, 'Window AC, not cooling. Can you explain inspection?',
        {'ac_type': 'Window AC', 'problem_description': 'not cooling'},
        kind='conversation', reply='A technician inspects it before quoting the repair.')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.ADDRESS
    assert 'inspects' in response['reply']
    assert 'address' in response['reply'].lower()


def test_invalid_fields_do_not_replace_valid_draft_or_fill_from_raw_message(chat):
    session = complete_draft(chat)
    response = send(chat, 'Please change that', {'service_name': 'Nonexistent service',
        'service_address': 'Who are you?', 'preferred_date': '2001-01-01', 'ac_type': 'Invalid AC'})
    session.refresh_from_db()
    assert session.data['service_name'] == 'AC repair'
    assert session.data['service_address'] == 'House 42 Main Road Kerala 676306'
    assert session.data['ac_type'] == 'Window AC'
    assert session.step == BookingStep.REVIEW
    assert response['booking_id'] is None


def test_explicit_clear_returns_to_missing_field(chat):
    session = complete_draft(chat)
    send(chat, "I don't know the address yet, remove that one", {}, clear_fields=['service_address'])
    session.refresh_from_db()
    assert session.step == BookingStep.ADDRESS
    assert 'service_address' not in session.data
    assert session.data['ac_type'] == 'Window AC'


@pytest.mark.parametrize('message,fields', [
    ('Window ac thanukkunnilla, naale vaikunneram', {'ac_type': 'Window AC', 'problem_description': 'not cooling',
        'preferred_date': 'tomorrow', 'preferred_time_slot': 'evening'}),
    ('विंडो एसी ठंडा नहीं कर रहा, कल शाम', {'ac_type': 'Window AC', 'problem_description': 'ठंडा नहीं कर रहा',
        'preferred_date': 'tomorrow', 'preferred_time_slot': 'evening'}),
    ('windw ac not coooling tomorow evning', {'ac_type': 'Window AC', 'problem_description': 'not cooling',
        'preferred_date': 'tomorrow', 'preferred_time_slot': 'evening'}),
])
def test_interpreted_language_and_typo_dialogue_keeps_schedule_while_asking_address(chat, message, fields):
    BookingSession.objects.create(conversation=chat[1], step=BookingStep.AC_DETAILS,
        data={'name': 'Ashfaque', 'service_id': chat[2].pk, 'service_name': 'AC repair'})
    send(chat, message, fields)
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.ADDRESS
    assert session.data['preferred_time_slot'] == 'evening'


def test_full_combined_booking_keeps_details_through_question_and_submission(chat):
    send(chat, 'Book AC repair for my friend John, Window AC not cooling, tomorrow evening',
         {'service_name': 'AC repair', 'recipient_name': 'John', 'ac_type': 'Window AC',
          'problem_description': 'not cooling', 'preferred_date': 'tomorrow', 'preferred_time_slot': 'evening'},
         recipient='other')
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
        question = ConversationService.process_message(chat[0].phone_number, 'Who are you?')
        assert 'assistant' in question['reply'].lower()
        address = ConversationService.process_message(chat[0].phone_number, 'House 42 Main Road Kerala 676306')
        assert address['booking_progress']['step'] == BookingStep.REVIEW
        assert not Booking.objects.exists()
        result = ConversationService.process_message(chat[0].phone_number, 'booking_submit')
        replay = ConversationService.process_message(chat[0].phone_number, 'booking_submit')
    assert result['booking_id']
    booking = Booking.objects.get()
    assert booking.recipient_name == 'John'
    assert booking.problem_description == 'not cooling'
    assert booking.status == 'PENDING'
    assert not replay.get('booking_id')


def test_date_and_time_are_order_independent(chat):
    complete_draft(chat)
    send(chat, 'Day after tomorrow at 3 pm',
         {'preferred_time_slot': '3 pm', 'preferred_date': 'day after tomorrow'})
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.REVIEW
    assert session.data['preferred_time_slot'] == '3 pm'


def test_known_price_question_keeps_database_price_even_if_model_invents_one(chat):
    complete_draft(chat)
    response = send(chat, 'What is the price?', {}, kind='conversation', reply='The price is 999999.')
    assert '999999' not in response['reply']
    assert '500' in response['reply']


def test_first_time_customer_can_finish_friend_booking_without_renaming_requester(chat):
    chat[0].name = ''
    chat[0].save()
    send(chat, 'Book AC repair for my friend John, Window AC not cooling, tomorrow evening',
         {'service_name': 'AC repair', 'recipient_name': 'John', 'ac_type': 'Window AC',
          'problem_description': 'not cooling', 'preferred_date': 'tomorrow', 'preferred_time_slot': 'evening'},
         recipient='other')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.ADDRESS
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
        ConversationService.process_message(chat[0].phone_number, 'House 42 Main Road Kerala 676306')
        result = ConversationService.process_message(chat[0].phone_number, 'booking_submit')
    assert result['booking_id']
    chat[0].refresh_from_db()
    assert chat[0].name == ''
    assert Booking.objects.get().recipient_name == 'John'


def test_empty_extracted_name_cannot_crash_or_rename_customer(chat):
    chat[0].name = ''
    chat[0].save()
    BookingSession.objects.create(conversation=chat[1], step=BookingStep.NAME, data={})
    result = send(chat, "I'm not ready to give my name", {'name': '   '})
    assert result['booking_progress']['step'] == BookingStep.NAME
    chat[0].refresh_from_db()
    assert chat[0].name == ''


@pytest.mark.parametrize('step', [BookingStep.ADDRESS, BookingStep.AC_DETAILS, BookingStep.NAME])
def test_provider_outage_does_not_save_unpunctuated_clarification(chat, step):
    session = BookingSession.objects.create(conversation=chat[1], step=step, data={
        'name': 'Ashfaque', 'service_id': chat[2].pk, 'service_name': 'AC repair'})
    before = dict(session.data)
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
        result = ConversationService.process_message(chat[0].phone_number, 'can you explain this')
    session.refresh_from_db()
    assert session.data == before
    assert session.step == step
    assert result['reply']
