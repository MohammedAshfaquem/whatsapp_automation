from io import StringIO
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.chatbot.gemini_service import GeminiChatService


def test_dialogue_evaluation_is_offline_by_default():
    output = StringIO()
    with patch.object(GeminiChatService, 'interpret_booking_turn') as interpret:
        call_command('evaluate_chatbot_dialogues', stdout=output)
    interpret.assert_not_called()
    assert '25 dialogue cases' in output.getvalue()


def test_live_evaluation_checks_fields_instead_of_reply_text(settings):
    settings.GEMINI_API_KEY = 'test'
    result = {'kind': 'answer', 'recipient': 'unspecified', 'reply': '', 'fields': {'ac_type': 'Split AC'}, 'clear_fields': []}
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=result):
        output = StringIO()
        call_command('evaluate_chatbot_dialogues', '--live', '--case', 'type-correction', stdout=output)
        assert '1/1 dialogue cases passed' in output.getvalue()
        with pytest.raises(CommandError, match='language expectations'):
            call_command('evaluate_chatbot_dialogues', '--live', '--case', 'name-correction', stdout=StringIO())
