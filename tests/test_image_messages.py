from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import httpx
import pytest

from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.models import Conversation, Customer, Message
from apps.bookings.models import BookingSession, BookingStep
from apps.services.models import Service, PriceType
from apps.whatsapp.webhook_service import WebhookService
from apps.whatsapp.whatsapp_client import WhatsAppClient


pytestmark = pytest.mark.django_db


def image_payload():
    return {'entry': [{'changes': [{'value': {'messages': [{
        'id': 'wamid.photo', 'from': '919999111120', 'type': 'image',
        'image': {'id': '12345', 'caption': 'Ice on this pipe, not cooling'},
    }]}}]}]}


def test_whatsapp_image_reaches_gemini_with_caption_and_services(settings):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    Service.objects.create(name='AC inspection', price_type=PriceType.FIXED, price_amount=500)
    reply = 'This appears to show ice on the pipe. AC inspection can help identify the cause.'
    with patch.object(WhatsAppClient, 'download_image', return_value=(b'photo', 'image/jpeg')) as download, \
            patch.object(GeminiChatService, 'generate_reply', return_value=reply) as generate, \
            patch('apps.whatsapp.events.dispatch', return_value=True):
        assert WebhookService.process_incoming_payload(image_payload())['processed'] == 1
        WebhookService.process_incoming_payload(image_payload())
    download.assert_called_once_with('12345')
    assert generate.call_count == 1
    prompt = generate.call_args.args[0]
    assert 'Ice on this pipe, not cooling' in prompt
    assert 'AC inspection' in prompt
    assert generate.call_args.kwargs['image_bytes'] == b'photo'
    assert Message.objects.filter(message_text=reply).count() == 1
    assert 'Ice on this pipe' in Message.objects.get(direction='INBOUND').message_text


@pytest.mark.parametrize('download_result', [None, (b'photo', 'image/jpeg')])
def test_image_failures_ask_for_description(settings, download_result):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    with patch.object(WhatsAppClient, 'download_image', return_value=download_result), \
            patch.object(GeminiChatService, 'generate_reply', return_value=None):
        result = ConversationService.process_message('+919999111121', '[attachment:image]', image_media_id='12345')
    assert 'describe' in result['reply'].lower()
    assert 'leak' not in result['reply'].lower()
    assert 'clear' not in result['reply'].lower()
    assert ('access' if download_result is None else 'analysis is unavailable') in result['reply'].lower()


def test_image_does_not_interrupt_human_handover(settings):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    customer = Customer.objects.create(phone_number='+919999111122')
    Conversation.objects.create(customer=customer, status='HUMAN_HANDOVER')
    with patch.object(WhatsAppClient, 'download_image') as download:
        result = ConversationService.process_message(customer.phone_number, '[attachment:image]', image_media_id='12345')
    assert result['reply'] == ''
    download.assert_not_called()


def test_photo_caption_cannot_become_a_booking_answer(settings):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    customer = Customer.objects.create(phone_number='+919999111123')
    conversation = Conversation.objects.create(customer=customer)
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.NAME)
    with patch.object(WhatsAppClient, 'download_image', return_value=(b'photo', 'image/jpeg')), \
            patch.object(GeminiChatService, 'generate_reply', return_value='Could you describe the issue?'):
        ConversationService.process_message(customer.phone_number, '[attachment:image]\nMain menu', image_media_id='12345')
    session.refresh_from_db()
    assert session.step == BookingStep.NAME
    assert session.data == {}


def test_unconfigured_image_support_asks_for_description():
    with patch.object(WhatsAppClient, 'download_image') as download:
        result = ConversationService.process_message('+919999111124', '[attachment:image]', image_media_id='12345')
    assert 'describe' in result['reply'].lower()
    assert 'analysis is unavailable' in result['reply'].lower()
    assert 'clear' not in result['reply'].lower()
    download.assert_not_called()


def test_rejected_ai_credentials_do_not_blame_photo_quality(settings):
    from apps.chatbot.ai_status import get_ai_status
    settings.GEMINI_API_KEY = 'AIzaSy-private-test'
    error = RuntimeError('API key not valid')
    error.code = 400
    provider = MagicMock()
    provider.models.generate_content.side_effect = error
    with patch.object(WhatsAppClient, 'download_image', return_value=(b'photo', 'image/jpeg')), \
            patch.object(GeminiChatService, '_get_client', return_value=provider):
        result = ConversationService.process_message('+919999111194', '[attachment:image]', image_media_id='12345')
    assert get_ai_status()['status'] == 'INVALID_CREDENTIALS'
    assert 'analysis is unavailable' in result['reply'].lower()
    assert 'clear' not in result['reply'].lower()
    assert settings.GEMINI_API_KEY not in result['reply']


