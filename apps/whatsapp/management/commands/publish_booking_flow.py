"""Explicit deployment step: publish a validated Flow, then optionally enable it locally."""
import re
import json

import httpx
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.whatsapp.models import WhatsAppConfig
from apps.whatsapp.whatsapp_client import WhatsAppClient
from .setup_booking_flow import response_data


class Command(BaseCommand):
    help = 'Publish a validated Meta Flow (irreversible). --enable writes its ID to the local .env after verification.'

    def add_arguments(self, parser):
        parser.add_argument('--flow-id', required=True)
        parser.add_argument('--enable', action='store_true')
        parser.add_argument('--inspect', action='store_true', help='Read status and health only; never publish or enable.')

    def handle(self, *args, **options):
        flow_id = options['flow_id']
        if not re.fullmatch(r'\d+', flow_id):
            raise CommandError('Flow ID must contain digits only.')
        config = WhatsAppConfig.get_settings()
        if not config.get('access_token'):
            raise CommandError('Configure the Meta access token before publication.')
        url = f'{WhatsAppClient.GRAPH_API_BASE_URL}/{WhatsAppClient.GRAPH_API_VERSION}/{flow_id}'
        try:
            with httpx.Client(timeout=30, headers={'Authorization': f"Bearer {config['access_token']}"},
                              follow_redirects=False) as client:
                current = response_data(client.get(url, params={'fields': 'id,status,validation_errors,health_status'}))
                if options['inspect']:
                    self.stdout.write(json.dumps(current, ensure_ascii=False, indent=2))
                    return
                status = current.get('status')
                if current.get('validation_errors'):
                    raise CommandError('Meta reports validation errors. Publication was not attempted.')
                if status == 'DRAFT':
                    result = response_data(client.post(f'{url}/publish'))
                    if not result.get('success'):
                        raise CommandError('Meta did not confirm publication. Check Flow status before retrying.')
                elif status != 'PUBLISHED':
                    raise CommandError(f'This Flow cannot be published from status {status}.')
                verified = response_data(client.get(url, params={'fields': 'id,status,health_status'}))
        except httpx.HTTPError as error:
            raise CommandError(f'Meta request could not complete ({type(error).__name__}). Check Flow status before retrying.') from None
        if verified.get('status') != 'PUBLISHED':
            raise CommandError('Meta has not verified PUBLISHED status. The server setting was not changed.')
        self.stdout.write(f'Flow {flow_id}: PUBLISHED (verified by Meta).')
        if options['enable']:
            health = verified.get('health_status', {}).get('can_send_message')
            if health not in ('AVAILABLE', 'LIMITED'):
                raise CommandError(f'Meta messaging health is {health or "unknown"}. Flow published, but not enabled locally.')
            from dotenv import set_key
            saved = set_key(str(settings.BASE_DIR / '.env'), 'WHATSAPP_BOOKING_FLOW_ID', flow_id)
            if not saved[0]:
                raise CommandError('Flow is published, but the local setting could not be saved.')
            self.stdout.write('Published Flow ID enabled in local .env. Reload the Django server to apply it.')
