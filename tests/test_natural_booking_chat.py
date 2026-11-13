"""Conversation examples approved by the user, tested without external AI calls."""
from datetime import datetime, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.utils import timezone

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import Conversation, Customer, Message
from apps.services.models import Service, PriceType
from apps.whatsapp.models import WhatsAppDelivery
from apps.whatsapp.webhook_service import WebhookService


pytestmark = pytest.mark.django_db


@pytest.fixture
def chat(monkeypatch):
    now = datetime(2026, 11, 2, 12, 34, tzinfo=ZoneInfo('Asia/Kolkata'))
    monkeypatch.setattr(timezone, 'now', lambda: now)
    service = Service.objects.create(name='AC repair', price_type=PriceType.INSPECTION_REQUIRED,
                                    estimated_duration='1-3 hours')
    customer = Customer.objects.create(phone_number='+919999111140', name='Ashfaque')
    conversation = Conversation.objects.create(customer=customer, service=service)
    return customer, conversation, service


def send(chat, message):
    return ConversationService.process_message(chat[0].phone_number, message)


def schedule_session(chat):
    return BookingSession.objects.create(conversation=chat[1], step=BookingStep.SCHEDULE, data={
        'name': 'Ashfaque', 'service_id': chat[2].pk, 'service_name': chat[2].name,
        'ac_type': 'Window AC', 'problem_description': 'Not cooling',
        'service_address': 'Maliyekkal House, VK Padi, 676306',
    })


@pytest.mark.parametrize('action', ['choose date', 'Another date'])
def test_another_date_clears_today_and_waits_for_a_new_day_before_review(chat, monkeypatch, action):
    now = datetime(2026, 11, 4, 1, 1, tzinfo=ZoneInfo('Asia/Kolkata'))
    monkeypatch.setattr(timezone, 'now', lambda: now)
    session = schedule_session(chat)
    send(chat, 'today')
    session.refresh_from_db()
    assert session.data['preferred_date'] == '2026-11-04'
    send(chat, action)
    session.refresh_from_db()
    assert 'preferred_date' not in session.data
    assert 'preferred_time_slot' not in session.data
    result = send(chat, 'morning')
    session.refresh_from_db()
    assert session.step == BookingStep.SCHEDULE
    assert 'preferred_date' not in session.data
    assert session.data['preferred_time_slot'] == 'morning'
    assert 'review' not in result['reply'].lower()
    assert not Booking.objects.exists()
    result = send(chat, '2026-11-05')
    session.refresh_from_db()
    assert session.step == BookingStep.REVIEW
    assert session.data['preferred_date'] == '2026-11-05'
    assert result['booking_id'] is None


def test_another_date_is_a_control_and_clears_old_time_too(chat):
    session = schedule_session(chat)
    session.data.update(preferred_date='2026-11-03', preferred_time_slot='evening')
    session.save()
    with patch('apps.chatbot.gemini_service.GeminiChatService.interpret_booking_turn', return_value=None) as interpret:
        send(chat, 'choose date')
    interpret.assert_not_called()
    session.refresh_from_db()
    assert 'preferred_date' not in session.data
    assert 'preferred_time_slot' not in session.data


def test_returning_casual_greeting_is_not_a_service_price_dump(chat):
    send(chat, 'hello')
    result = send(chat, 'hey bro')
    assert 'Ashfaque' in result['reply']
    assert 'welcome back' in result['reply'].lower()
    assert 'how can' in result['reply'].lower()
    assert 'Pricing:' not in result['reply']


def test_casual_greeting_does_not_fill_an_active_booking(chat):
    session = schedule_session(chat)
    result = send(chat, 'hey bro')
    assert 'unfinished' in result['reply'].lower()
    session.refresh_from_db()
    assert session.step == BookingStep.SCHEDULE
    assert 'preferred_date' not in session.data


@pytest.mark.parametrize('message', ['check_price', 'What is the price for AC repair?'])
def test_inspection_price_is_explained_without_inventing_a_charge(chat, message):
    message = f'check_price_{chat[2].pk}' if message == 'check_price' else message
    result = send(chat, message)
    assert 'after' in result['reply'].lower() and 'inspect' in result['reply'].lower()
    assert 'price for AC repair is Inspection required' not in result['reply']
    assert '₹' not in result['reply']
    assert 'free' not in result['reply'].lower()


