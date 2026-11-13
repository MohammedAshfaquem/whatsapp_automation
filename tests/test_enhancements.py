from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.utils import timezone

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.intent_service import IntentService
from apps.chatbot.models import Customer, Conversation, ChannelChoice
from apps.services.models import Service
from apps.whatsapp.webhook_service import WebhookService
from apps.whatsapp.models import WhatsAppWebhookLog

pytestmark = pytest.mark.django_db


@pytest.fixture
def repair():
    return Service.objects.create(name='AC repair', price_amount=500, is_active=True)


def test_missing_business_policies_are_not_invented():
    for question, forbidden in [('warranty', '30-day'), ('payment', 'Credit/Debit'), ('working hours', '9:00 AM')]:
        result = ConversationService.process_message('+919999111101', question)
        assert forbidden not in result['reply']
        assert 'confirm' in result['reply'].lower()


def test_private_notes_never_enter_customer_reply_or_prompt(repair):
    customer = Customer.objects.create(phone_number='+919999111102')
    Booking.objects.create(customer=customer, service=repair, service_address='House 42', owner_notes='PRIVATE billing dispute')
    result = ConversationService.process_message(customer.phone_number, 'booking status')
    assert 'PRIVATE' not in result['reply']
    assert 'PRIVATE' not in ConversationService.get_customer_account_summary(customer)


def test_new_service_overrides_previous_selection(repair):
    gas = Service.objects.create(name='AC gas filling', price_amount=1500, is_active=True)
    phone = '+919999111103'
    ConversationService.process_message(phone, f'service_{gas.id}')
    result = ConversationService.process_message(phone, f'book_service_{repair.id}')
    session = BookingSession.objects.get(conversation_id=result['conversation_id'])
    assert session.data['service_id'] == repair.id


def test_water_leak_is_not_gas_filling(repair):
    Service.objects.create(name='AC gas filling', price_amount=1500, is_active=True)
    assert IntentService.find_matching_service('water leakage from ac') == repair


def test_side_question_does_not_become_address(repair):
    customer = Customer.objects.create(phone_number='+919999111104', name='Afi')
    conv = Conversation.objects.create(customer=customer, service=repair)
    BookingSession.objects.create(conversation=conv, step=BookingStep.ADDRESS, data={'name': 'Afi', 'service_id': repair.id})
    ConversationService.process_message(customer.phone_number, 'What is the price?')
    session = BookingSession.objects.get(conversation=conv)
    assert session.step == BookingStep.ADDRESS
    assert 'service_address' not in session.data


def test_schedule_requires_date_and_review_before_submission(repair):
    customer = Customer.objects.create(phone_number='+919999111105', name='Afi')
    conv = Conversation.objects.create(customer=customer, service=repair)
    BookingSession.objects.create(conversation=conv, step=BookingStep.SCHEDULE, data={
        'name': 'Afi', 'service_id': repair.id, 'service_name': repair.name,
        'service_address': 'House 42, Main Road', 'ac_type': 'Split AC', 'problem_description': 'Not cooling',
    })
    bad = ConversationService.process_message(customer.phone_number, 'yesterday at 10 AM')
    assert bad['booking_id'] is None
    assert not Booking.objects.exists()
    review = ConversationService.process_message(customer.phone_number, 'Tomorrow at 11 AM')
    assert review['booking_id'] is None
    assert any(o['id'] == 'booking_submit' for o in review['options'])
    result = ConversationService.process_message(customer.phone_number, 'booking_submit')
    booking = Booking.objects.get(pk=result['booking_id'])
    assert booking.preferred_date == timezone.localdate() + timedelta(days=1)
    assert f'#{booking.id}' in result['reply']


def test_greeting_has_actionable_choices():
    result = ConversationService.process_message('+919999111106', 'Hello')
    assert {o['id'] for o in result['options']} >= {'view_services', 'book', 'talk to agent'}


