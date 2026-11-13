"""Slow providers must not block unrelated writes or leave half-applied bookings."""
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import OperationalError, close_old_connections, connection
from django.utils import timezone

from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import Customer, Conversation, Message, ProcessingStatus
from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.services.models import Service


@pytest.mark.django_db(transaction=True)
def test_photo_wait_does_not_block_another_customer_write():
    waiting, finish = Event(), Event()
    atomic_at_provider = []

    def slow_photo(*args):
        atomic_at_provider.append(connection.in_atomic_block)
        waiting.set()
        assert finish.wait(5)
        return 'Please describe when the cooling problem started.'

    def receive():
        close_old_connections()
        try:
            return ConversationService.process_message('+919999980001', '[attachment:image]', external_message_id='slow-photo')
        finally:
            close_old_connections()

    with patch('apps.chatbot.handlers.image.generate_reply', side_effect=slow_photo), ThreadPoolExecutor(1) as pool:
        pending = pool.submit(receive)
        try:
            assert waiting.wait(5)
            Customer.objects.create(phone_number='+919999980002', name='Another customer')
        finally:
            finish.set()
        result = pending.result(timeout=5)
    assert atomic_at_provider == [False]
    assert result['reply'].startswith('Please describe')


@pytest.mark.django_db(transaction=True)
def test_interrupted_submission_rolls_back_and_same_inbound_can_resume():
    customer = Customer.objects.create(phone_number='+919999980003', name='Ashfaque')
    service = Service.objects.create(name='AC repair', price_amount=500)
    conversation = Conversation.objects.create(customer=customer, service=service)
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.REVIEW, data={
        'name': 'Ashfaque', 'service_id': service.pk, 'service_name': service.name,
        'ac_type': 'Window AC', 'problem_description': 'not cooling',
        'service_address': 'House 10, Test street, Kerala, 676306',
        'preferred_date': str(timezone.localdate() + timedelta(days=1)), 'preferred_time_slot': 'morning'})
    save = Message.save

    def fail_result(self, *args, **kwargs):
        if self.external_message_id == 'interrupted-submit' and 'response_data' in kwargs.get('update_fields', []):
            raise OperationalError('simulated interruption')
        return save(self, *args, **kwargs)

    with patch.object(Message, 'save', fail_result), pytest.raises(OperationalError):
        ConversationService.process_message(customer.phone_number, 'booking_submit', external_message_id='interrupted-submit')
    assert Booking.objects.count() == 0
    session.refresh_from_db()
    assert session.step == BookingStep.REVIEW
    pending = Message.objects.get(external_message_id='interrupted-submit')
    assert pending.processing_status == ProcessingStatus.PROCESSING
    result = ConversationService.process_message(customer.phone_number, 'booking_submit', external_message_id='interrupted-submit')
    replay = ConversationService.process_message(customer.phone_number, 'booking_submit', external_message_id='interrupted-submit')
    assert Booking.objects.count() == 1
    assert result['booking_id'] == Booking.objects.get().pk
    assert replay == result
    assert Message.objects.filter(external_message_id='interrupted-submit').count() == 1


@pytest.mark.django_db(transaction=True)
def test_failed_webhook_returns_retryable_response_even_if_logging_is_locked(client):
    from apps.whatsapp.models import WhatsAppWebhookLog
    log = WhatsAppWebhookLog.objects.create(event_type='message', whatsapp_message_id='locked-event', raw_payload={})
    payload = {'entry': [{'changes': [{'value': {'messages': [{
        'from': '919999980004', 'id': 'locked-event', 'type': 'text', 'text': {'body': 'Hi'}}]}}]}]}
    with (patch('apps.whatsapp.webhook_service.WebhookService.verify_signature', return_value=True),
          patch('apps.whatsapp.events.WhatsAppWebhookLog.objects.get_or_create', return_value=(log, False)),
          patch.object(WhatsAppWebhookLog, 'save', side_effect=OperationalError('database is locked')),
          patch.object(ConversationService, 'process_message', side_effect=OperationalError('database is locked'))):
        response = client.post('/api/whatsapp/webhook/', payload, content_type='application/json')
    assert response.status_code == 503
    assert response.json()['failures'] == 1
    log.refresh_from_db()
    assert not log.is_processed


