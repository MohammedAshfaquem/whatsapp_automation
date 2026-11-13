from unittest.mock import patch

import pytest

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import Customer, Conversation
from apps.chatbot.gemini_service import GeminiChatService
from apps.services.models import Service


pytestmark = pytest.mark.django_db


@pytest.fixture
def chat():
    customer = Customer.objects.create(phone_number='+919999111180', name='Ashfaque')
    service = Service.objects.create(name='AC repair', price_amount=500)
    conversation = Conversation.objects.create(customer=customer, service=service)
    return customer, conversation, service


def send(chat, text):
    return ConversationService.process_message(chat[0].phone_number, text)


def test_friend_booking_asks_for_recipient_and_does_not_rename_requester(chat):
    result = send(chat, 'I want to book another one service also but thats for my friend')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.data['booking_for_other'] is True
    assert session.step == BookingStep.NAME
    assert 'name' in result['reply'].lower()
    send(chat, 'John')
    session.refresh_from_db()
    chat[0].refresh_from_db()
    assert session.data['recipient_name'] == 'John'
    assert chat[0].name == 'Ashfaque'
    assert session.step == BookingStep.SERVICE  # Do not silently reuse the last repair service.


def test_ownership_correction_is_never_a_symptom(chat):
    send(chat, f'book_service_{chat[2].pk}')
    send(chat, 'Window ac issue')
    result = send(chat, 'Not mine my friend ac')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.data['booking_for_other'] is True
    assert session.data['ac_type'] == 'Window AC'
    assert not session.data.get('problem_description')
    assert session.step == BookingStep.NAME
    assert 'friend' in result['reply'].lower() or 'recipient' in result['reply'].lower()
    send(chat, 'John')
    result = send(chat, 'not cooling')
    session.refresh_from_db()
    assert session.step == BookingStep.ADDRESS
    assert 'recipient' in result['reply'].lower() or 'their' in result['reply'].lower()


@pytest.mark.parametrize('question', ['Who are u?', 'Who are you?', 'Are you a bot?'])
def test_identity_question_is_answered_without_advancing_booking(chat, question):
    send(chat, f'book_service_{chat[2].pk}')
    session = BookingSession.objects.get(conversation=chat[1])
    before = dict(session.data)
    result = send(chat, question)
    session.refresh_from_db()
    assert 'assistant' in result['reply'].lower()
    assert session.step == BookingStep.AC_DETAILS
    assert session.data == before


def test_contextual_llm_reply_does_not_become_an_address(chat):
    session = BookingSession.objects.create(conversation=chat[1], step=BookingStep.ADDRESS,
        data={'name':'Ashfaque', 'service_id':chat[2].pk, 'service_name':chat[2].name,
              'ac_type':'Window AC', 'problem_description':'Not cooling'})
    interpretation = {'kind': 'conversation', 'recipient': 'unspecified',
                      'reply': 'I’m helping arrange the visit. Please share the service address when you’re ready.'}
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=interpretation):
        result = send(chat, 'You are misunderstanding what I am saying')
    session.refresh_from_db()
    assert result['reply'] == interpretation['reply']
    assert 'service_address' not in session.data
    assert session.step == BookingStep.ADDRESS


def test_submitted_friend_booking_keeps_the_requester_as_owner(chat):
    send(chat, 'book AC repair for my friend')
    send(chat, 'John')
    send(chat, 'Window AC not cooling')
    send(chat, 'House 42, Main Road, 676306')
    review = send(chat, 'tomorrow at 3 pm')
    assert 'John' in review['reply'] and 'Ashfaque' in review['reply']
    result = send(chat, 'booking_submit')
    booking = Booking.objects.get(pk=result['booking_id'])
    assert booking.recipient_name == 'John'
    assert booking.customer == chat[0]
    chat[0].refresh_from_db()
    assert chat[0].name == 'Ashfaque'


@pytest.mark.parametrize('answer', ['His name is John', 'My name is John'])
def test_recipient_name_introduction_does_not_change_requester_profile(chat, answer):
    send(chat, 'book AC repair for my friend')
    send(chat, answer)
    session = BookingSession.objects.get(conversation=chat[1])
    chat[0].refresh_from_db()
    assert session.data['recipient_name'] == 'John'
    assert chat[0].name == 'Ashfaque'


def test_friend_review_cannot_submit_without_recipient_name(chat):
    session = BookingSession.objects.create(conversation=chat[1], step=BookingStep.REVIEW,
        data={'booking_for_other':True,'name':'Ashfaque','service_id':chat[2].pk,'service_name':chat[2].name,
              'ac_type':'Window AC','problem_description':'Not cooling','service_address':'House 42 Main Road',
              'preferred_date':'2026-11-03','preferred_time_slot':'3 pm'})
    result = send(chat, 'booking_submit')
    session.refresh_from_db()
    assert session.step == BookingStep.NAME
    assert not Booking.objects.exists()
    assert 'name' in result['reply'].lower()


def test_status_shows_both_own_and_friend_bookings(chat):
    own = Booking.objects.create(customer=chat[0], service=chat[2], service_address='Own House')
    friend = Booking.objects.create(customer=chat[0], service=chat[2], recipient_name='John', service_address='Friend House')
    result = send(chat, 'booking status')
    assert f'#{own.pk}' in result['reply']
    assert f'#{friend.pk}' in result['reply']
    assert 'John' in result['reply']


def test_negated_self_correction_preserves_friend_and_known_recipient(chat):
    send(chat, 'book AC repair for my friend')
    send(chat, 'John')
    send(chat, 'This is not for me, it is for my friend')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.data['booking_for_other'] is True
    assert session.data['recipient_name'] == 'John'
    assert session.step == BookingStep.AC_DETAILS


@pytest.mark.parametrize('message,expected', [
    ('This is not for me, it is for my friend', 'other'),
    ('not for myself', None),
    ('This is not for my friend, it is for me', 'self'),
])
def test_recipient_correction_respects_negation(message, expected):
    from apps.bookings.booking_service import BookingService
    assert BookingService.recipient_correction(message) == expected