def test_handover_acknowledges_once():
    ConversationService.process_message('+919999111107', 'talk to agent')
    result = ConversationService.process_message('+919999111107', 'one more detail')
    assert result['handover_required']
    assert not result['reply']


def test_customer_cannot_manage_bookings(client, repair):
    user = User.objects.create_user('customer', password='test-password')
    customer = Customer.objects.create(user=user, phone_number='+919999111108')
    booking = Booking.objects.create(customer=customer, service_address='House 42')
    client.force_login(user)
    assert client.post(f'/bookings/{booking.id}/action/', {'action': 'confirm'}).status_code == 403
    assert client.get('/dashboard/').status_code == 200


def test_customer_cannot_read_other_transcripts(client):
    user = User.objects.create_user('viewer')
    Customer.objects.create(user=user, phone_number='+919999111109')
    other = Customer.objects.create(phone_number='+919999111110')
    conv = Conversation.objects.create(customer=other)
    client.force_login(user)
    assert client.get(f'/conversations/{conv.id}/messages/').status_code == 403


def test_public_simulator_requires_staff(client):
    response = client.post('/api/chat/test/', {'phone_number': '+919999111111', 'message': 'booking status'})
    assert response.status_code in (401, 403)


def payload(message_id='wamid.enhancement', msg_type='text'):
    return {'entry': [{'changes': [{'value': {'messages': [{
        'id': message_id, 'from': '919999111112', 'type': msg_type, 'text': {'body': 'hello'}
    }]}}]}]}


def test_duplicate_webhook_does_not_resend():
    with patch('apps.whatsapp.webhook_service.WhatsAppClient.send_interactive_options', return_value=(True, 'out.1')) as send:
        WebhookService.process_incoming_payload(payload())
        WebhookService.process_incoming_payload(payload())
    assert send.call_count == 1


def test_failed_send_is_not_marked_successful():
    with patch('apps.whatsapp.webhook_service.WhatsAppClient.send_interactive_options', return_value=(False, 'Timeout')):
        WebhookService.process_incoming_payload(payload())
    log = WhatsAppWebhookLog.objects.first()
    assert not log.is_processed
    assert log.error_message


def test_missing_signature_rejected_in_production(settings):
    settings.DEBUG = False
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={'app_secret': '', 'enabled': True}):
        assert not WebhookService.verify_signature(b'{}', None)


def test_attachment_is_not_fabricated_service_interest():
    with patch('apps.whatsapp.webhook_service.WhatsAppClient.send_interactive_options', return_value=(True, 'out.2')) as send:
        WebhookService.process_incoming_payload(payload(msg_type='audio'))
    assert 'voice' in send.call_args.kwargs['body_text'].lower()


def test_portal_retry_returns_same_booking_response(client, repair):
    user = User.objects.create_user('portal-customer')
    Customer.objects.create(user=user, phone_number='+919999111113', name='Afi')
    client.force_login(user)
    body = {'message_text': 'book AC repair', 'request_id': 'f9936ba6-15b8-4fb7-a0b9-765de217f430'}
    first = client.post('/chat/send/', body, content_type='application/json').json()
    second = client.post('/chat/send/', body, content_type='application/json').json()
    assert first == second
    assert BookingSession.objects.count() == 1


def test_staff_can_resume_handover(client):
    user = User.objects.create_user('operator', is_staff=True)
    customer = Customer.objects.create(phone_number='+919999111114')
    conv = Conversation.objects.create(customer=customer, status='HUMAN_HANDOVER')
    client.force_login(user)
    response = client.post(f'/conversations/{conv.pk}/action/', {'action': 'resume'})
    assert response.status_code == 200
    conv.refresh_from_db()
    assert conv.status == 'BOT_ACTIVE'


