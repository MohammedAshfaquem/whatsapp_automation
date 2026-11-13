from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def meta_response(data, status=200):
    response = MagicMock(status_code=status)
    response.json.return_value = data
    return response


def test_publish_enables_only_after_meta_confirms_published():
    provider = MagicMock()
    provider.get.side_effect = [meta_response({'status': 'DRAFT', 'validation_errors': []}),
                               meta_response({'id': '123456', 'status': 'PUBLISHED',
                                              'health_status': {'can_send_message': 'AVAILABLE'}})]
    provider.post.return_value = meta_response({'success': True})
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={'access_token': 'secret'}), \
            patch('httpx.Client') as client, patch('dotenv.set_key') as set_key:
        client.return_value.__enter__.return_value = provider
        call_command('publish_booking_flow', '--flow-id', '123456', '--enable', stdout=StringIO())
    assert provider.post.call_args.args[0].endswith('/123456/publish')
    assert set_key.call_args.args[1:] == ('WHATSAPP_BOOKING_FLOW_ID', '123456')


@pytest.mark.parametrize('initial,final,publish_status', [
    ({'status': 'DRAFT', 'validation_errors': [{'error': 'invalid'}]}, None, 200),
    ({'status': 'DEPRECATED'}, None, 200),
    ({'status': 'DRAFT', 'validation_errors': []}, {'status': 'DRAFT'}, 200),
    ({'status': 'DRAFT', 'validation_errors': []}, None, 400),
    ({'status': 'PUBLISHED'}, {'status': 'PUBLISHED', 'health_status': {'can_send_message': 'BLOCKED'}}, 200),
])
def test_unsuccessful_or_blocked_publication_never_enables(initial, final, publish_status):
    provider = MagicMock()
    provider.get.side_effect = [meta_response(initial), meta_response(final)]
    provider.post.return_value = meta_response({'error': {'code': 100}} if publish_status == 400 else {'success': True}, publish_status)
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={'access_token': 'secret'}), \
            patch('httpx.Client') as client, patch('dotenv.set_key') as set_key:
        client.return_value.__enter__.return_value = provider
        with pytest.raises(CommandError):
            call_command('publish_booking_flow', '--flow-id', '123456', '--enable', stdout=StringIO())
    set_key.assert_not_called()


def test_published_flow_is_not_published_again():
    provider = MagicMock()
    provider.get.return_value = meta_response({'status': 'PUBLISHED'})
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={'access_token': 'secret'}), \
            patch('httpx.Client') as client:
        client.return_value.__enter__.return_value = provider
        call_command('publish_booking_flow', '--flow-id', '123456', stdout=StringIO())
    provider.post.assert_not_called()


def test_inspection_is_read_only_even_for_a_draft():
    provider = MagicMock()
    provider.get.return_value = meta_response({'status': 'DRAFT', 'health_status': {'can_send_message': 'BLOCKED'}})
    with patch('apps.whatsapp.models.WhatsAppConfig.get_settings', return_value={'access_token': 'secret'}), \
            patch('httpx.Client') as client, patch('dotenv.set_key') as set_key:
        client.return_value.__enter__.return_value = provider
        call_command('publish_booking_flow', '--flow-id', '123456', '--inspect', stdout=StringIO())
    provider.post.assert_not_called()
    set_key.assert_not_called()