def test_actual_photo_quality_clarification_from_model_is_preserved(settings):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    answer = 'The photo is too blurry to see the pipe. Could you send a clearer photo?'
    with patch.object(WhatsAppClient, 'download_image', return_value=(b'photo', 'image/jpeg')), \
            patch.object(GeminiChatService, 'generate_reply', return_value=answer):
        result = ConversationService.process_message('+919999111195', '[attachment:image]', image_media_id='12345')
    assert result['reply'] == answer


def test_gemini_receives_image_bytes(settings):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(text='Please send a clearer photo.')
    with patch.object(GeminiChatService, '_get_client', return_value=client):
        assert GeminiChatService.generate_reply('Inspect this photo', image_bytes=b'photo', mime_type='image/jpeg')
    contents = client.models.generate_content.call_args.kwargs['contents']
    assert contents[0] == 'Inspect this photo'
    assert contents[1].inline_data.data == b'photo'
    assert contents[1].inline_data.mime_type == 'image/jpeg'
    instruction = client.models.generate_content.call_args.kwargs['config'].system_instruction
    assert 'photo cannot confirm a gas leak' in instruction


def media_client(metadata, content=b'photo'):
    client = MagicMock()
    client.__enter__.return_value = client
    client.get.return_value = httpx.Response(200, json=metadata, request=httpx.Request('GET', 'https://graph.facebook.com/12345'))
    response = httpx.Response(200, content=content, request=httpx.Request('GET', metadata['url']))
    client.stream.return_value.__enter__.return_value = response
    return client


def test_download_image_uses_authenticated_meta_media():
    metadata = {'url': 'https://lookaside.fbsbx.com/whatsapp_business/attachments/?id=12345',
                'mime_type': 'image/jpeg', 'file_size': 5}
    client = media_client(metadata)
    with patch('apps.whatsapp.whatsapp_client.WhatsAppConfig.get_settings', return_value={'access_token': 'test-token'}), \
            patch('apps.whatsapp.whatsapp_client.httpx.Client', return_value=client):
        assert WhatsAppClient.download_image('12345') == (b'photo', 'image/jpeg')
    assert client.get.call_args.kwargs['headers']['Authorization'] == 'Bearer test-token'
    assert client.stream.call_args.kwargs['headers']['Authorization'] == 'Bearer test-token'


@pytest.mark.parametrize('overrides', [
    {'url': 'https://untrusted.example/image.jpg'},
    {'mime_type': 'application/pdf'},
    {'file_size': 6 * 1024 * 1024},
])
def test_download_image_rejects_invalid_media(overrides):
    metadata = {'url': 'https://lookaside.fbsbx.com/image', 'mime_type': 'image/jpeg', 'file_size': 5, **overrides}
    client = media_client(metadata)
    with patch('apps.whatsapp.whatsapp_client.WhatsAppConfig.get_settings', return_value={'access_token': 'test-token'}), \
            patch('apps.whatsapp.whatsapp_client.httpx.Client', return_value=client):
        assert WhatsAppClient.download_image('12345') is None
    client.stream.assert_not_called()


def test_download_image_limits_actual_bytes_even_if_metadata_is_wrong():
    metadata = {'url': 'https://lookaside.fbsbx.com/image', 'mime_type': 'image/jpeg', 'file_size': 5}
    client = media_client(metadata, content=b'x' * (5 * 1024 * 1024 + 1))
    with patch('apps.whatsapp.whatsapp_client.WhatsAppConfig.get_settings', return_value={'access_token': 'test-token'}), \
            patch('apps.whatsapp.whatsapp_client.httpx.Client', return_value=client):
        assert WhatsAppClient.download_image('12345') is None


def test_download_image_handles_timeout():
    with patch('apps.whatsapp.whatsapp_client.WhatsAppConfig.get_settings', return_value={'access_token': 'test-token'}), \
            patch('apps.whatsapp.whatsapp_client.httpx.Client', side_effect=httpx.ReadTimeout('unavailable')):
        assert WhatsAppClient.download_image('12345') is None
