from django.db import models
from django.core.exceptions import ValidationError

class BusinessProfile(models.Model):
    """
    Shop profile containing business information, operating hours, policies,
    and service areas. Admin managed source of truth for the AI assistant.
    """
    shop_name = models.CharField(max_length=200, default="CoolAir AC Services & Mechanicals")
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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Business Profile"
        verbose_name_plural = "Business Profiles"

    def __str__(self):
        return f"{self.shop_name} ({'Active' if self.is_active else 'Inactive'})"

    def clean(self):
        # Ensure only one profile is active at a time
        if self.is_active:
            qs = BusinessProfile.objects.filter(is_active=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError("Only one Business Profile can be active at a time.")

    @classmethod
    def get_active(cls):
        """Helper to get currently active business profile."""
        profile = cls.objects.filter(is_active=True).first()
        return profile
