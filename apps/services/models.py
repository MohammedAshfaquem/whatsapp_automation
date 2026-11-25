from django.db import models
from django.core.exceptions import ValidationError
from django.utils.text import slugify

class PriceType(models.TextChoices):
    FIXED = 'FIXED', 'Fixed Price'
    STARTING_FROM = 'STARTING_FROM', 'Starting From'
    PRICE_RANGE = 'PRICE_RANGE', 'Price Range'
    INSPECTION_REQUIRED = 'INSPECTION_REQUIRED', 'Inspection Required'

class Service(models.Model):
    """
    Service model - PostgreSQL source of truth for services and pricing.
    """
    tenant = models.ForeignKey('tenants.Tenant', on_delete=models.CASCADE, related_name='services', null=True, blank=True)
    name = models.CharField(max_length=150, help_text="e.g. Website Development, General Servicing")
    slug = models.SlugField(max_length=160, blank=True)
    description = models.TextField(blank=True, default="", help_text="Detailed explanation of what the service includes")
    category = models.CharField(max_length=100, default="Maintenance", help_text="e.g. Maintenance, Repair, Installation")
    
    price_type = models.CharField(
        max_length=30,
        choices=PriceType.choices,
        default=PriceType.STARTING_FROM,
        help_text="Pricing structure for this service"
    )
    price_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Base/Starting/Fixed price in INR"
    )
    max_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Maximum price if price type is PRICE_RANGE"
    )
    currency = models.CharField(max_length=10, default="INR")
    estimated_duration = models.CharField(
        max_length=60,
        blank=True,
        help_text="Estimated duration (e.g. 45-60 mins, 2 hours)"
    )
    contact_number = models.CharField(
        max_length=30,
        blank=True,
        default="+91 98765 43210",
        help_text="Dedicated contact/WhatsApp number for this service"
    )
    is_active = models.BooleanField(default=True, help_text="Whether this service is currently offered")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['id']
        verbose_name = "Service"
        verbose_name_plural = "Services"
        unique_together = (('tenant', 'name'), ('tenant', 'slug'))

    def __str__(self):
        return f"{self.name} ({self.formatted_price})"

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        self.full_clean()
        super().save(*args, **kwargs)

    def clean(self):
        super().clean()
        # Price validation rules as per specification
        if self.price_type == PriceType.INSPECTION_REQUIRED:
            # Never treat an inspection-required service as having a confirmed fixed price
            if self.price_amount is not None and self.price_amount > 0:
                raise ValidationError({
                    'price_amount': "Inspection required service cannot have a fixed or starting price. Price is determined on inspection."
                })
            if self.max_price is not None and self.max_price > 0:
                raise ValidationError({
                    'max_price': "Inspection required service cannot have a max price."
                })
        elif self.price_type == PriceType.PRICE_RANGE:
            if self.price_amount is None or self.price_amount <= 0:
                raise ValidationError({
                    'price_amount': "Price range requires a valid minimum price (price_amount)."
                })
            if self.max_price is None or self.max_price <= 0:
                raise ValidationError({
                    'max_price': "Price range requires a valid maximum price (max_price)."
                })
            if self.max_price < self.price_amount:
                raise ValidationError({
                    'max_price': "Maximum price cannot be less than minimum price."
                })
        elif self.price_type in (PriceType.FIXED, PriceType.STARTING_FROM):
            if self.price_amount is None or self.price_amount <= 0:
                raise ValidationError({
                    'price_amount': f"{self.get_price_type_display()} requires a price amount greater than 0."
                })
            if self.max_price is not None and self.max_price > 0 and self.price_type == PriceType.FIXED:
                raise ValidationError({
                    'max_price': "Fixed price service cannot have a maximum price. Use Price Range if variable."
                })

    @property
    def formatted_price(self) -> str:
        symbol = "₹" if self.currency == "INR" else f"{self.currency} "
        if self.price_type == PriceType.INSPECTION_REQUIRED:
            from apps.business.domain import is_it_business
            if is_it_business():
                return 'Quote after requirements review'
            return "Inspection required"
        elif self.price_type == PriceType.STARTING_FROM:
            return f"{symbol}{self.price_amount:,.0f} onwards"
        elif self.price_type == PriceType.FIXED:
            return f"{symbol}{self.price_amount:,.0f}"
        elif self.price_type == PriceType.PRICE_RANGE:
            return f"{symbol}{self.price_amount:,.0f} - {symbol}{self.max_price:,.0f}"
        return "Contact shop"
