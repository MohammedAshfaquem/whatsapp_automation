import pytest
from django.core.exceptions import ValidationError
from apps.business.models import BusinessProfile
from apps.business.services import get_business_summary

@pytest.mark.django_db
class TestBusinessProfile:
    def test_single_active_profile_constraint(self):
        BusinessProfile.objects.all().delete()
        p1 = BusinessProfile.objects.create(
            shop_name="Shop 1",
            contact_phone="123456",
            address="Address 1",
            is_active=True
        )

        p2 = BusinessProfile(
            shop_name="Shop 2",
            contact_phone="654321",
            address="Address 2",
            is_active=True
        )

        with pytest.raises(ValidationError):
            p2.clean()

    def test_get_business_summary(self):
        BusinessProfile.objects.all().delete()
        profile = BusinessProfile.objects.create(
            shop_name="CoolAir AC Experts",
            contact_phone="+91 99999 88888",
            address="Plot 5, Sector 18, Noida",
            working_hours="10 AM - 7 PM",
            service_areas="Noida, Greater Noida",
            supported_ac_types="Split, Window",
            supported_ac_brands="LG, Daikin",
            warranty_policies="30-day warranty",
            accepted_payment_methods="Cash, UPI",
            general_service_policies="₹200 inspection charge",
            is_active=True
        )
        summary = get_business_summary()
        assert "CoolAir AC Experts" in summary
        assert "+91 99999 88888" in summary
        assert "Noida, Greater Noida" in summary
        assert "30-day warranty" in summary