def test_confirmed_booking_notifies_once_without_internal_notes(repair):
    from apps.bookings.notifications import change_booking_status
    from apps.whatsapp.models import WhatsAppDelivery
    from apps.chatbot.models import Message
    customer = Customer.objects.create(phone_number='+919999111115')
    conv = Conversation.objects.create(customer=customer, channel=ChannelChoice.WHATSAPP)
    Message.objects.create(conversation=conv, direction='INBOUND', sender_type='CUSTOMER', message_text='book')
    booking = Booking.objects.create(customer=customer, conversation=conv, service=repair, service_address='House 42', owner_notes='PRIVATE')
    change_booking_status(booking, 'CONFIRMED')
    change_booking_status(booking, 'CONFIRMED')
    assert WhatsAppDelivery.objects.count() == 1
    assert 'PRIVATE' not in str(WhatsAppDelivery.objects.get().payload)


def test_symptom_description_and_weekday_schedule_are_booking_answers(repair):
    customer = Customer.objects.create(name='Afi', phone_number='+919999111116')
    conv = Conversation.objects.create(customer=customer, service=repair)
    BookingSession.objects.create(conversation=conv, step=BookingStep.AC_DETAILS,
        data={'name': 'Afi', 'service_id': repair.pk, 'service_name': repair.name})
    ConversationService.process_message(customer.phone_number, 'Split AC not cooling')
    session = BookingSession.objects.get(conversation=conv)
    assert session.step == BookingStep.ADDRESS
    ConversationService.process_message(customer.phone_number, 'House 42 on Main Road')
    ConversationService.process_message(customer.phone_number, 'Sunday morning')
    session.refresh_from_db()
    assert session.step == BookingStep.REVIEW


def test_explicit_service_change_during_active_booking(repair):
    gas = Service.objects.create(name='AC gas filling', price_amount=1500)
    customer = Customer.objects.create(name='Afi', phone_number='+919999111117')
    ConversationService.process_message(customer.phone_number, f'book_service_{gas.pk}')
    ConversationService.process_message(customer.phone_number, f'book_service_{repair.pk}')
    session = BookingSession.objects.get(conversation__customer=customer)
    assert session.data['service_id'] == repair.pk
    assert session.step == BookingStep.AC_DETAILS


def test_staff_cannot_reset_existing_login_by_registering_customer(client):
    operator = User.objects.create_user('operator', is_staff=True)
    existing = User.objects.create_superuser('+919999111118', password='original-pass')
    client.force_login(operator)
    client.post('/customers/create/', {'name': 'Attempt', 'phone_number': existing.username,
        'create_portal_login': 'on', 'portal_password': 'replacement-pass'})
    existing.refresh_from_db()
    assert existing.check_password('original-pass')
    assert not Customer.objects.filter(user=existing).exists()


def test_submit_revalidates_time_after_review(repair):
    from datetime import datetime
    from apps.bookings.booking_service import BookingService
    customer = Customer.objects.create(name='Afi', phone_number='+919999111119')
    conv = Conversation.objects.create(customer=customer, service=repair)
    BookingSession.objects.create(conversation=conv, step=BookingStep.REVIEW, data={
        'name': 'Afi', 'service_id': repair.pk, 'service_name': repair.name,
        'service_address': 'House 42 Main Road', 'preferred_date': timezone.localdate().isoformat(),
        'preferred_time_slot': 'Today at 11 AM', 'problem_description': 'not cooling',
    })
    after = timezone.make_aware(datetime.combine(timezone.localdate(), datetime.strptime('12:00', '%H:%M').time()))
    with patch('apps.bookings.guided_booking.timezone.localtime', return_value=after):
        result = BookingService.process_booking_step(conv, 'booking_submit')
    assert result[1] is None
    assert not Booking.objects.exists()


def test_customer_can_refresh_own_handover_state_and_staff_reply(client):
    from apps.chatbot.models import Message
    user = User.objects.create_user('support-customer')
    customer = Customer.objects.create(user=user, phone_number='+919999111120')
    conv = Conversation.objects.create(customer=customer, status='HUMAN_HANDOVER')
    Message.objects.create(conversation=conv, direction='OUTBOUND', sender_type='HUMAN', message_text='Our team is checking your request.')
    client.force_login(user)
    data = client.get(f'/conversations/{conv.pk}/messages/').json()
    assert data['handover_required'] is True
    assert data['messages'][0]['text'] == 'Our team is checking your request.'
    assert 'booking_progress' in data


