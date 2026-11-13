"""Rolling summaries of completed exchanges; original messages remain the audit trail."""
import json

from apps.bookings.models import BookingSession
from .gemini_service import GeminiChatService
from .models import MessageDirection
from django.utils import timezone
from .processing import ConversationBusyError

class ConversationMemory:
    EXCHANGES_PER_BATCH = 10

    @staticmethod
    def _history(messages):
        return [{'direction': message.direction, 'sender_type': message.sender_type,
                 'text': message.message_text} for message in messages]

    @classmethod
    def prepare(cls, conversation, before_message_id, processing_token=None):
        """Called under the customer's processing lease, outside write transactions."""
        messages = list(conversation.messages.filter(
            pk__gt=conversation.memory_through_message_id, pk__lt=before_message_id).order_by('pk'))
        starts = [index for index, message in enumerate(messages) if message.direction == MessageDirection.INBOUND]
        if len(starts) < cls.EXCHANGES_PER_BATCH:
            return
        end = starts[cls.EXCHANGES_PER_BATCH] if len(starts) > cls.EXCHANGES_PER_BATCH else len(messages)
        batch = messages[:end]
        summary = GeminiChatService.summarize_conversation(conversation.memory_summary, cls._history(batch))
        if not summary:
            # Do not drop unsummarized context or advance the cursor on an API failure.
            return
        changes = {'memory_summary': summary, 'memory_through_message_id': batch[-1].pk}
        query = type(conversation).objects.filter(pk=conversation.pk,
            memory_through_message_id=conversation.memory_through_message_id)
        if processing_token is not None:
            query = query.filter(customer__processing_token=processing_token, customer__processing_until__gt=timezone.now())
        if not query.update(**changes):
            raise ConversationBusyError('Conversation memory changed while preparing this message.')
        conversation.memory_summary = summary
        conversation.memory_through_message_id = batch[-1].pk

    @classmethod
    def context(cls, conversation):
        """Current input has its own section; do not duplicate it in recent history."""
        current_id = conversation.messages.filter(direction=MessageDirection.INBOUND).order_by('-pk').values_list('pk', flat=True).first()
        messages = conversation.messages.filter(pk__gt=conversation.memory_through_message_id).order_by('pk')
        if current_id:
            messages = messages.filter(pk__lt=current_id)
        session = BookingSession.objects.filter(conversation=conversation).first()
        draft = {'step': session.step, 'details': session.data} if session else {'step': 'No draft'}
        return {'conversation_history': cls._history(messages),
                'conversation_summary': conversation.memory_summary,
                'booking_context': json.dumps(draft, ensure_ascii=False)}
