from unittest.mock import patch

import pytest

from apps.chatbot.models import Customer, Conversation, Message
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.prompts import build_rag_prompt


pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation():
    return Conversation.objects.create(customer=Customer.objects.create(phone_number='+919999111170'))


def exchange(conversation, text):
    Message.objects.create(conversation=conversation, direction='INBOUND', sender_type='CUSTOMER', message_text=text)
    return Message.objects.create(conversation=conversation, direction='OUTBOUND', sender_type='BOT', message_text='Reply ' + text)


def test_rollover_summarizes_ten_exchanges_without_deleting_originals(conversation):
    from apps.chatbot.memory import ConversationMemory
    for index in range(10):
        end = exchange(conversation, f'Message {index}')
    current = Message.objects.create(conversation=conversation, direction='INBOUND', message_text='New question')
    with patch.object(GeminiChatService, 'summarize_conversation', return_value='Booking is for the customer’s friend.') as summarize:
        ConversationMemory.prepare(conversation, current.pk)
    conversation.refresh_from_db()
    assert conversation.memory_summary == 'Booking is for the customer’s friend.'
    assert conversation.memory_through_message_id == end.pk
    assert Message.objects.filter(conversation=conversation).count() == 21
    assert len(summarize.call_args.args[1]) == 20
    context = ConversationMemory.context(conversation)
    assert context['conversation_summary'] == conversation.memory_summary
    assert context['conversation_history'] == []  # The current message has its own prompt section.


def test_successive_batches_merge_the_previous_summary(conversation):
    from apps.chatbot.memory import ConversationMemory
    for index in range(10):
        exchange(conversation, str(index))
    marker = Message.objects.create(conversation=conversation, direction='INBOUND', message_text='Next batch')
    with patch.object(GeminiChatService, 'summarize_conversation', return_value='First summary'):
        ConversationMemory.prepare(conversation, marker.pk)
    Message.objects.create(conversation=conversation, direction='OUTBOUND', message_text='Reply')
    for index in range(9):
        exchange(conversation, 'second ' + str(index))
    current = Message.objects.create(conversation=conversation, direction='INBOUND', message_text='Third batch')
    with patch.object(GeminiChatService, 'summarize_conversation', return_value='Merged summary') as summarize:
        ConversationMemory.prepare(conversation, current.pk)
    assert summarize.call_args.args[0] == 'First summary'
    assert len(summarize.call_args.args[1]) == 20
    assert conversation.memory_summary == 'Merged summary'


def test_failed_summary_keeps_cursor_and_pending_history_for_retry(conversation):
    from apps.chatbot.memory import ConversationMemory
    for index in range(10):
        exchange(conversation, f'Keep {index}')
    current = Message.objects.create(conversation=conversation, direction='INBOUND', message_text='New question')
    with patch.object(GeminiChatService, 'summarize_conversation', return_value=None):
        ConversationMemory.prepare(conversation, current.pk)
    assert conversation.memory_through_message_id == 0
    assert len(ConversationMemory.context(conversation)['conversation_history']) == 20


def test_memory_is_isolated_to_one_conversation(conversation):
    from apps.chatbot.memory import ConversationMemory
    other = Conversation.objects.create(customer=Customer.objects.create(phone_number='+919999111171'))
    exchange(other, 'PRIVATE other customer')
    exchange(conversation, 'Own conversation')
    current = Message.objects.create(conversation=conversation, direction='INBOUND', message_text='Question')
    context = ConversationMemory.context(conversation)
    assert 'PRIVATE' not in str(context)
    assert 'Own conversation' in str(context)
    assert 'Question' not in str(context['conversation_history'])


def test_prompt_includes_summary_and_all_ten_exchanges_without_six_message_clipping():
    history = [{'direction': 'INBOUND', 'text': f'Customer turn {index}'} for index in range(10)]
    prompt = build_rag_prompt('Current unique question', 'Shop', 'Services', 'Policies', history,
                              conversation_summary='The visit is for a friend.', booking_context='Recipient: John')
    assert 'Customer turn 0' in prompt and 'Customer turn 9' in prompt
    assert 'The visit is for a friend.' in prompt
    assert 'Recipient: John' in prompt
    assert prompt.count('Current unique question') == 1


def test_both_text_and_image_prompt_builder_uses_summary_and_current_draft(conversation):
    from apps.bookings.models import BookingSession
    from apps.chatbot.handlers.text import build_contextual_prompt
    conversation.memory_summary = 'Earlier the customer said this is for a friend.'
    conversation.save()
    BookingSession.objects.create(conversation=conversation, step='AC_DETAILS',
        data={'booking_for_other': True, 'recipient_name': 'John', 'ac_type': 'Window AC'})
    prompt = build_contextual_prompt('Current question', conversation)
    assert 'Earlier the customer' in prompt
    assert 'John' in prompt
    assert 'Window AC' in prompt


def test_replayed_message_does_not_summarize_twice(conversation):
    from apps.chatbot.conversation_service import ConversationService
    for index in range(10):
        exchange(conversation, str(index))
    with patch.object(GeminiChatService, 'summarize_conversation', return_value='Summary of earlier exchanges') as summarize:
        first = ConversationService.process_message(conversation.customer.phone_number, 'hello', external_message_id='memory.retry')
        second = ConversationService.process_message(conversation.customer.phone_number, 'hello', external_message_id='memory.retry')
    assert first == second
    assert summarize.call_count == 1