def test_window_ac_alone_requires_the_problem_before_address(chat):
    result = send(chat, f'book_service_{chat[2].pk}')
    assert 'type' in result['reply'].lower()
    assert not result['options']
    result = send(chat, 'i have window ac')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.AC_DETAILS
    assert session.data['ac_type'] == 'Window AC'
    assert not session.data.get('problem_description')
    assert 'issue' in result['reply'].lower()
    result = send(chat, 'not cooling')
    session.refresh_from_db()
    assert session.step == BookingStep.ADDRESS
    assert session.data['problem_description'] == 'not cooling'
    assert not result['options']


@pytest.mark.parametrize('message', ['Window AC, not cooling', 'My window AC is not cooling?'])
def test_both_ac_details_in_one_message_are_kept(chat, message):
    send(chat, f'book_service_{chat[2].pk}')
    send(chat, message)
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.ADDRESS
    assert session.data['ac_type'] == 'Window AC'
    assert 'not cooling' in session.data['problem_description']


@pytest.mark.parametrize('message', ['could u come today?', 'can you come tomorrow?', 'today', 'tomorrow'])
def test_date_only_requests_keep_context_and_ask_only_for_time(chat, message):
    session = schedule_session(chat)
    result = send(chat, message)
    session.refresh_from_db()
    expected_date = timezone.localdate() + timedelta(days=int('tomorrow' in message))
    assert session.data['preferred_date'] == expected_date.isoformat()
    assert session.step == BookingStep.SCHEDULE
    assert 'what time' in result['reply'].lower()
    assert 'only help' not in result['reply'].lower()
    assert not Booking.objects.exists()
    assert session.data['service_address'] == 'Maliyekkal House, VK Padi, 676306'
    result = send(chat, '3 pm')
    session.refresh_from_db()
    assert session.step == BookingStep.REVIEW
    assert 'booking_submit' in {option['id'] for option in result['options']}
    assert not Booking.objects.exists()


def test_past_time_does_not_erase_the_preferred_day(chat):
    session = schedule_session(chat)
    send(chat, 'today')
    result = send(chat, '10 am')
    session.refresh_from_db()
    assert session.step == BookingStep.SCHEDULE
    assert session.data['preferred_date'] == '2026-11-02'
    assert 'time' in result['reply'].lower()
    assert 'preferred_time_slot' not in session.data


def test_business_side_question_does_not_replace_the_selected_day(chat):
    session = schedule_session(chat)
    send(chat, 'tomorrow')
    result = send(chat, 'What are your working hours today?')
    session.refresh_from_db()
    assert session.data['preferred_date'] == '2026-11-03'
    assert 'what time' in result['reply'].lower()
    assert session.step == BookingStep.SCHEDULE


def test_complete_approved_conversation_stays_pending_until_submission(chat):
    send(chat, f'book_service_{chat[2].pk}')
    send(chat, 'i have window ac')
    send(chat, 'not cooling')
    send(chat, 'House: Maliyekkal House\nStreet: VK Padi\nPIN code: 676306')
    result = send(chat, 'could u come today?')
    assert 'what time' in result['reply'].lower()
    review = send(chat, '3 pm')
    assert not Booking.objects.exists()
    assert 'after' in review['reply'].lower() and 'inspection' in review['reply'].lower()
    submitted = send(chat, 'booking_submit')
    booking = Booking.objects.get(pk=submitted['booking_id'])
    assert booking.ac_type == 'Window AC'
    assert booking.problem_description == 'not cooling'
    assert booking.preferred_date.isoformat() == '2026-11-02'
    assert booking.status == 'PENDING'


def test_replayed_whatsapp_action_sends_one_reply(chat):
    payload = {'entry': [{'changes': [{'value': {'messages': [{
        'id': 'wamid.natural-price', 'from': chat[0].phone_number.lstrip('+'),
        'type': 'interactive', 'interactive': {'type': 'button_reply',
            'button_reply': {'id': f'check_price_{chat[2].pk}', 'title': 'Check Price'}},
    }]}}]}]}
    with patch('apps.whatsapp.whatsapp_client.WhatsAppClient.send_interactive_options', return_value=(True, 'out.once')) as deliver:
        WebhookService.process_incoming_payload(payload)
        WebhookService.process_incoming_payload(payload)
    assert deliver.call_count == 1
    assert WhatsAppDelivery.objects.count() == 1
    assert Message.objects.filter(external_message_id='wamid.natural-price').count() == 1


