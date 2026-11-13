import pytest
from django.conf import settings

@pytest.fixture(autouse=True)
def test_environment_setup(monkeypatch, tmp_path):
    """
    Ensure all unit tests run in isolation with remote API keys disabled by default,
    unless explicitly mocked or enabled inside a test.
    Prevents tests from incurring latency or external API calls.
    """
    monkeypatch.setattr(settings, 'GEMINI_API_KEY', '')
    monkeypatch.setattr(settings, 'WHATSAPP_ENABLED', False)
    monkeypatch.setattr(settings, 'WHATSAPP_TYPING_INDICATOR_ENABLED', False, raising=False)
    monkeypatch.setattr(settings, 'DEBUG', True)
    # Tests must never reset the real shop's persistent knowledge collection.
    monkeypatch.setattr(settings, 'CHROMA_PERSIST_DIRECTORY', str(tmp_path / 'chroma'))
    from apps.knowledge_base.vector_store import ChromaVectorStore
    monkeypatch.setattr(ChromaVectorStore, '_instance', None)
