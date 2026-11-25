from django.db import models
from django.core.exceptions import ValidationError

from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify


class BusinessProfile(models.Model):
    """
    Shop profile containing business information, operating hours, policies,
    and service areas. Admin managed source of truth for the AI assistant.
    """
    tenant = models.OneToOneField('tenants.Tenant', on_delete=models.CASCADE, related_name='business_profile', null=True, blank=True)
    shop_name = models.CharField(max_length=200, default="Neoriz Solutions")
    contact_phone = models.CharField(max_length=20, default="+91 98765 43210")
    address = models.TextField(default="123 Industrial Area, Main Road, New Delhi, India")
    google_maps_url = models.URLField(blank=True, null=True, help_text="Link to shop location on Google Maps")

    working_hours = models.TextField(
        default="Monday to Saturday: 9:00 AM - 8:00 PM\nSunday: 10:00 AM - 4:00 PM",
        help_text="Detailed working hours for each day"
    )
    holiday_information = models.TextField(
        blank=True,
        default="Closed on National Holidays and Diwali",
        help_text="Information about scheduled holidays or closures"
    )
    service_areas = models.TextField(
        default="South Delhi, Central Delhi, Noida Sector 1-62, Indirapuram, Gurgaon DLF Phase 1-5",
        help_text="Localities and neighborhoods served by the shop"
    )
    supported_ac_types = models.TextField(
        default="Split AC, Window AC, Inverter AC, Cassette AC, Tower AC",
        help_text="Types of air conditioners serviced"
    )
    supported_ac_brands = models.TextField(
        default="Daikin, Voltas, LG, Samsung, Blue Star, Carrier, Hitachi, Lloyd, Panasonic, Godrej",
        help_text="Brands handled by the shop technicians"
    )
    warranty_policies = models.TextField(
        default="30-day warranty on general service and repair workmanship. 90-day warranty on genuine spare parts replaced by our team.",
        help_text="Warranty terms and coverage details"
    )
    accepted_payment_methods = models.TextField(
        default="Cash, UPI (Google Pay, PhonePe, Paytm), Credit & Debit Cards, Net Banking",
        help_text="Payment modes accepted"
    )
    general_service_policies = models.TextField(
        default="Visiting/inspection charge of ₹200 applies if service is not availed after inspection. Payment due upon service completion.",
        help_text="General service terms, visiting charges, inspection rules"
    )
    is_active = models.BooleanField(default=True, help_text="Designates if this profile is actively used by the bot")
    business_hours = models.JSONField(default=dict, blank=True, help_text="Structured weekly business hours schedule")
    after_hours_auto_reply = models.TextField(blank=True, default='', help_text="Optional automatic reply sent outside business hours")
    greeting_auto_reply = models.TextField(blank=True, default='', help_text="Optional automatic greeting on first customer message")
    auto_assign_inbound = models.BooleanField(default=False, help_text="Automatically round-robin assign new human-queue chats")
    no_response_followup_minutes = models.PositiveSmallIntegerField(default=0, help_text="Create follow-up alert after N minutes without human response (0 = disabled)")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business Profile"
        verbose_name_plural = "Business Profiles"

    def __str__(self):
        return f"{self.shop_name} ({'Active' if self.is_active else 'Inactive'})"

    def clean(self):
        # Ensure only one profile is active at a time per tenant
        if self.is_active:
            qs = BusinessProfile.objects.filter(is_active=True)
            if self.tenant_id:
                qs = qs.filter(tenant=self.tenant)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("Only one Business Profile can be active per tenant at a time.")

    @classmethod
    def get_active(cls, tenant=None):
        """Helper to get currently active business profile for the current or specified tenant."""
        from apps.tenants.context import get_current_tenant
        if tenant is None:
            tenant = get_current_tenant()
        if tenant:
            profile = cls.objects.filter(tenant=tenant, is_active=True).first()
            if profile:
                return profile
        return cls.objects.filter(is_active=True).first()


class PricingStatus(models.TextChoices):
    APPROVED_PRICING = 'APPROVED_PRICING', 'Approved Pricing Available'
    QUOTE_REQUIRED = 'QUOTE_REQUIRED', 'Quote on Request'
    CONTACT_SALES = 'CONTACT_SALES', 'Contact Sales for Pricing'
    UNCONFIRMED = 'UNCONFIRMED', 'Pricing Not Yet Confirmed'


class FeatureAvailability(models.TextChoices):
    AVAILABLE = 'AVAILABLE', 'Verified Available'
    NOT_SUPPORTED = 'NOT_SUPPORTED', 'Not Supported / Unavailable'
    UNCONFIRMED = 'UNCONFIRMED', 'Unconfirmed / Roadmap / Under Verification'


