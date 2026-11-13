from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from apps.chatbot.gemini_service import GeminiChatService


@pytest.mark.parametrize('raw', ['not JSON', '{}', '{"kind":"submit","recipient":"self","reply":"done"}'])
def test_interpreter_rejects_malformed_or_action_responses(raw):
    with patch.object(GeminiChatService, 'generate_reply', return_value=raw):
        assert GeminiChatService.interpret_booking_turn('Context') is None


@pytest.mark.django_db
def test_interpreter_requests_structured_output_with_the_booking_policy(settings):
    settings.GEMINI_API_KEY = 'AIzaSy-test'
    client = MagicMock()
    client.models.generate_content.return_value = SimpleNamespace(
        text='{"kind":"conversation","recipient":"unspecified","reply":"I can help clarify that."}')
    with patch.object(GeminiChatService, '_get_client', return_value=client):
        result = GeminiChatService.interpret_booking_turn('The current draft and prior summary')
    config = client.models.generate_content.call_args.kwargs['config']
    assert config.response_mime_type == 'application/json'
    assert 'BOOKING TURN INTERPRETATION' in config.system_instruction
    assert result['kind'] == 'conversation'


def test_summary_uses_a_dedicated_instruction_instead_of_chat_persona():
    with patch.object(GeminiChatService, 'generate_reply', return_value='Friend John needs a window AC inspection.') as generate:
        assert GeminiChatService.summarize_conversation('Earlier facts', [{'text':'New fact'}])
    assert 'Summarize' in generate.call_args.kwargs['system_instruction']
    assert 'Earlier facts' in generate.call_args.args[0]


@pytest.mark.parametrize('fields,clear_fields', [
    ({'customer_id': '7'}, []), ({'preferred_date': 123}, []),
    ({'service_address': 'a' * 1501}, []), ({}, ['status']), ({}, 'name'),
])
def test_interpreter_rejects_unapproved_or_malformed_fields(fields, clear_fields):
    import json
    raw = json.dumps({'kind': 'answer', 'recipient': 'unspecified', 'reply': '',
                      'fields': fields, 'clear_fields': clear_fields})
    with patch.object(GeminiChatService, 'generate_reply', return_value=raw):
        assert GeminiChatService.interpret_booking_turn('Context') is None
