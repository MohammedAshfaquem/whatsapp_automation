import logging
import json
from time import monotonic
from typing import Optional
from django.conf import settings
from .prompts import SYSTEM_INSTRUCTION, get_system_instruction, get_booking_instruction

logger = logging.getLogger(__name__)

class GeminiChatService:
    """
    Interfaces with Google Gemini LLM for generating grounded, natural WhatsApp responses.
    """
    _client = None
    _client_key = None

    @classmethod
    def _get_client(cls):
        api_key = getattr(settings, 'GEMINI_API_KEY', '').strip()
        if not api_key:
            return None

        if cls._client is None or cls._client_key != api_key:
            try:
                from google import genai
                from google.genai import types
                cls._client = genai.Client(api_key=api_key, http_options=types.HttpOptions(
                    timeout=20000, retry_options=types.HttpRetryOptions(attempts=1)))
                cls._client_key = api_key
            except Exception as e:
                logger.warning('Failed to initialize Gemini client: %s', type(e).__name__)
                return None
        return cls._client

    @classmethod
    def is_configured(cls) -> bool:
        """Check local configuration only; provider readiness is tested separately."""
        key = getattr(settings, 'GEMINI_API_KEY', '').strip()
        return bool(key)

    @classmethod
    def generate_reply(cls, prompt: str, image_bytes: Optional[bytes] = None,
                       mime_type: str = 'image/jpeg', system_instruction=None, response_schema=None) -> Optional[str]:
        """
        Generate completion from Gemini model using system instruction and temperature for fidelity.
        """
        if not cls.is_configured():
            logger.debug("GEMINI_API_KEY is not configured or invalid. Falling back to deterministic response.")
            return None

        from .ai_status import record_ai_status, classify_provider_error
        started = monotonic()

        client = cls._get_client()
        if not client:
            record_ai_status('UNAVAILABLE')
            return None

        model_name = settings.GEMINI_CHAT_MODEL

        try:
            from google.genai import types
            config = types.GenerateContentConfig(
                system_instruction=system_instruction or get_system_instruction(),
                temperature=0.2,
                max_output_tokens=600,
            )
            if response_schema:
                config.response_mime_type = 'application/json'
                config.response_schema = response_schema

            contents = prompt
            if image_bytes:
                contents = [prompt, types.Part.from_bytes(data=image_bytes, mime_type=mime_type)]

            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config
            )

            if response and response.text:
                reply = response.text.strip()
                record_ai_status('READY' if reply else 'EMPTY_RESPONSE', int((monotonic() - started) * 1000))
                return reply or None
            record_ai_status('EMPTY_RESPONSE', int((monotonic() - started) * 1000))
            return None
        except Exception as error:
            record_ai_status(classify_provider_error(error), int((monotonic() - started) * 1000))
            logger.warning('Gemini generation failed: %s (code=%s)', type(error).__name__, getattr(error, 'code', None))
            return None

    @classmethod
    def summarize_conversation(cls, previous_summary, messages):
        from .prompts import MEMORY_INSTRUCTION
        prompt = json.dumps({'previous_summary': previous_summary, 'completed_messages': messages}, ensure_ascii=False)
        summary = cls.generate_reply(prompt, system_instruction=MEMORY_INSTRUCTION)
        return summary.strip() if summary and 5 < len(summary.strip()) <= 5000 else None

    @classmethod
    def interpret_booking_turn(cls, prompt):
        from .prompts import BOOKING_TURN_INSTRUCTION
        from apps.bookings.booking_fields import FIELD_LIMITS
        schema = {'type': 'object', 'properties': {
            'kind': {'type': 'string', 'enum': ['answer', 'conversation', 'recipient_correction']},
            'recipient': {'type': 'string', 'enum': ['self', 'other', 'unspecified']},
            'reply': {'type': 'string'},
            'fields': {'type': 'object', 'properties': {key: {'type': 'string'} for key in FIELD_LIMITS}},
            'clear_fields': {'type': 'array', 'items': {'type': 'string', 'enum': list(FIELD_LIMITS)}},
        }, 'required': ['kind', 'recipient', 'reply']}
        raw = cls.generate_reply(prompt, system_instruction=get_system_instruction() + get_booking_instruction(),
                                 response_schema=schema)
        try:
            result = json.loads(raw) if raw else None
        except (ValueError, TypeError):
            return None
        if (not isinstance(result, dict) or result.get('kind') not in ('answer', 'conversation', 'recipient_correction')
                or result.get('recipient') not in ('self', 'other', 'unspecified')
                or not isinstance(result.get('reply'), str)):
            return None
        fields = result.get('fields', {})
        clear_fields = result.get('clear_fields', [])
        if (not isinstance(fields, dict) or any(key not in FIELD_LIMITS or not isinstance(value, str)
                or len(value) > FIELD_LIMITS[key] for key, value in fields.items())
                or not isinstance(clear_fields, list) or any(not isinstance(key, str) or key not in FIELD_LIMITS for key in clear_fields)):
            return None
        result['fields'] = fields
        result['clear_fields'] = clear_fields
        return result