@pytest.mark.django_db(transaction=True)
def test_same_customer_busy_but_other_customer_can_continue():
    from apps.chatbot.processing import customer_turn, ConversationBusyError
    customer = Customer.objects.create(phone_number='+919999980005')
    with customer_turn(customer):
        with pytest.raises(ConversationBusyError):
            ConversationService.process_message(customer.phone_number, 'Hi', external_message_id='busy-turn')
        result = ConversationService.process_message('+919999980006', 'Hi')
        assert result['reply']
        assert not Message.objects.filter(external_message_id='busy-turn').exists()
    assert ConversationService.process_message(customer.phone_number, 'Hi', external_message_id='busy-turn')['reply']


@pytest.mark.django_db(transaction=True)
def test_handover_during_ai_wait_suppresses_bot_answer():
    from apps.chatbot.models import ConversationStatus

    def staff_takes_over(message, media_id, conversation):
        Conversation.objects.filter(pk=conversation.pk).update(status=ConversationStatus.HUMAN_HANDOVER)
        return 'Prepared photo answer'

    with patch('apps.chatbot.handlers.image.generate_reply', side_effect=staff_takes_over):
        result = ConversationService.process_message('+919999980007', '[attachment:image]')
    assert result['handover_required']
    assert result['reply'] == ''


@pytest.mark.django_db(transaction=True)
def test_expired_worker_cannot_finalize_or_clear_new_lease():
    from apps.chatbot.processing import ConversationBusyError

    def replace_owner(message, media_id, conversation):
        Customer.objects.filter(pk=conversation.customer_id).update(
            processing_token='new-owner', processing_until=timezone.now() + timedelta(minutes=3))
        return 'Old worker answer'

    with patch('apps.chatbot.handlers.image.generate_reply', side_effect=replace_owner), pytest.raises(ConversationBusyError):
        ConversationService.process_message('+919999980008', '[attachment:image]', external_message_id='expired-turn')
    assert Customer.objects.get(phone_number='+919999980008').processing_token == 'new-owner'
    assert not Message.objects.get(external_message_id='expired-turn').response_data


@pytest.mark.django_db
def test_latest_history_is_stable_when_messages_share_a_timestamp():
    customer = Customer.objects.create(phone_number='+919999980009')
    conversation = Conversation.objects.create(customer=customer)
    first = Message.objects.create(conversation=conversation, direction='OUTBOUND', sender_type='BOT', message_text='Old reply')
    latest = Message.objects.create(conversation=conversation, direction='OUTBOUND', sender_type='BOT', message_text='New reply')
    Message.objects.filter(conversation=conversation).update(created_at=first.created_at)
    assert conversation.messages.last().pk == latest.pk


@pytest.mark.django_db
def test_gemini_busy_response_has_no_hidden_retries(settings):
    import httpx
    from google import genai
    import tenacity
    from apps.chatbot.gemini_service import GeminiChatService
    requests = []
    settings.GEMINI_API_KEY = 'test-key'
    original_client = genai.Client

    def unavailable(request):
        requests.append(request)
        return httpx.Response(503, json={'error': {'code': 503, 'message': 'Temporarily unavailable', 'status': 'UNAVAILABLE'}})

    def local_client(**kwargs):
        kwargs['http_options'].client_args = {'transport': httpx.MockTransport(unavailable)}
        client = original_client(**kwargs)
        client._api_client._retry.wait = tenacity.wait_none()
        return client

    with patch.object(GeminiChatService, '_client', None), patch('google.genai.Client', side_effect=local_client):
        assert GeminiChatService.generate_reply('Hello') is None
    assert len(requests) == 1


