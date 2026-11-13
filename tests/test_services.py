import pytest
from django.core.exceptions import ValidationError
from apps.services.models import Service, PriceType
from apps.services.services import get_active_services, get_services_formatted_text

@pytest.mark.django_db
class TestServiceModel:
    def test_create_starting_from_service(self):
        service = Service.objects.create(
            name="AC Deep Jet Cleaning",
            description="Deep cleaning with high-pressure water jet pump",
            price_type=PriceType.STARTING_FROM,
            price_amount=799.00
        )
        assert service.slug == "ac-deep-jet-cleaning"
        assert service.formatted_price == "₹799 onwards"
        assert service.is_active is True

    def test_create_fixed_price_service(self):
        service = Service.objects.create(
            name="AC Remote Replacement",
            description="Universal remote control",
            price_type=PriceType.FIXED,
            price_amount=450.00
        )
        assert service.formatted_price == "₹450"

    def test_create_price_range_service(self):
        service = Service.objects.create(
            name="AC PCB Repair",
            description="Circuit board component repair",
            price_type=PriceType.PRICE_RANGE,
            price_amount=800.00,
            max_price=2200.00
        )
        assert service.formatted_price == "₹800 - ₹2,200"

    def test_inspection_required_cannot_have_price(self):
        service = Service(
            name="Compressor Replacement",
            description="Inspection needed",
            price_type=PriceType.INSPECTION_REQUIRED,
            price_amount=1200.00
        )
        with pytest.raises(ValidationError):
            service.save()

    def test_price_range_max_must_be_greater_than_min(self):
        service = Service(
            name="Fan Motor Replacement",
            description="Motor repair or replacement",
            price_type=PriceType.PRICE_RANGE,
            price_amount=1500.00,
            max_price=1000.00
        )
        with pytest.raises(ValidationError):
            service.save()

    def test_fixed_service_requires_price(self):
        service = Service(
            name="Drain Pipe Replacement",
            description="New pipe installation",
            price_type=PriceType.FIXED,
            price_amount=None
        )
        with pytest.raises(ValidationError):
            service.save()

    def test_active_and_inactive_services_filtering(self):
        Service.objects.all().delete()
        Service.objects.create(
            name="Active Service 1",
            description="Active description",
            price_type=PriceType.STARTING_FROM,
            price_amount=500.00,
            is_active=True
        )
        Service.objects.create(
            name="Inactive Service 2",
            description="Inactive description",
            price_type=PriceType.STARTING_FROM,
            price_amount=900.00,
            is_active=False
        )

        active = get_active_services()
        assert active.count() == 1
        assert active.first().name == "Active Service 1"

        formatted = get_services_formatted_text()
        assert "Active Service 1" in formatted
        assert "Inactive Service 2" not in formatted

    def test_service_list_api(self, client):
        Service.objects.all().delete()
        Service.objects.create(
            name="API Service Test",
            description="Testing API retrieval",
            price_type=PriceType.STARTING_FROM,
            price_amount=600.00,
            is_active=True
        )
        response = client.get('/api/services/')
        assert response.status_code == 200
        data = response.json()
        assert len(data['results']) == 1
        assert data['results'][0]['name'] == "API Service Test"
        assert data['results'][0]['formatted_price'] == "₹600 onwards"
