from unittest.mock import patch
from pathlib import Path
import runpy

import pytest
from django.db import OperationalError
from django.test import Client, override_settings
from django.core.exceptions import ImproperlyConfigured


@pytest.mark.parametrize('secret,hosts', [('', 'example.com'), ('django-insecure-test', 'example.com'), ('a' * 64, 'example.com'), ('valid-secret-' * 6, '*'), ('valid-secret-' * 6, '')])
def test_production_rejects_unsafe_configuration(monkeypatch, secret, hosts):
    monkeypatch.setenv('DJANGO_DEBUG', 'False')
    monkeypatch.setenv('DJANGO_SECRET_KEY', secret)
    monkeypatch.setenv('DJANGO_ALLOWED_HOSTS', hosts)
    with pytest.raises(ImproperlyConfigured):
        runpy.run_path(str(Path(__file__).resolve().parents[1] / 'config' / 'settings.py'))


def test_production_security_defaults(monkeypatch):
    monkeypatch.setenv('DJANGO_DEBUG', 'False')
    monkeypatch.setenv('DJANGO_SECRET_KEY', 'test-production-secret-' * 4)
    monkeypatch.setenv('DJANGO_ALLOWED_HOSTS', 'service.example.com')
    monkeypatch.setenv('DJANGO_CSRF_TRUSTED_ORIGINS', 'https://service.example.com')
    config = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'config' / 'settings.py'))
    assert config['CSRF_TRUSTED_ORIGINS'] == ['https://service.example.com']
    assert config['SESSION_COOKIE_SECURE'] and config['CSRF_COOKIE_SECURE']
    assert config['SECURE_SSL_REDIRECT']
    assert config['SECURE_HSTS_SECONDS'] > 0


@pytest.mark.django_db
def test_health_checks_database_without_caching():
    response = Client().get('/health/')
    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}
    assert response['Cache-Control'] == 'no-store'


def test_health_does_not_disclose_database_error():
    with patch('config.health.connections') as connections:
        connections.__getitem__.return_value.cursor.side_effect = OperationalError('secret database address')
        response = Client().get('/health/')
    assert response.status_code == 503
    assert response.json() == {'status': 'unavailable'}


@override_settings(SECURE_SSL_REDIRECT=True, SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
def test_production_redirects_http_to_https():
    response = Client().get('/login/')
    assert response.status_code == 301
    assert response['Location'] == 'https://testserver/login/'
