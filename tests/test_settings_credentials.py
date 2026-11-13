"""A terminal's stale key must not hide a developer's explicit local key change."""
import runpy
from pathlib import Path

import pytest


@pytest.mark.parametrize('debug,file_key,expected', [
    ('True', 'local-new-key', 'local-new-key'),
    ('False', 'local-new-key', 'deployment-key'),
    ('True', '', ''),
    ('True', None, 'deployment-key'),
])
def test_local_debug_key_precedence_preserves_production_environment(tmp_path, monkeypatch, debug, file_key, expected):
    source = Path(__file__).resolve().parents[1] / 'config' / 'settings.py'
    target = tmp_path / 'config' / 'settings.py'
    target.parent.mkdir()
    target.write_text(source.read_text(encoding='utf-8'), encoding='utf-8')
    values = f'DJANGO_DEBUG={debug}\nGEMINI_CHAT_MODEL=local-model\n'
    if file_key is not None:
        values += f'GEMINI_API_KEY={file_key}\n'
    (tmp_path / '.env').write_text(values, encoding='utf-8')
    monkeypatch.setenv('DJANGO_DEBUG', debug)
    monkeypatch.setenv('GEMINI_API_KEY', 'deployment-key')
    monkeypatch.setenv('GEMINI_CHAT_MODEL', 'deployment-model')
    namespace = runpy.run_path(str(target))
    assert namespace['GEMINI_API_KEY'] == expected
    assert namespace['GEMINI_CHAT_MODEL'] == ('local-model' if debug == 'True' else 'deployment-model')
