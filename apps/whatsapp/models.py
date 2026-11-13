from django.db import models
from django.conf import settings

class WhatsAppConfig(models.Model):
    """
    Admin-managed Meta WhatsApp Cloud API credentials and settings.
    Allows shop owner to configure or enable WhatsApp directly via Django Admin.
    """
    is_enabled = models.BooleanField(
        default=False,
        help_text="Master toggle to enable/disable Meta WhatsApp automation"
    )
    phone_number_id = models.CharField(
        max_length=60,
        blank=True,
        help_text="Meta WhatsApp Phone Number ID (e.g. from App Dashboard)"
    )
    business_account_id = models.CharField(
        max_length=60,
        blank=True,
        help_text="WhatsApp Business Account (WABA) ID"
    )
    verify_token = models.CharField(
        max_length=120,
        blank=True,
        help_text="Custom secret token entered in Meta Webhook configuration"
    )
    access_token = models.CharField(
        max_length=350,
        blank=True,
        help_text="Permanent Meta System User Access Token with whatsapp_business_messaging permission"
    )
    app_secret = models.CharField(
        max_length=120,
        blank=True,
        help_text="Meta App Secret used to verify X-Hub-Signature-256 payload integrity"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Cloud API Configuration"
        verbose_name_plural = "WhatsApp Cloud API Configuration"

    def __str__(self):
        status_str = "Enabled" if self.is_enabled else "Disabled"
        return f"WhatsApp Settings ({status_str} - ID: {self.phone_number_id or 'Not Set'})"

    @classmethod
    def get_settings(cls):
        """
        Retrieve active configuration.
        Access token strictly prioritizes .env (settings.WHATSAPP_ACCESS_TOKEN) following
        security best practices (12-Factor App methodology: storing secrets in environment, not DB).
        """
        env_token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '').strip()
        env_phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '').strip()
        env_verify = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '').strip()
        env_secret = getattr(settings, 'META_APP_SECRET', '').strip()
        env_enabled = getattr(settings, 'WHATSAPP_ENABLED', True)
        env_waba = getattr(settings, 'WHATSAPP_BUSINESS_ACCOUNT_ID', '').strip()

        db_cfg = cls.objects.first()

        # Prioritize .env token so developers only ever need to update .env
        access_token = env_token or (db_cfg.access_token if db_cfg else '')
        phone_number_id = (db_cfg.phone_number_id if db_cfg and db_cfg.phone_number_id else '') or env_phone_id
        verify_token = (db_cfg.verify_token if db_cfg and db_cfg.verify_token else '') or env_verify
        app_secret = (db_cfg.app_secret if db_cfg and db_cfg.app_secret else '') or env_secret
        enabled = db_cfg.is_enabled if db_cfg else env_enabled
        waba_id = (db_cfg.business_account_id if db_cfg and db_cfg.business_account_id else '') or env_waba

        return {
            "enabled": enabled,
            "phone_number_id": phone_number_id,
            "business_account_id": waba_id,
            "verify_token": verify_token,
            "access_token": access_token,
            "app_secret": app_secret,
        }

class WhatsAppWebhookLog(models.Model):
    """
    Audit log of raw incoming Meta WhatsApp webhook payloads for debugging and traceability.
    """
    event_type = models.CharField(max_length=50, default="messages")
    whatsapp_message_id = models.CharField(max_length=150, blank=True, db_index=True)
    sender_phone = models.CharField(max_length=30, blank=True)
    raw_payload = models.JSONField(default=dict)
    is_processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "WhatsApp Webhook Log"
        verbose_name_plural = "WhatsApp Webhook Logs"

    def __str__(self):
        return f"Webhook #{self.id}: {self.sender_phone} ({'Processed' if self.is_processed else 'Failed'})"


class WhatsAppDelivery(models.Model):
    """Durable outbound queue shared by replies and booking notifications."""
    dedup_key = models.CharField(max_length=180, unique=True)
    recipient_phone = models.CharField(max_length=30)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='PENDING', db_index=True)
    provider_message_id = models.CharField(max_length=150, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
