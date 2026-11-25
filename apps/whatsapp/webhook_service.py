import hmac
import hashlib
import logging
from django.conf import settings
from typing import Tuple, Dict, Any, Optional
from .models import WhatsAppConfig
from .whatsapp_client import WhatsAppClient  # Exposed for test patching compatibility.

logger = logging.getLogger(__name__)

class WebhookService:
    """
    Handles Meta WhatsApp Cloud API webhook challenge verification,
    HMAC SHA-256 signature security, and incoming message parsing & routing across tenants.
    """

    @classmethod
    def resolve_tenant_from_payload(cls, payload: Dict[str, Any]):
        """Extract phone_number_id or WABA ID from payload to identify the tenant."""
        phone_number_id = None
        waba_id = None
        for entry in payload.get('entry', []):
            if entry.get('id'):
                waba_id = str(entry.get('id')).strip()
            for change in entry.get('changes', []):
                value = change.get('value', {})
                metadata = value.get('metadata', {})
                if metadata.get('phone_number_id'):
                    phone_number_id = str(metadata.get('phone_number_id')).strip()
                    break
            if phone_number_id:
                break

        if phone_number_id:
            cfg = WhatsAppConfig.objects.filter(phone_number_id=phone_number_id).select_related('tenant').first()
            if cfg and cfg.tenant:
                return cfg.tenant

        if waba_id:
            cfg = WhatsAppConfig.objects.filter(business_account_id=waba_id).select_related('tenant').first()
            if cfg and cfg.tenant:
                return cfg.tenant

        # Strict isolation: never fall back to another client's or Neoriz's workspace
        return None

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
        if hub_mode != "subscribe" or not hub_verify_token:
            return False, "Verification failed"

        configs = WhatsAppConfig.objects.filter(is_enabled=True, verify_token=hub_verify_token).select_related('tenant')
        for cfg in configs:
            if cfg.tenant and not cfg.tenant.is_active:
                logger.warning("Webhook challenge rejected: tenant %s is suspended.", cfg.tenant.name)
                return False, "Verification failed: tenant suspended"
            return True, hub_challenge or ""

        env_verify = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '').strip()
        if env_verify and hub_verify_token == env_verify:
            return True, hub_challenge or ""

        logger.warning('WhatsApp webhook verification failed.')
        return False, "Verification failed"

    @classmethod
    def verify_signature(cls, raw_body: bytes, signature_header: Optional[str], tenant=None) -> bool:
        """
        Verify the X-Hub-Signature-256 header using the tenant's Meta App Secret.
        """
        cfg = WhatsAppConfig.get_settings(tenant=tenant)
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
    def process_incoming_payload(cls, payload: Dict[str, Any], tenant=None) -> Dict[str, Any]:
        """
        Parse and process inbound Meta WhatsApp webhook event idempotently for the tenant.
        """
        from .events import process_events
        return process_events(payload, tenant=tenant)


# Module-level convenience functions
resolve_tenant_from_payload = WebhookService.resolve_tenant_from_payload
verify_challenge = WebhookService.verify_challenge
verify_signature = WebhookService.verify_signature
process_incoming_payload = WebhookService.process_incoming_payload

