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
    def send_template_message(cls, recipient_phone, name, language='en', parameters=None):
        phone = cls.normalize_phone(recipient_phone)
        template = {'name': name, 'language': {'code': language}}
        if parameters:
            template['components'] = [{'type': 'body', 'parameters': [{'type': 'text', 'text': str(value)} for value in parameters]}]
        return cls._send_payload(phone, {'messaging_product': 'whatsapp', 'to': phone, 'type': 'template', 'template': template}, 'Booking status template')

    @classmethod
    def normalize_phone(cls, phone_number: str) -> str:
        """Strip spaces, plus signs, and non-digit characters for Meta API."""
        return re.sub(r'\D', '', phone_number)

    @classmethod
    def send_text_message(
        cls,
        recipient_phone: str,
        message_text: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Send text reply to a customer using WhatsApp Cloud API.
        Returns (success: bool, whatsapp_message_id_or_error: str).
        """
        cfg = WhatsAppConfig.get_settings()
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

        return cls._send_payload(normalized_phone, payload, log_summary=f"Text: {message_text[:60]}")

    @classmethod
    def send_button_message(
        cls,
        recipient_phone: str,
        body_text: str,
        buttons: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
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
            log_summary=f"Buttons [{', '.join(button_titles)}]: {body_text[:50]}"
        )

    @classmethod
    def send_list_message(
        cls,
        recipient_phone: str,
        body_text: str,
        button_label: str,
        sections: list,
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
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
            log_summary=f"List ({total_rows} rows): {body_text[:50]}"
        )

    @classmethod
    def send_flow_message(cls, recipient_phone, body_text, flow_id, flow_token, screen, data):
        """Open a published, static Flow at the current booking step."""
        phone = cls.normalize_phone(recipient_phone)
        payload = {'messaging_product': 'whatsapp', 'recipient_type': 'individual', 'to': phone,
            'type': 'interactive', 'interactive': {'type': 'flow', 'body': {'text': body_text[:4096]},
            'action': {'name': 'flow', 'parameters': {'flow_message_version': '3', 'flow_id': flow_id,
                'flow_token': flow_token, 'flow_cta': 'Enter address' if screen == 'ADDRESS' else 'Choose date',
                'mode': 'published', 'flow_action': 'navigate',
                'flow_action_payload': {'screen': screen, 'data': data}}}}}
        return cls._send_payload(phone, payload, log_summary=f'Booking form: {screen}')

    @classmethod
    def send_interactive_options(
        cls,
        recipient_phone: str,
        body_text: str,
        options: list,
        button_label: str = "View Services",
        section_title: str = "Available Services",
        header_text: Optional[str] = None,
        footer_text: Optional[str] = None
    ) -> Tuple[bool, Optional[str]]:
        """
        Smart dispatcher for options:
        - 1 to 3 options: sends interactive quick reply buttons.
        - > 3 options: sends interactive list message (menu picker up to 10 rows).
        """
        if not options:
            return cls.send_text_message(recipient_phone, body_text)

        if len(options) <= 3:
            return cls.send_button_message(
                recipient_phone=recipient_phone,
                body_text=body_text,
                buttons=options,
                header_text=header_text,
                footer_text=footer_text
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
                footer_text=footer_text
            )

    @classmethod
    def _send_payload(
        cls,
        normalized_phone: str,
        payload: Dict[str, Any],
        log_summary: str = ""
    ) -> Tuple[bool, Optional[str]]:
        """Internal helper to dispatch message payload to Meta Graph API or simulate."""
        cfg = WhatsAppConfig.get_settings()
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

