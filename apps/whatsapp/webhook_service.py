import hmac
import hashlib
import logging
from django.conf import settings
from typing import Tuple, Dict, Any, Optional
from .models import WhatsAppConfig, WhatsAppWebhookLog
from .whatsapp_client import WhatsAppClient
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import ChannelChoice

logger = logging.getLogger(__name__)

class WebhookService:
    """
    Handles Meta WhatsApp Cloud API webhook challenge verification,
    HMAC SHA-256 signature security, and incoming message parsing & routing.
    """

    @classmethod
    def verify_challenge(
        cls,
        hub_mode: Optional[str],
        hub_verify_token: Optional[str],
        hub_challenge: Optional[str]
    ) -> Tuple[bool, str]:
        """
        Verify the GET challenge sent by Meta when registering the webhook URL.
        """
        cfg = WhatsAppConfig.get_settings()
        expected_token = cfg.get("verify_token", "")

        if hub_mode == "subscribe" and hub_verify_token and expected_token and hub_verify_token == expected_token:
            logger.info("WhatsApp webhook challenge verification succeeded.")
            return True, hub_challenge or ""

        logger.warning('WhatsApp webhook verification failed.')
        return False, "Verification failed"

    @classmethod
    def verify_signature(cls, raw_body: bytes, signature_header: Optional[str]) -> bool:
        """
        Verify the X-Hub-Signature-256 header using the Meta App Secret.
        """
        cfg = WhatsAppConfig.get_settings()
        app_secret = cfg.get("app_secret", "")

        if not app_secret:
            return bool(settings.DEBUG and not cfg.get('enabled'))

        if not signature_header or not signature_header.startswith("sha256="):
            logger.warning("Missing or malformed X-Hub-Signature-256 header")
            return False

        received_hash = signature_header[7:]
        expected_hash = hmac.new(
            key=app_secret.encode('utf-8'),
            msg=raw_body,
            digestmod=hashlib.sha256
        ).hexdigest()

        is_valid = hmac.compare_digest(received_hash, expected_hash)
        if not is_valid:
            logger.error("X-Hub-Signature-256 validation failed. Payload rejected.")
        return is_valid

    @classmethod
    def process_incoming_payload(cls, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Parse and process inbound Meta WhatsApp webhook event idempotently.
        """
        from .events import process_events
        return process_events(payload)
