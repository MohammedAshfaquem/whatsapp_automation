import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import signing
from django.utils import timezone

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import Customer, Conversation, ChannelChoice
from apps.services.models import Service
from apps.whatsapp.webhook_service import WebhookService
from apps.whatsapp.whatsapp_client import WhatsAppClient

pytestmark = pytest.mark.django_db


@pytest.fixture
def chat(settings):
    settings.WHATSAPP_BOOKING_FLOW_ID = '123456'
    customer = Customer.objects.create(phone_number='+919999111187', name='Ashfaque')
    service = Service.objects.create(name='AC repair', price_amount=500)
    conversation = Conversation.objects.create(customer=customer, service=service, channel=ChannelChoice.WHATSAPP)
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.ADDRESS,
        data={'name': customer.name, 'service_id': service.pk, 'service_name': service.name,
              'ac_type': 'Window AC', 'problem_description': 'not cooling'})
    return customer, conversation, session


def send(chat, message, **kwargs):
    return ConversationService.process_message(chat[0].phone_number, message, channel=ChannelChoice.WHATSAPP, **kwargs)


def offer(chat):
    return send(chat, 'booking_resume')['flow']


def address(flow):
    return {'flow_token': flow['flow_token'], 'house': 'House 42', 'street': 'Main Road',
            'locality': 'Tirur', 'pin_code': '676306', 'landmark': 'Near school',
            'preferred_date': (timezone.localdate() + timedelta(days=1)).isoformat(), 'time_slot': 'evening'}


def payload(chat, data, message_id='wamid.form1'):
    return {'entry': [{'changes': [{'value': {'messages': [{
        'id': message_id, 'from': chat[0].phone_number.lstrip('+'), 'type': 'interactive',
        'interactive': {'type': 'nfm_reply', 'nfm_reply': {'name': 'flow', 'response_json': json.dumps(data)}}
    }]}}]}]}


def test_whatsapp_offers_address_form_and_schedule_picker(chat):
    first = offer(chat)
    assert first['screen'] == 'ADDRESS'
    assert first['flow_id'] == '123456'
    with patch('apps.whatsapp.events.dispatch', return_value=True):
        assert WebhookService.process_incoming_payload(payload(chat, address(first)))['processed'] == 1
    chat[2].refresh_from_db()
    assert chat[2].step == BookingStep.REVIEW
    assert '676306' in chat[2].data['service_address']
    with patch('apps.whatsapp.events.dispatch', return_value=True):
        WebhookService.process_incoming_payload(payload(chat, address(first)))
    chat[2].refresh_from_db()
    assert chat[2].step == BookingStep.REVIEW
    assert not Booking.objects.exists()
    result = send(chat, 'booking_submit')
    assert result['booking_id']
    assert Booking.objects.get().status == 'PENDING'


def test_disabled_flow_and_website_channel_keep_typed_booking(chat, settings):
    settings.WHATSAPP_BOOKING_FLOW_ID = ''
    assert not send(chat, 'booking_resume').get('flow')
    settings.WHATSAPP_BOOKING_FLOW_ID = '123456'
    chat[1].channel = ChannelChoice.SIMULATED
    chat[1].save()
    result = ConversationService.process_message(chat[0].phone_number, 'booking_resume')
    assert not result.get('flow')


@pytest.mark.parametrize('changes', [{'pin_code': '123'}, {'house': ''}, {'street': ['bad']},
                                     {'landmark': 'x' * 121}])
def test_invalid_address_never_advances_or_mutates_draft(chat, changes):
    from apps.whatsapp.booking_flows import apply_response
    data = address(offer(chat))
    data.update(changes)
    before = dict(chat[2].data)
    answer = apply_response(chat[1], data)
    chat[2].refresh_from_db()
    assert chat[2].step == BookingStep.ADDRESS
    assert chat[2].data == before
    assert 'address' in answer.lower() or 'pin' in answer.lower()


def test_stale_cross_customer_and_expired_tokens_are_rejected(chat):
    from apps.whatsapp.booking_flows import apply_response
    data = address(offer(chat))
    other = Customer.objects.create(phone_number='+919999111188')
    other_conversation = Conversation.objects.create(customer=other, channel=ChannelChoice.WHATSAPP)
    assert 'latest form' in apply_response(other_conversation, data).lower()
    chat[2].data['problem_description'] = 'leaking water'
    chat[2].save()
    assert 'latest form' in apply_response(chat[1], data).lower()
    fresh = address(offer(chat))
    with patch('django.core.signing.time.time', return_value=timezone.now().timestamp() + 7201):
        assert 'latest form' in apply_response(chat[1], fresh).lower()
    assert not Booking.objects.exists()


def test_old_form_cannot_overwrite_typed_address_or_cancelled_draft(chat):
    from apps.whatsapp.booking_flows import apply_response
    data = address(offer(chat))
    send(chat, 'House 99 Station Road Tirur 676306')
    assert 'latest form' in apply_response(chat[1], data).lower()
    send(chat, 'cancel')
    assert 'latest form' in apply_response(chat[1], data).lower()


def test_form_responses_never_call_gemini_and_handover_stays_quiet(chat):
    first = offer(chat)
    with patch('apps.chatbot.gemini_service.GeminiChatService.generate_reply') as ai, \
            patch('apps.whatsapp.events.dispatch', return_value=True):
        WebhookService.process_incoming_payload(payload(chat, address(first)))
    ai.assert_not_called()
    chat[1].status = 'HUMAN_HANDOVER'
    chat[1].save()
    with patch('apps.whatsapp.events.dispatch') as dispatch:
        WebhookService.process_incoming_payload(payload(chat, {'flow_token': first['flow_token']}, 'wamid.handoverform'))
    dispatch.assert_not_called()
    chat[2].refresh_from_db()
    assert chat[2].step == BookingStep.REVIEW