@pytest.mark.parametrize('message', ['Window', 'window AC Daikin', 'i have window ac at home',
                                     'I have a 1.5 ton split AC', 'LG 2 ton 5 star Window AC'])
def test_type_only_variations_do_not_become_symptoms(chat, message):
    send(chat, f'book_service_{chat[2].pk}')
    result = send(chat, message)
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.AC_DETAILS
    assert not session.data.get('problem_description')
    assert 'issue' in result['reply'].lower()


def test_issue_then_type_works_without_repeating_the_issue(chat):
    send(chat, f'book_service_{chat[2].pk}')
    send(chat, 'not cooling')
    result = send(chat, 'Window AC')
    session = BookingSession.objects.get(conversation=chat[1])
    assert session.step == BookingStep.ADDRESS
    assert session.data['problem_description'] == 'not cooling'
    assert 'address' in result['reply'].lower()


def test_time_then_date_works_and_past_presets_are_hidden(chat):
    session = schedule_session(chat)
    result = send(chat, 'today')
    assert 'morning' not in {option['id'] for option in result['options']}
    assert 'afternoon' in {option['id'] for option in result['options']}
    session.data = {key: value for key, value in session.data.items() if key != 'preferred_date'}
    session.save()
    result = send(chat, '3 pm')
    assert 'which date' in result['reply'].lower()
    result = send(chat, 'tomorrow')
    session.refresh_from_db()
    assert session.step == BookingStep.REVIEW
    assert session.data['preferred_date'] == '2026-11-03'


def test_location_side_question_containing_today_does_not_change_schedule(chat):
    session = schedule_session(chat)
    send(chat, 'tomorrow')
    send(chat, 'Where is your shop today?')
    session.refresh_from_db()
    assert session.data['preferred_date'] == '2026-11-03'


def test_expired_partial_day_asks_for_a_new_day(chat, monkeypatch):
    session = schedule_session(chat)
    send(chat, 'today')
    tomorrow = datetime(2026, 11, 3, 12, 34, tzinfo=ZoneInfo('Asia/Kolkata'))
    monkeypatch.setattr(timezone, 'now', lambda: tomorrow)
    result = send(chat, '3 pm')
    session.refresh_from_db()
    assert session.step == BookingStep.SCHEDULE
    assert not session.data.get('preferred_date')
    assert 'which date' in result['reply'].lower()


def test_typed_team_request_still_works_without_help_buttons(chat):
    send(chat, f'book_service_{chat[2].pk}')
    result = send(chat, 'talk to team')
    assert result['handover_required'] is True


def test_editing_ac_details_does_not_erase_other_booking_fields(chat):
    session = schedule_session(chat)
    send(chat, 'tomorrow at 3 pm')
    send(chat, 'booking_edit')
    send(chat, 'booking_edit_ac_details')
    send(chat, 'Split AC')
    session.refresh_from_db()
    assert session.step == BookingStep.REVIEW
    assert session.data['ac_type'] == 'Split AC'
    assert session.data['problem_description'] == 'Not cooling'
    assert session.data['service_address'] == 'Maliyekkal House, VK Padi, 676306'


def test_expired_review_returns_to_date_choices(chat, monkeypatch):
    session = schedule_session(chat)
    send(chat, 'today at 3 pm')
    tomorrow = datetime(2026, 11, 3, 12, 34, tzinfo=ZoneInfo('Asia/Kolkata'))
    monkeypatch.setattr(timezone, 'now', lambda: tomorrow)
    result = send(chat, 'booking_submit')
    session.refresh_from_db()
    assert session.step == BookingStep.SCHEDULE
    assert not session.data.get('preferred_date')
    assert not session.data.get('preferred_time_slot')
    assert {'today', 'tomorrow'} <= {option['id'] for option in result['options']}
    assert not Booking.objects.exists()