@pytest.mark.parametrize('step', [BookingStep.NAME, BookingStep.SERVICE, BookingStep.AC_DETAILS,
    BookingStep.ADDRESS, BookingStep.SCHEDULE, BookingStep.REVIEW, BookingStep.EDIT])
def test_greeting_does_not_fill_or_reject_an_unfinished_booking(step, repair):
    customer = Customer.objects.create(name='Afi', phone_number='+919999111121')
    conv = Conversation.objects.create(customer=customer, service=repair)
    data = {'name': 'Afi', 'service_id': repair.pk, 'service_name': repair.name}
    session = BookingSession.objects.create(conversation=conv, step=step, data=data)
    response = ConversationService.process_message(customer.phone_number, 'Hi')
    assert 'hello' in response['reply'].lower()
    assert 'unfinished' in response['reply'].lower()
    assert 'incomplete' not in response['reply'].lower()
    assert {option['id'] for option in response['options']} == {'booking_resume', 'booking_start_fresh', 'talk to agent'}
    session.refresh_from_db()
    customer.refresh_from_db()
    assert session.step == step
    assert session.data == data
    assert customer.name == 'Afi'
    assert not Booking.objects.exists()


def test_customer_can_resume_or_discard_draft_after_greeting(repair):
    customer = Customer.objects.create(name='Afi', phone_number='+919999111122')
    conv = Conversation.objects.create(customer=customer, service=repair)
    session = BookingSession.objects.create(conversation=conv, step=BookingStep.ADDRESS,
        data={'name':'Afi','service_id':repair.pk,'service_name':repair.name})
    ConversationService.process_message(customer.phone_number, 'Hello!')
    resumed = ConversationService.process_message(customer.phone_number, 'booking_resume')
    assert 'complete service address' in resumed['reply'].lower()
    session.refresh_from_db()
    assert session.step == BookingStep.ADDRESS
    fresh = ConversationService.process_message(customer.phone_number, 'booking_start_fresh')
    session.refresh_from_db()
    conv.refresh_from_db()
    assert session.step == BookingStep.CANCELLED
    assert conv.service is None
    assert 'how can we help' in fresh['reply'].lower()
    assert not Booking.objects.exists()


def test_older_whatsapp_message_does_not_reply_after_newer_event():
    from apps.whatsapp.models import WhatsAppDelivery
    newer = payload(message_id='wamid.newer')
    newer_message = newer['entry'][0]['changes'][0]['value']['messages'][0]
    newer_message['timestamp'] = '1793354312'
    older = payload(message_id='wamid.delayed')
    older['entry'][0]['changes'][0]['value']['messages'][0]['timestamp'] = '1793354298'
    with patch('apps.whatsapp.webhook_service.WhatsAppClient.send_interactive_options', return_value=(True, 'out.new')) as send:
        WebhookService.process_incoming_payload(newer)
        result = WebhookService.process_incoming_payload(older)
    assert result['processed'] == 1
    assert send.call_count == 1
    assert WhatsAppDelivery.objects.count() == 1
    assert WhatsAppWebhookLog.objects.get(whatsapp_message_id='wamid.delayed').is_processed


