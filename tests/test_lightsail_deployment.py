import subprocess

import pytest

from deploy import lightsail


def test_init_protects_existing_credentials(tmp_path, monkeypatch):
    env = tmp_path / '.env.lightsail'
    monkeypatch.setattr(lightsail, 'ENV', env)
    lightsail.initialize('wapp.neorizsolutions.com')
    original = env.read_text()
    values = dict(line.split('=', 1) for line in original.splitlines())
    assert values['APP_DOMAIN'] == 'wapp.neorizsolutions.com'
    assert len(values['DJANGO_SECRET_KEY']) >= 50
    assert len(values['POSTGRES_PASSWORD']) == 64
    assert values['WHATSAPP_ENABLED'] == 'False'
    with pytest.raises(FileExistsError):
        lightsail.initialize('wapp.neorizsolutions.com')
    assert env.read_text() == original


@pytest.mark.parametrize('domain', ['https://example.com', 'example.com/path', 'example.com\nKEY=value', '-bad.example.com'])
def test_init_rejects_invalid_domain(tmp_path, monkeypatch, domain):
    monkeypatch.setattr(lightsail, 'ENV', tmp_path / '.env.lightsail')
    with pytest.raises(ValueError):
        lightsail.initialize(domain)
    assert not lightsail.ENV.exists()


def test_migration_failure_keeps_traffic_stopped(monkeypatch):
    calls = []

    def compose(*args, **kwargs):
        calls.append(args)
        if 'migrate' in args:
            raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(lightsail, 'compose', compose)
    monkeypatch.setattr(lightsail, 'backup', lambda: calls.append(('backup',)))
    with pytest.raises(subprocess.CalledProcessError):
        lightsail.deploy()
    stop = calls.index(('stop', 'proxy', 'retry', 'web'))
    assert calls.index(('backup',)) < stop
    assert calls[stop + 1] == ('run', '--rm', 'web', 'python', 'manage.py', 'migrate', '--noinput')
    assert not any(call[:3] == ('up', '-d', '--wait') and 'proxy' in call for call in calls)


def test_failed_backup_does_not_leave_partial_archive(tmp_path, monkeypatch):
    monkeypatch.setattr(lightsail, 'ROOT', tmp_path)

    def compose(*args, **kwargs):
        kwargs['stdout'].write(b'incomplete')
        raise subprocess.CalledProcessError(1, args)

    monkeypatch.setattr(lightsail, 'compose', compose)
    with pytest.raises(subprocess.CalledProcessError):
        lightsail.backup()
    assert list((tmp_path / '.backups').iterdir()) == []


def test_backend_only_release_defers_public_proxy(monkeypatch):
    calls = []
    monkeypatch.setattr(lightsail, 'compose', lambda *args, **kwargs: calls.append(args))
    monkeypatch.setattr(lightsail, 'backup', lambda: None)
    lightsail.deploy(backend_only=True)
    assert calls[-1] == ('up', '-d', '--wait', '--wait-timeout', '240', 'web', 'retry')