def test_outgoing_flow_uses_native_meta_payload():
    with patch.object(WhatsAppClient, '_send_payload', return_value=(True, 'wamid.flow')) as send_payload:
        WhatsAppClient.send_flow_message('+919999111187', 'Enter address', '123456', 'signed-token', 'ADDRESS', {'house': ''})
    interactive = send_payload.call_args.args[1]['interactive']
    assert interactive['type'] == 'flow'
    assert interactive['action']['parameters']['flow_message_version'] == '3'
    assert interactive['action']['parameters']['flow_action_payload']['screen'] == 'ADDRESS'


def test_status_lookup_does_not_offer_an_unfinished_booking_form(chat):
    Booking.objects.create(customer=chat[0], service_address='House Main Road')
    result = send(chat, 'booking status')
    assert not result.get('flow')


@pytest.mark.parametrize('changes', [
    {'preferred_date': '2001-01-01', 'time_slot': 'evening'},
    {'preferred_date': 'tomorrow', 'time_slot': 'morning'},
    {'preferred_date': '2026-99-99', 'time_slot': 'afternoon'},
    {'time_slot': 'confirmed'}, {'time_slot': 12},
])
def test_invalid_schedule_preserves_draft(chat, changes):
    from apps.whatsapp.booking_flows import apply_response
    chat[2].step = BookingStep.SCHEDULE
    chat[2].data['service_address'] = 'House 42 Main Road Tirur 676306'
    chat[2].save()
    form = offer(chat)
    before = dict(chat[2].data)
    data = {'flow_token': form['flow_token'],
            'preferred_date': (timezone.localdate() + timedelta(days=1)).isoformat(), 'time_slot': 'evening'}
    data.update(changes)
    assert 'future visit' in apply_response(chat[1], data)
    chat[2].refresh_from_db()
    assert chat[2].data == before
    assert chat[2].step == BookingStep.SCHEDULE


def test_form_targets_its_original_conversation_when_customer_has_multiple(chat):
    form = offer(chat)
    other = Conversation.objects.create(customer=chat[0], channel=ChannelChoice.WHATSAPP)
    with patch('apps.whatsapp.events.dispatch', return_value=True):
        WebhookService.process_incoming_payload(payload(chat, address(form)))
    chat[2].refresh_from_db()
    assert chat[2].step == BookingStep.REVIEW
    assert not BookingSession.objects.filter(conversation=other).exists()


def test_schema_screens_accept_server_defaults(chat):
    from pathlib import Path
    from django.conf import settings
    schema = json.loads((Path(settings.BASE_DIR) / 'apps/whatsapp/flows/booking_details.json').read_text())
    for step in (BookingStep.ADDRESS, BookingStep.SCHEDULE):
        chat[2].step = step
        chat[2].save()
        flow = offer(chat)
        screen = next(item for item in schema['screens'] if item['id'] == step)
        assert screen.get('terminal', False) == (step == BookingStep.SCHEDULE)
        assert set(flow['data']) == set(screen['data'])
    components = schema['screens'][1]['layout']['children'][0]['children']
    assert any(item['type'] == 'DatePicker' for item in components)


@pytest.mark.parametrize('raw', ['not JSON', '[]', '{}', '{"flow_token":123}'])
def test_malformed_response_is_rejected_without_creating_booking(chat, raw):
    event = payload(chat, {})
    event['entry'][0]['changes'][0]['value']['messages'][0]['interactive']['nfm_reply']['response_json'] = raw
    with patch('apps.whatsapp.events.dispatch', return_value=True):
        result = WebhookService.process_incoming_payload(event)
    assert result['failures'] == 0
    chat[2].refresh_from_db()
    assert chat[2].step == BookingStep.ADDRESS
    assert not Booking.objects.exists()


def test_booking_change_confirmation_is_not_replaced_by_an_address_form(chat):
    booking = Booking.objects.create(customer=chat[0], service_address='House 42 Main Road')
    result = send(chat, f'cancel_booking_{booking.pk}')
    assert not result.get('flow')
    assert any(option['id'] == f'confirm_cancel_{booking.pk}' for option in result['options'])


def test_typed_address_correction_invalidates_old_structured_defaults(chat):
    from apps.whatsapp.booking_flows import apply_response
    apply_response(chat[1], address(offer(chat)))
    send(chat, 'booking_edit')
    send(chat, 'booking_edit_address')
    send(chat, 'House 99 New Road Tirur 676306')
    send(chat, 'booking_edit')
    send(chat, 'booking_edit_address')
    form = offer(chat)
    assert form['data']['house'] == ''
    chat[2].refresh_from_db()
    assert chat[2].data['service_address'] == 'House 99 New Road Tirur 676306'


def test_combined_form_validates_schedule_before_saving_address(chat):
    from apps.whatsapp.booking_flows import apply_response
    data = address(offer(chat))
    data['preferred_date'] = '2001-01-01'
    assert 'future visit' in apply_response(chat[1], data)
    chat[2].refresh_from_db()
    assert 'service_address' not in chat[2].data
    assert chat[2].step == BookingStep.ADDRESS
