import socket
import pytest
from django.conf import settings
from django.test import override_settings


@pytest.fixture(autouse=True)
def test_environment_setup(monkeypatch, tmp_path):
    """
    Ensure all unit tests run in isolation with remote API keys disabled by default,
    isolated media/vector directories, and test DNS mappings.
    """
    monkeypatch.setattr(settings, 'GEMINI_API_KEY', '')
    monkeypatch.setattr(settings, 'WHATSAPP_ENABLED', False)
    monkeypatch.setattr(settings, 'WHATSAPP_TYPING_INDICATOR_ENABLED', False, raising=False)
    monkeypatch.setattr(settings, 'DEBUG', True)
    # Tests must never reset the real shop's persistent knowledge collection.
    monkeypatch.setattr(settings, 'CHROMA_PERSIST_DIRECTORY', str(tmp_path / 'chroma'))
    from apps.knowledge_base.vector_store import ChromaVectorStore
    monkeypatch.setattr(ChromaVectorStore, '_instance', None)

    # Test-only DNS mock mapping for test domains so production code stays pure
    real_getaddrinfo = socket.getaddrinfo
    TEST_DNS_MAP = {
        'api.externalclient.com': '93.184.216.34',
        'webhook.site': '93.184.216.35',
        'hooks.slack.com': '93.184.216.36',
    }

    def mock_getaddrinfo(host, port, *args, **kwargs):
        if host in TEST_DNS_MAP:
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (TEST_DNS_MAP[host], port))]
        return real_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, 'getaddrinfo', mock_getaddrinfo)

    media_root = tmp_path / 'media'
    media_root.mkdir(parents=True, exist_ok=True)
    with override_settings(MEDIA_ROOT=str(media_root)):
        yield
