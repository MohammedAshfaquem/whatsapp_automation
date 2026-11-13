"""Benign provider probe. Print safe diagnostics only, never API keys or request headers."""
import os
import json
import re
import argparse
from time import monotonic

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
import django
django.setup()

from django.conf import settings
from google.genai import types
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.ai_status import record_ai_status, classify_provider_error

started = monotonic()
parser = argparse.ArgumentParser()
parser.add_argument('--list-models', action='store_true')
parser.add_argument('--model')
args = parser.parse_args()
model = args.model or settings.GEMINI_CHAT_MODEL
try:
    client = GeminiChatService._get_client()
    if client is None:
        raise RuntimeError('Gemini client is not configured')
    if args.list_models:
        models = [item.name for item in client.models.list() if 'flash' in (item.name or '')]
        print(json.dumps({'available_flash_models': models[:20]}))
        raise SystemExit(0)
    result = client.models.generate_content(model=model, contents='Reply with OK only.',
        config=types.GenerateContentConfig(temperature=0, max_output_tokens=50))
    status = 'READY' if result and result.text and result.text.strip() else 'EMPTY_RESPONSE'
    if model == settings.GEMINI_CHAT_MODEL:
        record_ai_status(status, int((monotonic() - started) * 1000))
    print(json.dumps({'status': status, 'model': model}))
except Exception as error:
    status = classify_provider_error(error)
    if model == settings.GEMINI_CHAT_MODEL:
        record_ai_status(status, int((monotonic() - started) * 1000))
    message = str(getattr(error, 'message', type(error).__name__))
    if settings.GEMINI_API_KEY:
        message = message.replace(settings.GEMINI_API_KEY, '[redacted]')
    message = re.sub(r'AIza[\w-]+', '[redacted]', message)
    print(json.dumps({'status': status, 'code': getattr(error, 'code', None), 'reason': message[:400]}))