@pytest.mark.django_db(transaction=True)
def test_completed_reply_replays_after_a_newer_whatsapp_turn():
    from apps.chatbot.models import ChannelChoice
    now = timezone.now()
    options = {'phone_number': '+919999980010', 'channel': ChannelChoice.WHATSAPP}
    first = ConversationService.process_message(**options, message_text='Hi', external_message_id='earlier', external_timestamp=now)
    ConversationService.process_message(**options, message_text='menu', external_message_id='later', external_timestamp=now + timedelta(seconds=1))
    replay = ConversationService.process_message(**options, message_text='Hi', external_message_id='earlier', external_timestamp=now)
    assert replay == first


@pytest.mark.django_db(transaction=True)
def test_new_turn_cannot_overtake_persisted_unfinished_message():
    from apps.chatbot.processing import ConversationBusyError
    customer = Customer.objects.create(phone_number='+919999980011')
    conversation = Conversation.objects.create(customer=customer)
    Message.objects.create(conversation=conversation, direction='INBOUND', sender_type='CUSTOMER',
        message_text='Hi', external_message_id='unfinished', processing_status=ProcessingStatus.PROCESSING)
    with pytest.raises(ConversationBusyError):
        ConversationService.process_message(customer.phone_number, 'menu', external_message_id='overtaking')
    assert not Message.objects.filter(external_message_id='overtaking').exists()
    assert ConversationService.process_message(customer.phone_number, 'Hi', external_message_id='unfinished')['reply']
    assert ConversationService.process_message(customer.phone_number, 'menu', external_message_id='overtaking')['reply']


@pytest.mark.django_db(transaction=True)
def test_expired_summary_worker_cannot_overwrite_newer_memory():
    from apps.chatbot.processing import ConversationBusyError
    customer = Customer.objects.create(phone_number='+919999980012')
    conversation = Conversation.objects.create(customer=customer)
    for _ in range(10):
        Message.objects.create(conversation=conversation, direction='INBOUND', sender_type='CUSTOMER', message_text='Hi')
        Message.objects.create(conversation=conversation, direction='OUTBOUND', sender_type='BOT', message_text='Hello')

    def newer_summary(*args):
        Customer.objects.filter(pk=customer.pk).update(processing_token='new-owner', processing_until=timezone.now() + timedelta(minutes=3))
        Conversation.objects.filter(pk=conversation.pk).update(memory_summary='Newer verified summary', memory_through_message_id=999)
        return 'Old worker summary'

    with patch('apps.chatbot.gemini_service.GeminiChatService.summarize_conversation', side_effect=newer_summary), pytest.raises(ConversationBusyError):
        ConversationService.process_message(customer.phone_number, 'Hi', external_message_id='expired-summary')
    conversation.refresh_from_db()
    assert conversation.memory_summary == 'Newer verified summary'
    assert conversation.memory_through_message_id == 999


@pytest.mark.django_db(transaction=True)
def test_retry_after_staff_closes_conversation_keeps_original_audit_record():
    customer = Customer.objects.create(phone_number='+919999980013')
    conversation = Conversation.objects.create(customer=customer, status='CLOSED')
    inbound = Message.objects.create(conversation=conversation, direction='INBOUND', sender_type='CUSTOMER',
        message_text='book', external_message_id='closed-retry', processing_status=ProcessingStatus.PROCESSING)
    result = ConversationService.process_message(customer.phone_number, 'book', external_message_id='closed-retry')
    assert result['conversation_id'] == conversation.pk
    assert result['reply'] == ''
    assert Conversation.objects.count() == 1
    assert not BookingSession.objects.exists()
    inbound.refresh_from_db()
    assert inbound.response_data['conversation_id'] == inbound.conversation_id
    assert inbound.processing_status == ProcessingStatus.PROCESSED
