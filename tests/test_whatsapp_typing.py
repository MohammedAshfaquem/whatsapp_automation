from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import ChannelChoice, Conversation, Customer
from apps.whatsapp.webhook_service import WebhookService
from apps.whatsapp.whatsapp_client import WhatsAppClient

pytestmark = pytest.mark.django_db


def test_typing_indicator_uses_native_read_receipt_payload(settings):
    settings.WHATSAPP_TYPING_INDICATOR_ENABLED = True
    config = {'enabled': True, 'phone_number_id': '123456', 'access_token': 'private-token'}
    provider = MagicMock()
    provider.post.return_value = SimpleNamespace(status_code=200, json=lambda: {'success': True})
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value=config), patch('httpx.Client') as client:
        client.return_value.__enter__.return_value = provider
        assert WhatsAppClient.send_typing_indicator('wamid.inbound') is True
    assert provider.post.call_args.kwargs['json'] == {
        'messaging_product': 'whatsapp', 'status': 'read', 'message_id': 'wamid.inbound',
        'typing_indicator': {'type': 'text'}}
    assert provider.post.call_args.args[0].endswith('/123456/messages')


@pytest.mark.parametrize('problem', [httpx.ReadTimeout('timeout'), ValueError('invalid JSON')])
def test_indicator_failure_is_nonfatal(settings, problem):
    settings.WHATSAPP_TYPING_INDICATOR_ENABLED = True
    config = {'enabled': True, 'phone_number_id': '123456', 'access_token': 'secret'}
    provider = MagicMock()
    provider.post.side_effect = problem
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value=config), patch('httpx.Client') as client:
        client.return_value.__enter__.return_value = provider
        assert WhatsAppClient.send_typing_indicator('wamid.inbound') is False


def test_disabled_indicator_makes_no_network_request(settings):
    settings.WHATSAPP_TYPING_INDICATOR_ENABLED = False
    with patch('httpx.Client') as client:
        assert WhatsAppClient.send_typing_indicator('wamid.inbound') is False
    client.assert_not_called()


def test_typing_precedes_reply_generation_and_webhook_replay_does_not_repeat_it():
    calls = []
    with patch.object(WhatsAppClient, 'send_typing_indicator', side_effect=lambda _: calls.append('typing')), \
            patch('apps.chatbot.handlers.text.generate_reply', side_effect=lambda *_: calls.append('reply') or 'Hello!'):
        first = ConversationService.process_message('+919999111189', 'hello', channel=ChannelChoice.WHATSAPP,
                                                     external_message_id='wamid.typing')
        replay = ConversationService.process_message('+919999111189', 'hello', channel=ChannelChoice.WHATSAPP,
                                                      external_message_id='wamid.typing')
    assert calls == ['typing', 'reply']
    assert first == replay


def test_handover_website_and_status_callbacks_do_not_show_bot_typing():
    customer = Customer.objects.create(phone_number='+919999111190')
    Conversation.objects.create(customer=customer, channel=ChannelChoice.WHATSAPP, status='HUMAN_HANDOVER')
    with patch.object(WhatsAppClient, 'send_typing_indicator') as typing:
        result = ConversationService.process_message(customer.phone_number, 'hello', channel=ChannelChoice.WHATSAPP,
                                                     external_message_id='wamid.human')
        ConversationService.process_message('+919999111191', 'hello')
        WebhookService.process_incoming_payload({'entry': [{'changes': [{'value': {
            'statuses': [{'id': 'wamid.outbound', 'status': 'read'}]}}]}]})
    assert not result['reply']
    typing.assert_not_called()


def test_failed_indicator_does_not_block_chat_reply():
    with patch.object(WhatsAppClient, 'send_typing_indicator', return_value=False):
        result = ConversationService.process_message('+919999111192', 'hello', channel=ChannelChoice.WHATSAPP,
                                                     external_message_id='wamid.failure')
    assert result['reply']


@pytest.mark.parametrize('status,body', [(400, {'error': 'unsupported'}), (200, []), (200, {'success': False})])
def test_rejected_or_malformed_indicator_response_is_nonfatal(settings, status, body):
    settings.WHATSAPP_TYPING_INDICATOR_ENABLED = True
    provider = MagicMock()
    provider.post.return_value = SimpleNamespace(status_code=status, json=lambda: body)
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={
            'enabled': True, 'phone_number_id': '123456', 'access_token': 'secret'}), patch('httpx.Client') as client:
        client.return_value.__enter__.return_value = provider
        assert WhatsAppClient.send_typing_indicator('wamid.inbound') is False


def test_out_of_order_messages_do_not_trigger_typing():
    from datetime import timedelta
    from django.utils import timezone
    now = timezone.now()
    customer = Customer.objects.create(phone_number='+919999111193', last_whatsapp_event_at=now)
    with patch.object(WhatsAppClient, 'send_typing_indicator') as typing:
        result = ConversationService.process_message(customer.phone_number, 'hello', channel=ChannelChoice.WHATSAPP,
            external_message_id='wamid.old', external_timestamp=now - timedelta(minutes=1))
    assert result['ignored_reason'] == 'out_of_order'
    typing.assert_not_called()
