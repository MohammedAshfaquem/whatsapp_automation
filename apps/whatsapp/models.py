from django.db import models
from django.conf import settings

class WhatsAppConfig(models.Model):
    """
    Admin-managed Meta WhatsApp Cloud API credentials and settings.
    Allows shop owner to configure or enable WhatsApp directly via Django Admin.
    """
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='whatsapp_config', null=True, blank=True)
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
    app_id = models.CharField(max_length=60, blank=True, default='')
    app_secret = models.CharField(
        max_length=120,
        blank=True,
        help_text="Meta App Secret used to verify X-Hub-Signature-256 payload integrity"
    )
    connection_verified_at = models.DateTimeField(null=True, blank=True)
    verified_display_phone_number = models.CharField(max_length=30, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Cloud API Configuration"
        verbose_name_plural = "WhatsApp Cloud API Configuration"
        constraints = [
            models.UniqueConstraint(fields=['phone_number_id'], condition=~models.Q(phone_number_id=''), name='whatsapp_unique_phone_number_id'),
            models.UniqueConstraint(fields=['business_account_id'], condition=~models.Q(business_account_id=''), name='whatsapp_unique_business_account_id'),
        ]

    def __str__(self):
        status_str = "Enabled" if self.is_enabled else "Disabled"
        return f"WhatsApp Settings ({status_str} - ID: {self.phone_number_id or 'Not Set'})"

    def save(self, *args, **kwargs):
        fields = ('phone_number_id', 'business_account_id', 'access_token', 'verify_token', 'app_id', 'app_secret', 'is_enabled')
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values(*fields).first()
            if previous and any(previous[field] != getattr(self, field) for field in fields):
                self.connection_verified_at = None
                self.verified_display_phone_number = ''
                if kwargs.get('update_fields'):
                    kwargs['update_fields'] = set(kwargs['update_fields']) | {'connection_verified_at', 'verified_display_phone_number'}
        super().save(*args, **kwargs)

    @classmethod
    def get_settings(cls, tenant=None):
        """
        Retrieve active configuration for a specific tenant or the current context.
        """
        from apps.tenants.context import get_current_tenant
        if tenant is None:
            tenant = get_current_tenant()

        if tenant is not None:
            # Tenant configuration is a complete credential boundary: no field-level
            # environment fallback and no lookup of another tenant's configuration.
            db_cfg = cls.objects.filter(tenant=tenant).first()
            setup_ready = True
            if tenant.requires_meta_setup:
                from apps.tenants.meta_setup import meta_setup_state
                setup_ready = meta_setup_state(tenant)['ready']
            return {
                'enabled': bool(db_cfg and db_cfg.is_enabled and tenant.is_subscription_active and setup_ready),
                'phone_number_id': db_cfg.phone_number_id if db_cfg else '',
                'business_account_id': db_cfg.business_account_id if db_cfg else '',
                'verify_token': db_cfg.verify_token if db_cfg else '',
                'access_token': db_cfg.access_token if db_cfg else '',
                'app_secret': db_cfg.app_secret if db_cfg else '',
                'app_id': db_cfg.app_id if db_cfg else '',
                'tenant': tenant,
            }

        env_token = getattr(settings, 'WHATSAPP_ACCESS_TOKEN', '').strip()
        env_phone_id = getattr(settings, 'WHATSAPP_PHONE_NUMBER_ID', '').strip()
        env_verify = getattr(settings, 'WHATSAPP_VERIFY_TOKEN', '').strip()
        env_secret = getattr(settings, 'META_APP_SECRET', '').strip()
        env_enabled = getattr(settings, 'WHATSAPP_ENABLED', True)
        env_waba = getattr(settings, 'WHATSAPP_BUSINESS_ACCOUNT_ID', '').strip()

        # Unscoped legacy callers may use only an explicitly unscoped record.
        db_cfg = cls.objects.filter(tenant__isnull=True).first()

        access_token = (db_cfg.access_token if db_cfg and db_cfg.access_token else '') or env_token
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
            "tenant": tenant,
        }

class WhatsAppWebhookLog(models.Model):
    """
    Audit log of raw incoming Meta WhatsApp webhook payloads for debugging and traceability.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.SET_NULL, null=True, blank=True, related_name='webhook_logs')
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
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, null=True, blank=True, related_name='deliveries')
    dedup_key = models.CharField(max_length=180, unique=True)
    recipient_phone = models.CharField(max_length=30)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=20, default='PENDING', db_index=True)
    provider_message_id = models.CharField(max_length=150, blank=True, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    quota_reserved = models.BooleanField(default=False, db_index=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class WhatsAppBusinessProfile(models.Model):
    """
    Connected WhatsApp phone number's official Meta business profile metadata.
    Mirrors Meta's /{phone-number-id}/whatsapp_business_profile endpoint.
    """
    VERTICAL_CHOICES = [
        ('UNDEFINED', 'Undefined / Not Set'),
        ('OTHER', 'Other'),
        ('AUTO', 'Automotive'),
        ('BEAUTY', 'Beauty, Spa & Salon'),
        ('APPAREL', 'Clothing & Apparel'),
        ('EDU', 'Education'),
        ('ENTERTAIN', 'Entertainment'),
        ('EVENT_PLAN', 'Event Planning & Services'),
        ('FINANCE', 'Finance & Banking'),
        ('GROCERY', 'Grocery & Supermarket'),
        ('GOVT', 'Government & Public Services'),
        ('HOTEL', 'Hotel & Lodging'),
        ('HEALTH', 'Healthcare & Medical'),
        ('NONPROFIT', 'Non-profit & Community'),
        ('PROF_SERVICES', 'Professional Services'),
        ('RETAIL', 'Retail & Shopping'),
        ('TRAVEL', 'Travel & Transportation'),
        ('RESTAURANT', 'Restaurant & Food Service'),
    ]

    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='whatsapp_business_profile')
    about = models.CharField(max_length=139, blank=True, default='', help_text="About/bio status text (max 139 characters)")
    description = models.TextField(max_length=512, blank=True, default='', help_text="Business description (max 512 characters)")
    address = models.CharField(max_length=256, blank=True, default='', help_text="Physical business address (max 256 characters)")
    email = models.EmailField(max_length=128, blank=True, default='', help_text="Customer-facing contact email (max 128 characters)")
    websites = models.JSONField(default=list, blank=True, help_text="Up to 2 official website URLs")
    vertical = models.CharField(max_length=50, choices=VERTICAL_CHOICES, default='PROF_SERVICES')
    profile_picture_storage_key = models.CharField(max_length=500, blank=True, default='')
    profile_picture_url = models.URLField(max_length=500, blank=True, default='')

    # Read-only fields populated from Meta's phone number registration & verification
    verified_name = models.CharField(max_length=150, blank=True, default='', help_text="Meta-approved display name")
    display_phone_number = models.CharField(max_length=30, blank=True, default='', help_text="Formatted international phone number registered with Meta")
    quality_rating = models.CharField(max_length=30, default='UNKNOWN', help_text="Meta quality rating: GREEN, YELLOW, RED, or UNKNOWN")
    messaging_limit_tier = models.CharField(max_length=50, blank=True, default='UNKNOWN', help_text="Messaging volume limit tier")
    code_verification_status = models.CharField(max_length=30, blank=True, default='UNKNOWN')

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "WhatsApp Business Profile"
        verbose_name_plural = "WhatsApp Business Profiles"

    def __str__(self):
        return f"Business Profile ({self.tenant.name} - {self.display_phone_number or self.verified_name or 'Unset'})"
