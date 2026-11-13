"""Safe, persistent provider diagnostics for the staff portal."""
import hashlib

from django.conf import settings
from django.utils import timezone

from .models import AIConnectionStatus

MESSAGES = {
    'NOT_CONFIGURED': 'AI key is missing. Configure it on the server and test the connection.',
    'UNTESTED': 'This AI configuration has not been tested yet.',
    'READY': 'The AI provider responded successfully.',
    'INVALID_CREDENTIALS': 'The AI provider rejected access. Check the server API key and permissions.',
    'UNAVAILABLE': 'The AI provider could not respond. Check the connection, quota, and selected model, then retry.',
    'EMPTY_RESPONSE': 'The AI provider returned no usable text. Retry the connection test.',
}


def configuration_hash():
    value = f"{getattr(settings, 'GEMINI_CHAT_MODEL', '')}:{getattr(settings, 'GEMINI_API_KEY', '').strip()}"
    return hashlib.sha256(value.encode()).hexdigest()


def record_ai_status(status, latency_ms=0):
    AIConnectionStatus.objects.update_or_create(provider='gemini', defaults={
        'configuration_hash': configuration_hash(), 'status': status,
        'checked_at': timezone.now(), 'latency_ms': max(0, latency_ms)})


def get_ai_status():
    row = AIConnectionStatus.objects.filter(provider='gemini', configuration_hash=configuration_hash()).first()
    configured = bool(getattr(settings, 'GEMINI_API_KEY', '').strip())
    status = (row.status if row else 'UNTESTED') if configured else 'NOT_CONFIGURED'
    return {'status': status, 'message': MESSAGES[status],
            'checked_at': row.checked_at.isoformat() if row and configured else None,
            'latency_ms': row.latency_ms if row and configured else None}


def classify_provider_error(error):
    code = str(getattr(error, 'code', ''))
    # Inspect locally only. Neither the exception nor its text is persisted/exposed.
    text = str(error).lower()
    if code in ('401', '403') or (code == '400' and ('api key not valid' in text or 'api_key_invalid' in text)):
        return 'INVALID_CREDENTIALS'
    return 'UNAVAILABLE'
