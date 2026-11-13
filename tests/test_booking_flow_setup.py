from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def test_default_setup_is_offline():
    with patch('httpx.Client') as client:
        output = StringIO()
        call_command('setup_booking_flow', stdout=output)
    client.assert_not_called()
    assert 'booking_details.json' in output.getvalue()


def test_setup_uploads_draft_for_validation_without_publishing():
    provider = MagicMock()
    provider.post.return_value.status_code = 200
    provider.post.return_value.json.return_value = {'success': True, 'validation_errors': []}
    provider.get.return_value.status_code = 200
    provider.get.return_value.json.return_value = {'id': '123456', 'status': 'DRAFT', 'validation_errors': []}
    config = {'access_token': 'private-token', 'business_account_id': '987654'}
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value=config), \
            patch('httpx.Client') as client:
        client.return_value.__enter__.return_value = provider
        call_command('setup_booking_flow', '--flow-id', '123456', stdout=StringIO())
    assert len(provider.post.call_args_list) == 1
    assert provider.post.call_args.args[0].endswith('/123456/assets')
    assert not any('/publish' in str(call) for call in provider.mock_calls)


def test_setup_does_not_update_a_published_flow():
    provider = MagicMock()
    provider.get.return_value.status_code = 200
    provider.get.return_value.json.return_value = {'status': 'PUBLISHED'}
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={'access_token': 'secret'}), \
            patch('httpx.Client') as client:
        client.return_value.__enter__.return_value = provider
        with pytest.raises(CommandError, match='draft'):
            call_command('setup_booking_flow', '--flow-id', '123456', stdout=StringIO())
    provider.post.assert_not_called()
