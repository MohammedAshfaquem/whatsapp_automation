"""Official Meta resumable upload for business profile pictures. No simulation."""
import re
import httpx
from django.conf import settings
from .models import WhatsAppConfig
from .whatsapp_client import WhatsAppClient


class ProfileMediaError(Exception):
    def __init__(self, message, status=502):
        super().__init__(message)
        self.status = status


def upload_profile_picture(tenant, data, mime_type):
    cfg = WhatsAppConfig.get_settings(tenant=tenant)
    app_id = str(cfg.get('app_id') or getattr(settings, 'META_APP_ID', '')).strip()
    if not app_id or not app_id.isdigit():
        raise ProfileMediaError('Meta app ID is not configured for profile photo uploads.', 503)
    phone_id = str(cfg.get('phone_number_id') or '')
    if not (cfg.get('enabled') and phone_id.isdigit() and cfg.get('access_token')):
        raise ProfileMediaError('Connect an active WhatsApp account before uploading a profile photo.', 400)
    base = f'{WhatsAppClient.GRAPH_API_BASE_URL}/{WhatsAppClient.GRAPH_API_VERSION}'
    token = cfg['access_token']
    try:
        with httpx.Client(timeout=httpx.Timeout(30, connect=5), follow_redirects=False) as client:
            session = client.post(f'{base}/{app_id}/uploads', headers={'Authorization': f'Bearer {token}'}, params={'file_length':len(data), 'file_type':mime_type, 'file_name':'profile.png' if mime_type == 'image/png' else 'profile.jpg'})
            if session.status_code != 200:
                raise ProfileMediaError('Meta rejected the profile photo upload session.')
            upload_id = session.json().get('id', '')
            # Preserve Meta's signed upload ID, but never permit a different host/path.
            if not isinstance(upload_id, str) or not re.fullmatch(r'upload:[A-Za-z0-9_:.=+%-]+(?:\?sig=[A-Za-z0-9_:.=+%&-]+)?', upload_id):
                raise ProfileMediaError('Meta returned an invalid upload session.')
            uploaded = client.post(f'{base}/{upload_id}', headers={'Authorization': f'OAuth {token}', 'file_offset':'0', 'Content-Type':mime_type}, content=data)
            if uploaded.status_code != 200:
                raise ProfileMediaError('Meta rejected the profile photo data.')
            handle = uploaded.json().get('h')
            if not isinstance(handle, str) or not handle:
                raise ProfileMediaError('Meta did not return a profile photo handle.')
            result = client.post(f'{base}/{phone_id}/whatsapp_business_profile', headers={'Authorization':f'Bearer {token}'}, json={'messaging_product':'whatsapp', 'profile_picture_handle':handle})
            if result.status_code != 200 or result.json().get('success') is not True:
                raise ProfileMediaError('Meta rejected the profile photo update.')
    except (httpx.HTTPError, ValueError, TypeError, AttributeError):
        # Provider exceptions may contain tokens or signed session identifiers.
        raise ProfileMediaError('Meta profile photo upload failed. Please retry.') from None
