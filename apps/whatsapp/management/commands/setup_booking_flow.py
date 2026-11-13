"""Upload a static form to a Meta draft for validation; never publish or enable it."""
import json
import re
from pathlib import Path

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.whatsapp.models import WhatsAppConfig
from apps.whatsapp.whatsapp_client import WhatsAppClient


def response_data(response):
    try:
        data = response.json()
    except ValueError:
        raise CommandError(f'Meta returned a non-JSON response (HTTP {response.status_code}).') from None
    if not 200 <= response.status_code < 300:
        code = data.get('error', {}).get('code', 'unknown')
        raise CommandError(f'Meta rejected the request (HTTP {response.status_code}, code {code}). Check account permissions and credentials.')
    return data


class Command(BaseCommand):
    help = 'Show the native form file, or create/update a Meta draft and inspect validation. Never publishes.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--create', action='store_true', help='Create a new draft in the configured WABA.')
        group.add_argument('--flow-id', help='Upload to an existing draft Flow ID.')

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / 'apps' / 'whatsapp' / 'flows' / 'booking_details.json'
        asset = path.read_bytes()
        json.loads(asset)
        if not options['create'] and not options['flow_id']:
            self.stdout.write(str(path))
            self.stdout.write('Offline only. Import this JSON in WhatsApp Manager, or use --create / --flow-id to upload a draft.')
            return
        config = WhatsAppConfig.get_settings()
        if not config.get('access_token'):
            raise CommandError('Configure the Meta access token before uploading a Flow.')
        flow_id = options['flow_id']
        if flow_id and not re.fullmatch(r'\d+', flow_id):
            raise CommandError('Flow ID must contain digits only.')
        waba = config.get('business_account_id', '')
        if options['create'] and not re.fullmatch(r'\d+', waba):
            raise CommandError('Configure the WhatsApp Business Account ID before creating a draft.')
        base = f'{WhatsAppClient.GRAPH_API_BASE_URL}/{WhatsAppClient.GRAPH_API_VERSION}'
        try:
            with httpx.Client(timeout=30, headers={'Authorization': f"Bearer {config['access_token']}"},
                              follow_redirects=False) as client:
                if options['create']:
                    result = response_data(client.post(f'{base}/{waba}/flows', data={
                        'name': 'AC service address and visit preference', 'categories': '["APPOINTMENT_BOOKING"]'}))
                    flow_id = str(result.get('id', ''))
                    if not re.fullmatch(r'\d+', flow_id):
                        raise CommandError('Meta did not return a valid Flow ID. Check WhatsApp Manager before creating another.')
                    self.stdout.write(f'Created draft Flow ID: {flow_id}')
                existing = response_data(client.get(f'{base}/{flow_id}', params={'fields': 'id,status'}))
                if existing.get('status') != 'DRAFT':
                    raise CommandError('Only a draft Flow can be updated. Create a new draft for changes.')
                uploaded = response_data(client.post(f'{base}/{flow_id}/assets',
                    data={'name': 'flow.json', 'asset_type': 'FLOW_JSON'},
                    files={'file': ('booking_details.json', asset, 'application/json')}))
                errors = uploaded.get('validation_errors', [])
                if errors:
                    self.stdout.write(json.dumps(errors, ensure_ascii=False, indent=2))
                    raise CommandError(f'Meta reported validation errors for draft {flow_id}. It was not published.')
                metadata = response_data(client.get(f'{base}/{flow_id}', params={'fields': 'id,status,validation_errors'}))
                if metadata.get('validation_errors'):
                    self.stdout.write(json.dumps(metadata['validation_errors'], indent=2))
                    raise CommandError(f'Draft {flow_id} still has validation errors.')
        except httpx.HTTPError as error:
            raise CommandError(f'Meta request could not complete ({type(error).__name__}). If creating, check WhatsApp Manager before retrying.') from None
        self.stdout.write(f'Draft {flow_id}: JSON uploaded; no validation errors reported. Not published or enabled.')
        self.stdout.write('Preview ADDRESS and SCHEDULE in WhatsApp Manager. After publishing, set ' 
                          f'WHATSAPP_BOOKING_FLOW_ID={flow_id} on the server and restart it.')