def test_late_greeting_cannot_modify_booking_state(repair):
    customer = Customer.objects.create(name='Afi', phone_number='+919999111123')
    conv = Conversation.objects.create(customer=customer, channel=ChannelChoice.WHATSAPP, service=repair)
    session = BookingSession.objects.create(conversation=conv, step=BookingStep.ADDRESS,
        data={'name':'Afi','service_id':repair.pk,'service_name':repair.name})
    from datetime import datetime, timezone as dt_timezone
    newer = datetime.fromtimestamp(1793354312, dt_timezone.utc)
    older = datetime.fromtimestamp(1793354298, dt_timezone.utc)
    ConversationService.process_message(customer.phone_number, 'booking_start_fresh', channel=ChannelChoice.WHATSAPP,
        external_message_id='wamid.fresh', external_timestamp=newer)
    response = ConversationService.process_message(customer.phone_number, 'Hi', channel=ChannelChoice.WHATSAPP,
        external_message_id='wamid.late-hi', external_timestamp=older)
    assert response['reply'] == ''
    assert response['ignored_reason'] == 'out_of_order'
    session.refresh_from_db()
    assert session.step == BookingStep.CANCELLED


@pytest.mark.parametrize('question', ['any discount?', 'any disount?', 'any offers?', 'best price?', 'offer undo?'])
def test_discount_questions_get_relevant_fallback_and_keep_service(question, repair):
    customer = Customer.objects.create(name='Afi', phone_number='+919999111124')
    conv = Conversation.objects.create(customer=customer, service=repair)
    response = ConversationService.process_message(customer.phone_number, question)
    assert 'only help with ac' not in response['reply'].lower()
    assert any(word in response['reply'].lower() for word in ('discount', 'offer'))
    assert response['handover_required'] is False
    assert any(option['id'] == 'talk to agent' for option in response['options'])
    conv.refresh_from_db()
    assert conv.service == repair
    assert conv.unresolved_count == 0


def test_discount_question_during_booking_does_not_fill_address(repair):
    customer = Customer.objects.create(name='Afi', phone_number='+919999111125')
    conv = Conversation.objects.create(customer=customer, service=repair)
    session = BookingSession.objects.create(conversation=conv, step=BookingStep.ADDRESS,
        data={'name':'Afi','service_id':repair.pk,'service_name':repair.name})
    response = ConversationService.process_message(customer.phone_number, 'any disount?')
    assert 'offer details' in response['reply'].lower()
    assert 'service address' in response['reply'].lower()
    session.refresh_from_db()
    assert session.step == BookingStep.ADDRESS
    assert 'service_address' not in session.data


def test_discount_query_can_use_explicit_active_faq_policy(repair):
    from apps.knowledge_base.models import FAQ
    policy = FAQ.objects.create(question='Do you offer discounts?', answer='Our service prices are fixed. No discounts are currently offered.')
    response = ConversationService.process_message('+919999111126', 'Do you offer discounts?')
    assert policy.answer in response['reply']


def test_service_offer_question_is_still_a_service_list(repair):
    from apps.chatbot.intent_service import IntentType
    assert IntentService.detect_intent('What services do you offer?')[0] == IntentType.SERVICE_LIST


@pytest.mark.parametrize('question', ['where is your location?', 'What is your location?',
    'Where are you located?', 'Send me your location', 'location please', 'AC repair shop address'])
def test_shop_location_questions_do_not_match_service_coverage(question, repair):
    from apps.chatbot.intent_service import IntentType
    assert IntentService.detect_intent(question)[0] == IntentType.SHOP_LOCATION


@pytest.mark.parametrize('question', ['Which areas do you serve?', 'Do you serve my location?',
    'What locations do you cover?', 'Do you come to my location?'])
def test_coverage_questions_keep_service_areas_intent(question, repair):
    from apps.chatbot.intent_service import IntentType
    assert IntentService.detect_intent(question)[0] == IntentType.SERVICE_AREAS


def test_location_reply_uses_configured_address_not_coverage():
    from apps.business.models import BusinessProfile
    BusinessProfile.objects.create(shop_name='Test Service Desk', address='Unit 12, Test Business Road',
        service_areas='Coverage Zone A', contact_phone='+919000000099', google_maps_url='https://maps.google.com/?q=test')
    response = ConversationService.process_message('+919999111127', 'where is your location?')
    assert 'Unit 12, Test Business Road' in response['reply']
    assert 'https://maps.google.com/?q=test' in response['reply']
    assert 'Coverage Zone A' not in response['reply']