class Product(models.Model):
    """
    Neoriz Solutions software product (e.g. TABLO, WhatsApp Automation + CRM).
    PostgreSQL source of truth for product capabilities, pricing status, and suitability.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='products', null=True, blank=True)
    name = models.CharField(max_length=150, help_text="e.g. TABLO, WhatsApp Automation + CRM")
    slug = models.SlugField(max_length=160, blank=True)
    tagline = models.CharField(max_length=255, blank=True, help_text="Short positioning tagline")
    description = models.TextField(blank=True, default="", help_text="Detailed explanation of what the product does")
    intended_customers = models.TextField(blank=True, help_text="Target audience and intended customer types")
    limitations = models.TextField(blank=True, help_text="Explicit verified limitations or boundaries")
    deployment_onboarding = models.TextField(blank=True, help_text="Deployment method and onboarding process")
    support_info = models.TextField(blank=True, help_text="Support channels, availability, and SLA/support terms")
    demo_process = models.TextField(blank=True, help_text="How product demonstrations are conducted")
    
    pricing_status = models.CharField(
        max_length=30,
        choices=PricingStatus.choices,
        default=PricingStatus.UNCONFIRMED,
        help_text="Status of public/approved pricing for this product"
    )
    pricing_details = models.TextField(
        blank=True,
        help_text="Approved pricing structure, starting rates, or quotation process notes"
    )
    source_references = models.TextField(
        blank=True,
        help_text="Documentation, website URLs, or records verifying these facts"
    )
    last_verified_at = models.DateField(
        null=True,
        blank=True,
        help_text="Date facts were last verified"
    )
    aliases = models.CharField(
        max_length=255,
        blank=True,
        help_text="Comma-separated keywords or aliases (e.g. 'tablo, restaurant app, qr ordering')"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Whether this product is currently active and promoted by the assistant"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = "Product"
        verbose_name_plural = "Products"
        unique_together = (('tenant', 'slug'), ('tenant', 'name'))

    def __str__(self):
        return f"{self.name} ({'Active' if self.is_active else 'Inactive'})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    @property
    def formatted_pricing(self) -> str:
        if self.pricing_status == PricingStatus.APPROVED_PRICING and self.pricing_details:
            return self.pricing_details
        if self.pricing_status == PricingStatus.QUOTE_REQUIRED:
            return "Custom quotation after requirements review"
        if self.pricing_status == PricingStatus.CONTACT_SALES:
            return "Contact our sales team for confirmed pricing"
        return "Pricing to be confirmed by our team based on your requirements"

    def get_verified_capabilities(self):
        return self.capabilities.filter(is_active=True, status=FeatureAvailability.AVAILABLE)

    def get_unsupported_features(self):
        return self.capabilities.filter(is_active=True, status=FeatureAvailability.NOT_SUPPORTED)

    def get_unconfirmed_features(self):
        return self.capabilities.filter(is_active=True, status=FeatureAvailability.UNCONFIRMED)


class ProductCapability(models.Model):
    """
    Discrete capability or feature of a Product with explicit availability status.
    Distinguishes verified available features from unconfirmed or unsupported features.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='capabilities')
    name = models.CharField(max_length=150, help_text="e.g. QR-Based Ordering, POS Integration, Inventory Holds")
    category = models.CharField(max_length=100, blank=True, help_text="e.g. Ordering, Kitchen, Operations, CRM, Analytics")
    status = models.CharField(
        max_length=30,
        choices=FeatureAvailability.choices,
        default=FeatureAvailability.UNCONFIRMED,
        help_text="Verified availability state of this capability"
    )
    description = models.TextField(blank=True, help_text="Verified explanation of how this works or limitation notes")
    source_reference = models.CharField(max_length=255, blank=True, help_text="Reference document or URL")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product', 'category', 'name']
        verbose_name = "Product Capability"
        verbose_name_plural = "Product Capabilities"
        unique_together = ('product', 'name')

    def __str__(self):
        return f"{self.product.name} - {self.name} [{self.get_status_display()}]"


class ProductIntegration(models.Model):
    """
    Third-party platform or service integration for a Product.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='integrations')
    name = models.CharField(max_length=150, help_text="e.g. WhatsApp Business Cloud API, Payment Gateways, Existing POS")
    status = models.CharField(
        max_length=30,
        choices=FeatureAvailability.choices,
        default=FeatureAvailability.UNCONFIRMED,
        help_text="Integration availability status"
    )
    description = models.TextField(blank=True, help_text="Verified integration details or prerequisites")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product', 'name']
        verbose_name = "Product Integration"
        verbose_name_plural = "Product Integrations"
        unique_together = ('product', 'name')

    def __str__(self):
        return f"{self.product.name} - {self.name} [{self.get_status_display()}]"


class ProductPricingPlan(models.Model):
    """
    Approved pricing plan or tier for a Product.
    """
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='pricing_plans')
    name = models.CharField(max_length=150, help_text="e.g. Starter, Growth, Enterprise, Single Outlet")
    billing_frequency = models.CharField(max_length=50, blank=True, help_text="e.g. Monthly, Annual, One-time")
    price_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Base rate if approved")
    currency = models.CharField(max_length=10, default="INR")
    is_quote_based = models.BooleanField(default=False, help_text="Quote provided after requirements review")
    setup_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="One-time setup/onboarding fee if verified")
    description = models.TextField(blank=True, help_text="What is included in this plan")
    third_party_charges = models.TextField(blank=True, help_text="Third-party fees (e.g. Meta conversation charges, gateway fees)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['product', 'id']
        verbose_name = "Product Pricing Plan"
        verbose_name_plural = "Product Pricing Plans"

    def __str__(self):
        if self.is_quote_based or self.price_amount is None:
            price_str = "Quote on Request"
        else:
            symbol = "₹" if self.currency == "INR" else f"{self.currency} "
            freq = f" / {self.billing_frequency}" if self.billing_frequency else ""
            price_str = f"{symbol}{self.price_amount:,.0f}{freq}"
        return f"{self.product.name} - {self.name} ({price_str})"

