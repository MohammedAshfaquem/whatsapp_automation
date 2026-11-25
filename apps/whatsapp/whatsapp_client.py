import re
import logging
from urllib.parse import urlparse
from typing import Tuple, Optional, Dict, Any
import httpx
from .models import WhatsAppConfig

logger = logging.getLogger(__name__)

class WhatsAppClient:
    """
    Client for the official Meta WhatsApp Cloud API.
    Sends text messages and manages API errors safely without exposing tokens.
    """
    GRAPH_API_VERSION = "v21.0"
    GRAPH_API_BASE_URL = "https://graph.facebook.com"

    @classmethod
    def send_typing_indicator(cls, message_id: str) -> bool:
        """Best-effort read/typing signal. Failure must never interrupt a reply."""
        from django.conf import settings
        if (not getattr(settings, 'WHATSAPP_TYPING_INDICATOR_ENABLED', True)
                or not isinstance(message_id, str) or not message_id.startswith('wamid.') or len(message_id) > 300):
            return False
        config = WhatsAppConfig.get_settings()
        if not (config.get('enabled') and config.get('phone_number_id') and config.get('access_token')):
            return False
        url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{config['phone_number_id']}/messages"
        payload = {'messaging_product': 'whatsapp', 'status': 'read', 'message_id': message_id,
                   'typing_indicator': {'type': 'text'}}
        try:
            with httpx.Client(timeout=httpx.Timeout(2.0, connect=1.0), follow_redirects=False) as client:
                response = client.post(url, headers={'Authorization': f"Bearer {config['access_token']}"}, json=payload)
            if response.status_code != 200:
                return False
            result = response.json()
            return isinstance(result, dict) and result.get('success') is True
        except (httpx.HTTPError, ValueError, TypeError):
            logger.debug('WhatsApp typing indicator unavailable; continuing with reply.')
            return False

    @classmethod
    def download_image(cls, media_id):
        """Fetch a WhatsApp JPEG/PNG in memory; return None when unavailable."""
        token = WhatsAppConfig.get_settings().get('access_token')
        if not token or not re.fullmatch(r'\d+', str(media_id)):
            return None
        headers = {'Authorization': f'Bearer {token}'}
        max_bytes = 5 * 1024 * 1024
        try:
            with httpx.Client(timeout=15, follow_redirects=False) as client:
                metadata_response = client.get(
                    f'{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{media_id}', headers=headers)
                metadata_response.raise_for_status()
                metadata = metadata_response.json()
                mime_type = metadata.get('mime_type')
                url = metadata.get('url', '')
                parsed = urlparse(url)
                # Never forward the access token to a URL outside Meta's media host.
                if (parsed.scheme != 'https' or parsed.hostname != 'lookaside.fbsbx.com'
                        or parsed.port not in (None, 443) or parsed.username or parsed.password
                        or mime_type not in ('image/jpeg', 'image/png')
                        or int(metadata.get('file_size', 0)) > max_bytes):
                    return None
                with client.stream('GET', url, headers=headers) as response:
                    response.raise_for_status()
                    image = bytearray()
                    for chunk in response.iter_bytes():
                        image.extend(chunk)
                        if len(image) > max_bytes:
                            return None
                return (bytes(image), mime_type) if image else None
        except (httpx.HTTPError, ValueError, TypeError):
            # Provider errors can contain signed URLs. Keep them out of logs.
            logger.warning('Unable to download WhatsApp image')
            return None

    @classmethod
    def send_template_message(cls, recipient_phone, name, language='en', parameters=None, tenant=None):
        phone = cls.normalize_phone(recipient_phone)
        template = {'name': name, 'language': {'code': language}}
        if parameters:
            template['components'] = [{'type': 'body', 'parameters': [{'type': 'text', 'text': str(value)} for value in parameters]}]
        return cls._send_payload(phone, {'messaging_product': 'whatsapp', 'to': phone, 'type': 'template', 'template': template}, 'Booking status template', tenant=tenant)

    @classmethod
    def normalize_phone(cls, phone_number: str) -> str:
        """Strip spaces, plus signs, and non-digit characters for Meta API."""
        return re.sub(r'\D', '', phone_number)

    @classmethod
    def send_text_message(
        cls,
        recipient_phone: str,
        message_text: str,
        tenant=None
    ) -> Tuple[bool, Optional[str]]:
        """
        Send text reply to a customer using WhatsApp Cloud API.
        Returns (success: bool, whatsapp_message_id_or_error: str).
        """
        from apps.tenants.platform_auth import check_outbound_whatsapp_pause
        paused, pause_reason = check_outbound_whatsapp_pause(tenant)
        if paused:
            return False, pause_reason
        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        enabled = cfg.get("enabled", False)
        phone_number_id = cfg.get("phone_number_id", "")
        access_token = cfg.get("access_token", "")

        # If WhatsApp is disabled or credentials not set, run in safe simulation mode
        if not enabled or not phone_number_id or not access_token:
            from django.conf import settings
            if not settings.DEBUG:
                return False, 'WhatsApp is disabled or credentials are missing'
            logger.info(
                f"[WhatsApp Client - Simulation Mode] To: {recipient_phone} | "
                f"Message: {message_text[:60]}... (Live WhatsApp credentials disabled/not set)"
            )
            import time
            return True, f"simulated_msg_{int(time.time())}"

        normalized_phone = cls.normalize_phone(recipient_phone)
        url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{phone_number_id}/messages"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": "text",
            "text": {
                "preview_url": False,
                "body": message_text
            }
        }

        return cls._send_payload(normalized_phone, payload, log_summary=f"Text: {message_text[:60]}", tenant=tenant)

    @classmethod
    def upload_media(
        cls,
        file_bytes: bytes,
        mime_type: str,
        filename: str = 'attachment',
        tenant=None,
    ) -> Tuple[bool, Optional[str]]:
        """Upload binary media bytes to Meta Cloud API /media and return (ok, media_id_or_error)."""
        from apps.tenants.platform_auth import check_outbound_whatsapp_pause
        paused, pause_reason = check_outbound_whatsapp_pause(tenant)
        if paused:
            return False, pause_reason

        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        enabled = cfg.get("enabled", False)
        phone_number_id = cfg.get("phone_number_id", "")
        access_token = cfg.get("access_token", "")
        if not enabled or not phone_number_id or not access_token:
            from django.conf import settings
            if not settings.DEBUG:
                return False, 'WhatsApp is disabled or credentials are missing'
            import time
            return True, f"simulated_media_{int(time.time())}"

        url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{phone_number_id}/media"
        try:
            with httpx.Client(timeout=20.0) as client:
                resp = client.post(
                    url,
                    headers={"Authorization": f"Bearer {access_token}"},
                    data={"messaging_product": "whatsapp", "type": mime_type},
                    files={"file": (filename, file_bytes, mime_type)},
                )
            if resp.status_code in (200, 201):
                media_id = resp.json().get("id")
                if media_id:
                    return True, str(media_id)
                return False, "Meta upload returned no media id"
            return False, f"Meta media upload error {resp.status_code}"
        except httpx.TimeoutException:
            return False, "Media upload Request Timeout"
        except Exception as exc:
            logger.error("Unexpected error uploading WhatsApp media: %s", exc)
            return False, str(exc)

    @classmethod
    def send_media_message(
        cls,
        recipient_phone: str,
        media_type: str,
        media_id_or_url: str,
        filename: str = '',
        caption: str = '',
        tenant=None,
    ) -> Tuple[bool, Optional[str]]:
        """Send an image, document, audio, or video message via Meta Cloud API."""
        if media_type not in ('image', 'document', 'audio', 'video'):
            return False, f"Unsupported WhatsApp media type: {media_type}"
        normalized_phone = cls.normalize_phone(recipient_phone)
        is_url = str(media_id_or_url).startswith(('http://', 'https://'))
        media_obj: Dict[str, Any] = {'link': media_id_or_url} if is_url else {'id': str(media_id_or_url)}
        if caption and media_type in ('image', 'document', 'video'):
            media_obj['caption'] = caption[:1024]
        if filename and media_type == 'document':
            media_obj['filename'] = filename[:200]
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": media_type,
            media_type: media_obj,
        }
        return cls._send_payload(normalized_phone, payload, log_summary=f"Media ({media_type}): {filename}", tenant=tenant)

    @classmethod
    def send_button_message(
        cls,
        recipient_phone: str,
        body_text: str,
        buttons: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        tenant=None
    ) -> Tuple[bool, Optional[str]]:
        """
        Send interactive reply buttons (max 3 buttons) via Meta WhatsApp Cloud API.
        buttons: [{"id": "btn_1", "title": "Button Title"}, ...]
        """
        normalized_phone = cls.normalize_phone(recipient_phone)
        formatted_buttons = []
        for btn in buttons[:3]:
            formatted_buttons.append({
                "type": "reply",
                "reply": {
                    "id": str(btn.get("id", ""))[:256],
                    "title": str(btn.get("title", ""))[:20]
                }
            })

        interactive_data: Dict[str, Any] = {
            "type": "button",
            "body": {
                "text": body_text[:1024]
            },
            "action": {
                "buttons": formatted_buttons
            }
        }

        if header_text:
            interactive_data["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive_data["footer"] = {"text": footer_text[:60]}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": "interactive",
            "interactive": interactive_data
        }

        button_titles = [b.get("title") for b in buttons[:3]]
        return cls._send_payload(
            normalized_phone,
            payload,
            log_summary=f"Buttons [{', '.join(button_titles)}]: {body_text[:50]}",
            tenant=tenant
        )

    @classmethod
    def send_list_message(
        cls,
        recipient_phone: str,
        body_text: str,
        button_label: str,
        sections: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        tenant=None
    ) -> Tuple[bool, Optional[str]]:
        """
        Send interactive list message (max 10 rows total) via Meta WhatsApp Cloud API.
        sections: [{"title": "Section Title", "rows": [{"id": "r1", "title": "Row Title", "description": "..."}]}]
        """
        normalized_phone = cls.normalize_phone(recipient_phone)
        formatted_sections = []
        total_rows = 0

        for sec in sections:
            sec_rows = []
            for r in sec.get("rows", []):
                if total_rows >= 10:
                    break
                row_item = {
                    "id": str(r.get("id", ""))[:200],
                    "title": str(r.get("title", ""))[:24]
                }
                desc = r.get("description")
                if desc:
                    row_item["description"] = str(desc)[:72]
                sec_rows.append(row_item)
                total_rows += 1

            if sec_rows:
                formatted_sections.append({
                    "title": str(sec.get("title", "Services"))[:24],
                    "rows": sec_rows
                })

        interactive_data: Dict[str, Any] = {
            "type": "list",
            "body": {
                "text": body_text[:4096]
            },
            "action": {
                "button": button_label[:20] if button_label else "Select Option",
                "sections": formatted_sections
            }
        }

        if header_text:
            interactive_data["header"] = {"type": "text", "text": header_text[:60]}
        if footer_text:
            interactive_data["footer"] = {"text": footer_text[:60]}

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": normalized_phone,
            "type": "interactive",
            "interactive": interactive_data
        }

        return cls._send_payload(
            normalized_phone,
            payload,
            log_summary=f"List ({total_rows} rows): {body_text[:50]}",
            tenant=tenant
        )

    @classmethod
    def send_flow_message(cls, recipient_phone, body_text, flow_id, flow_token, screen, data, tenant=None):
        """Open a published, static Flow at the current booking step."""
        phone = cls.normalize_phone(recipient_phone)
        payload = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': phone,
            'type': 'interactive', 'interactive': {'type': 'flow', 'body': {'text': body_text[:4096]},
            'action': {'name': 'flow', 'parameters': {'flow_message_version': '3', 'flow_id': flow_id,
                'flow_token': flow_token, 'flow_cta': 'Enter address' if screen == 'ADDRESS' else 'Choose date',
                'mode': 'published', 'flow_action': 'navigate',
                'flow_action_payload': {'screen': screen, 'data': data}}}}}
        return cls._send_payload(phone, payload, log_summary=f'Booking form: {screen}', tenant=tenant)

    @classmethod
    def send_interactive_options(
        cls,
        recipient_phone: str,
        body_text: str,
        options: list,
        button_label: str = "View Services",
        section_title: str = "Available Services",
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None,
        tenant=None
    ) -> Tuple[bool, Optional[str]]:
        """
        Smart dispatcher for options:
        - 1 to 3 options: sends interactive quick reply buttons.
        - > 3 options: sends interactive list message (menu picker up to 10 rows).
        """
        if not options:
            return cls.send_text_message(recipient_phone, body_text, tenant=tenant)

        if len(options) <= 3:
            return cls.send_button_message(
                recipient_phone=recipient_phone,
                body_text=body_text,
                buttons=options,
                header_text=header_text,
                footer_text=footer_text,
                tenant=tenant
            )
        else:
            sections = [{
                "title": section_title,
                "rows": options
            }]
            return cls.send_list_message(
                recipient_phone=recipient_phone,
                body_text=body_text,
                button_label=button_label,
                sections=sections,
                header_text=header_text,
                footer_text=footer_text,
                tenant=tenant
            )

    @classmethod
    def _send_payload(
        cls,
        normalized_phone: str,
        payload: Dict[str, Any],
        log_summary: str = "",
        tenant=None
    ) -> Tuple[bool, Optional[str]]:
        """Internal helper to dispatch message payload to Meta Graph API or simulate."""
        if tenant and not tenant.is_active:
            return False, "Tenant is suspended"
        from apps.tenants.platform_auth import check_outbound_whatsapp_pause
        paused, pause_reason = check_outbound_whatsapp_pause(tenant)
        if paused:
            return False, pause_reason

        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        enabled = cfg.get("enabled", False)
        phone_number_id = cfg.get("phone_number_id", "")
        access_token = cfg.get("access_token", "")

        if not enabled or not phone_number_id or not access_token:
            from django.conf import settings
            if not settings.DEBUG:
                return False, 'WhatsApp is disabled or credentials are missing'
            logger.info(
                f"[WhatsApp Client - Simulation Mode] To: {normalized_phone} | "
                f"{log_summary} (Live WhatsApp credentials disabled/not set)"
            )
            import time
            return True, f"simulated_msg_{int(time.time())}"

        url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.post(url, headers=headers, json=payload)

            if response.status_code in (200, 201):
                data = response.json()
                msg_id = data.get("messages", [{}])[0].get("id", "sent_unknown_id")
                logger.info(f"WhatsApp message sent successfully to {normalized_phone} (ID: {msg_id})")
                return True, msg_id
            else:
                err_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else response.text
                logger.error(
                    f"Meta WhatsApp Cloud API error: Status {response.status_code} | "
                    f"Recipient: {normalized_phone} | Details: {err_data}"
                )
                return False, f"API Error {response.status_code}"
        except httpx.TimeoutException:
            logger.error(f"Timeout while sending WhatsApp message to {normalized_phone}")
            return False, "Request Timeout"
        except Exception as e:
            logger.error(f"Unexpected error sending WhatsApp message: {e}", exc_info=True)
            return False, str(e)

    @classmethod
    def get_business_profile(cls, tenant=None) -> Dict[str, Any]:
        """
        Fetch official WhatsApp Business Profile and phone number registration metadata from Meta.
        """
        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        phone_id = cfg.get("phone_number_id")
        access_token = cfg.get("access_token")
        enabled = cfg.get("enabled", False)

        if not enabled or not phone_id or not access_token:
            return {'configured': False, 'live': False}

        headers = {"Authorization": f"Bearer {access_token}"}
        result: Dict[str, Any] = {'configured': True, 'live': False, 'phone_number_id': phone_id}

        try:
            with httpx.Client(timeout=10.0) as client:
                # 1. Profile fields
                profile_url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{phone_id}/whatsapp_business_profile"
                params = {'fields': 'about,address,description,email,profile_picture_url,websites,vertical'}
                resp = client.get(profile_url, headers=headers, params=params)
                if resp.status_code != 200:
                    return {'configured': True, 'live': False, 'error': 'Meta profile request failed'}
                if resp.status_code == 200:
                    data = resp.json().get('data', [{}])
                    if data:
                        profile_info = data[0]
                        result.update({
                            'about': profile_info.get('about', ''),
                            'address': profile_info.get('address', ''),
                            'description': profile_info.get('description', ''),
                            'email': profile_info.get('email', ''),
                            'websites': profile_info.get('websites', []),
                            'vertical': profile_info.get('vertical', ''),
                            'profile_picture_url': profile_info.get('profile_picture_url', ''),
                        })

                # 2. Number metadata (verified name, quality rating, tier)
                number_url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{phone_id}"
                num_params = {'fields': 'verified_name,display_phone_number,quality_rating,code_verification_status,messaging_limit_tier'}
                num_resp = client.get(number_url, headers=headers, params=num_params)
                if num_resp.status_code != 200:
                    return {'configured': True, 'live': False, 'error': 'Meta number metadata request failed'}
                result['live'] = True
                if num_resp.status_code == 200:
                    num_data = num_resp.json()
                    result.update({
                        'verified_name': num_data.get('verified_name', ''),
                        'display_phone_number': num_data.get('display_phone_number', ''),
                        'quality_rating': num_data.get('quality_rating') or 'UNKNOWN',
                        'code_verification_status': num_data.get('code_verification_status') or 'UNKNOWN',
                        'messaging_limit_tier': num_data.get('messaging_limit_tier') or 'UNKNOWN',
                    })
        except Exception as e:
            logger.warning(f"Error fetching WhatsApp business profile from Meta: {e}")
            result['live'] = False
            result['error'] = 'Could not reach Meta Graph API'

        return result

    @classmethod
    def create_template(cls, template, examples):
        """Submit body-text templates; never simulate an approval or retry an uncertain POST."""
        cfg = WhatsAppConfig.get_settings(tenant=template.tenant)
        if not all((cfg.get('enabled'), cfg.get('business_account_id'), cfg.get('access_token'))):
            return False, {}, 'Meta account is not configured', False
        component = {'type': 'BODY', 'text': template.body_text}
        if examples:
            component['example'] = {'body_text': [examples]}
        payload = {'name': template.name, 'language': template.language, 'category': template.category, 'components': [component]}
        try:
            with httpx.Client(timeout=15.0, follow_redirects=False) as client:
                response = client.post(f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{cfg['business_account_id']}/message_templates",
                    headers={'Authorization': f"Bearer {cfg['access_token']}"}, json=payload)
            data = response.json()
            if response.status_code in (200, 201) and isinstance(data, dict) and data.get('id'):
                return True, data, '', False
            code = data.get('error', {}).get('code', 'UNKNOWN') if isinstance(data, dict) else 'UNKNOWN'
            return False, {}, f'Meta rejected submission (HTTP {response.status_code}, code {code}). Check WhatsApp Manager.', response.status_code >= 500
        except (httpx.HTTPError, ValueError, TypeError):
            return False, {}, 'Submission outcome uncertain. Sync Meta templates before attempting another submission.', True

    @classmethod
    def fetch_templates(cls, tenant=None) -> Tuple[bool, list, str]:
        """Fetch every page, returning no partial results on any failure."""
        from .template_sync import validate_snapshot
        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        waba_id, token = cfg.get('business_account_id'), cfg.get('access_token')
        if not cfg.get('enabled') or not waba_id or not token:
            return False, [], 'Meta WhatsApp credentials or Business Account ID not configured'
        url = f'{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{waba_id}/message_templates'
        headers = {'Authorization': f'Bearer {token}'}
        params = {'fields': 'id,name,status,category,language,components', 'limit': '100'}
        collected, visited = [], set()
        try:
            with httpx.Client(timeout=10.0, follow_redirects=False) as client:
                while url:
                    parsed = urlparse(url)
                    if (parsed.scheme != 'https' or parsed.hostname != 'graph.facebook.com'
                            or parsed.port not in (None, 443) or parsed.username or parsed.password
                            or parsed.path != f'/{cls.GRAPH_API_VERSION}/{waba_id}/message_templates'
                            or url in visited or len(visited) >= 1000):
                        raise ValueError('Invalid pagination')
                    visited.add(url)
                    response = client.get(url, headers=headers, params=params)
                    if response.status_code != 200:
                        return False, [], f'Meta template fetch failed (HTTP {response.status_code})'
                    page = response.json()
                    if not isinstance(page, dict) or 'error' in page or not isinstance(page.get('data'), list):
                        raise ValueError('Invalid template page')
                    collected.extend(page['data'])
                    paging = page.get('paging', {})
                    if not isinstance(paging, dict):
                        raise ValueError('Invalid pagination')
                    url = paging.get('next')
                    if url is not None and (not isinstance(url, str) or not url):
                        raise ValueError('Invalid pagination')
                    params = None
            validate_snapshot(collected)
            return True, collected, ''
        except (httpx.HTTPError, ValueError, TypeError):
            logger.warning('Unable to fetch complete Meta template snapshot')
            return False, [], 'Unable to fetch complete Meta template snapshot'

    @classmethod
    def update_business_profile(cls, profile_fields: Dict[str, Any], tenant=None) -> Tuple[bool, str]:
        """
        Update official WhatsApp Business Profile on Meta Cloud API.
        """
        cfg = WhatsAppConfig.get_settings(tenant=tenant)
        phone_id = cfg.get("phone_number_id")
        access_token = cfg.get("access_token")
        enabled = cfg.get("enabled", False)

        if not enabled or not phone_id or not access_token:
            from django.conf import settings
            if settings.DEBUG:
                return True, "Simulated profile update"
            return False, "WhatsApp is disabled or credentials are missing"

        url = f"{cls.GRAPH_API_BASE_URL}/{cls.GRAPH_API_VERSION}/{phone_id}/whatsapp_business_profile"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload: Dict[str, Any] = {"messaging_product": "whatsapp"}
        for k in ('about', 'address', 'description', 'email', 'websites', 'vertical'):
            if k in profile_fields:
                payload[k] = profile_fields[k]

        try:
            with httpx.Client(timeout=10.0) as client:
                resp = client.post(url, headers=headers, json=payload)
            if resp.status_code == 200 and resp.json().get('success') is True:
                return True, "Profile updated successfully on Meta"
            err = resp.json().get('error', {}).get('message', f'HTTP {resp.status_code}')
            return False, err
        except Exception as e:
            logger.error(f"Error updating WhatsApp business profile: {e}")
            return False, str(e)


