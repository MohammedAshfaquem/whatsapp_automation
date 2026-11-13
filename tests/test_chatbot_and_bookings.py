import pytest
from django.contrib.auth.models import User
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice, ConversationStatus
from apps.bookings.models import Booking, BookingStatus
from apps.services.models import Service, PriceType

@pytest.mark.django_db
class TestChatbotAndBookings:
    @pytest.fixture(autouse=True)
    def authenticated_simulator(self, client, db):
        operator = User.objects.create_user('simulator-operator', is_staff=True)
        client.force_login(operator)

    def test_customer_and_conversation(self):
        customer = Customer.objects.create(
            name="John Doe",
            phone_number="+919876543210"
        )
        assert str(customer) == "John Doe (+919876543210)"

        conversation = Conversation.objects.create(
            customer=customer,
            channel=ChannelChoice.SIMULATED,
            status=ConversationStatus.BOT_ACTIVE
        )
        assert conversation.status == ConversationStatus.BOT_ACTIVE

    def test_simulated_chat_endpoint_greeting(self, client):
        payload = {
            "phone_number": "+919876543210",
            "message": "Hi, good morning!"
        }
        response = client.post('/api/chat/test/', data=payload, content_type='application/json')
        assert response.status_code == 200
        data = response.json()
        assert data['conversation_id'] is not None
        assert "Hello!" in data['reply']
        assert data['handover_required'] is False

    def test_simulated_chat_endpoint_services_lookup(self, client):
        Service.objects.all().delete()
        Service.objects.create(
            name="AC Deep Clean",
            description="Deep cleaning service",
            price_type=PriceType.STARTING_FROM,
            price_amount=699.00,
            is_active=True
        )

        payload = {
            "phone_number": "+919876543210",
            "message": "What is the price of service?"
        }
        response = client.post('/api/chat/test/', data=payload, content_type='application/json')
        assert response.status_code == 200
        data = response.json()
        assert "Which service are you interested in?" in data['reply']
        assert data.get('options') is not None
        assert any(opt['title'] == "AC Deep Clean" for opt in data['options'])
        assert any("₹699 onwards" in opt.get('description', '') for opt in data['options'])

    def test_simulated_chat_human_handover_behavior(self, client):
        customer = Customer.objects.create(
            name="Handover Customer",
            phone_number="+919999900000"
        )
        Conversation.objects.create(
            customer=customer,
            channel=ChannelChoice.SIMULATED,
            status=ConversationStatus.HUMAN_HANDOVER
        )

        payload = {
            "phone_number": "+919999900000",
            "message": "Can I talk to the shop owner?"
        }
        response = client.post('/api/chat/test/', data=payload, content_type='application/json')
        assert response.status_code == 200
        data = response.json()
        assert data['handover_required'] is True
        assert not data['reply']

    def test_booking_owner_confirmation(self, client):
        # Create superuser / staff user for authorized booking management
        admin_user = User.objects.create_superuser(username='owner', password='ownerpassword', email='owner@example.com')
        client.login(username='owner', password='ownerpassword')

        customer = Customer.objects.create(name="Jane Doe", phone_number="+919811122233")
        service = Service.objects.create(
            name="AC Gas Topup",
            description="Gas topup",
            price_type=PriceType.STARTING_FROM,
            price_amount=1200.00
        )
        booking = Booking.objects.create(
            customer=customer,
            service=service,
            service_address="Flat 402, Sunshine Apartments, Delhi",
            status=BookingStatus.PENDING
        )

        # Confirm booking
        confirm_url = f"/api/bookings/{booking.id}/confirm/"
        resp = client.post(confirm_url, data={"owner_notes": "Technician Ramesh assigned"}, content_type='application/json')
        assert resp.status_code == 200

        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONFIRMED
        assert "Ramesh" in booking.owner_notes
