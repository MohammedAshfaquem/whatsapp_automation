import pytest
from django.contrib.auth.models import User
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice, ConversationStatus
from apps.services.models import Service, PriceType
from apps.business.models import BusinessProfile
from apps.bookings.models import Booking, BookingSession, BookingStep, BookingStatus
from apps.chatbot.conversation_service import ConversationService

@pytest.fixture(autouse=True)
def setup_phase4_data(db):
    BusinessProfile.objects.all().delete()
    Service.objects.all().delete()
    Booking.objects.all().delete()
    BookingSession.objects.all().delete()

    BusinessProfile.objects.create(
        shop_name="CoolAir AC Services",
        contact_phone="+91 98765 43210",
        address="Main Market, Delhi",
        is_active=True
    )

    Service.objects.create(
        name="AC gas filling",
        description="Refrigerant refill and nitrogen leak check",
        price_type=PriceType.STARTING_FROM,
        price_amount=1500.00,
        is_active=True
    )

    Service.objects.create(
        name="AC general servicing",
        description="Filter clean and jet wash",
        price_type=PriceType.STARTING_FROM,
        price_amount=500.00,
        is_active=True
    )

@pytest.mark.django_db
class TestMultiTurnBookingWorkflow:
    def test_complete_slot_filling_booking_flow(self):
        phone = "+919988776655"

        # Step 1: Initiate booking with service mention
        r1 = ConversationService.process_message(phone, "I want to book AC gas filling")
        assert "name" in r1["reply"].lower()
        assert r1["booking_id"] is None

        # Step 2: Provide name
        r2 = ConversationService.process_message(phone, "Afi Ahmed")
        assert "what type of ac" in r2["reply"].lower()
        customer = Customer.objects.get(phone_number=phone)
        assert customer.name == "Afi Ahmed"

        # Step 3: Provide AC details & issue
        r3 = ConversationService.process_message(phone, "Split AC Daikin, not cooling properly")
        assert "service address" in r3["reply"].lower()

        # Step 4: Provide address
        r4 = ConversationService.process_message(phone, "Flat 302, Palm Residency, South Delhi")
        assert "preferred date and time" in r4["reply"].lower()

        # Step 5: Provide schedule date/time -> Creates Booking
        review = ConversationService.process_message(phone, "Tomorrow at 11 AM")
        assert review['booking_id'] is None
        r5 = ConversationService.process_message(phone, 'booking_submit')
        assert "submitted successfully" in r5["reply"].lower()
        assert "pending confirmation" in r5["reply"].lower()
        assert r5["booking_id"] is not None

        # Verify Booking in database
        booking = Booking.objects.get(id=r5["booking_id"])
        assert booking.status == BookingStatus.PENDING
        assert booking.customer.phone_number == phone
        assert booking.customer.name == "Afi Ahmed"
        assert booking.service.name == "AC gas filling"
        assert "Palm Residency" in booking.service_address
        assert "Tomorrow at 11 AM" in booking.preferred_time_slot
        assert "Split AC" in booking.ac_type

    def test_cancel_booking_session(self):
        phone = "+919911223344"
        r1 = ConversationService.process_message(phone, "I want to book an appointment")
        assert "name" in r1["reply"].lower()

        # Customer decides to cancel
        r2 = ConversationService.process_message(phone, "cancel")
        assert "cancelled" in r2["reply"].lower()
        assert r2["booking_id"] is None

        # Next message is treated normally, not as a booking slot
        r3 = ConversationService.process_message(phone, "What are your services?")
        assert "Which service are you interested in?" in r3["reply"]
        assert any(opt['title'] == "AC general servicing" for opt in r3["options"])

@pytest.mark.django_db
class TestHumanHandoverWorkflow:
    def test_customer_requests_human_handover(self):
        phone = "+919876500001"
        res = ConversationService.process_message(phone, "Please connect me to human support")
        assert res["handover_required"] is True
        assert "handed over" in res["reply"].lower()

        conv = Conversation.objects.get(id=res["conversation_id"])
        assert conv.status == ConversationStatus.HUMAN_HANDOVER

        # Subsequent messages continue to return handover notice
        res2 = ConversationService.process_message(phone, "Is anyone there?")
        assert res2["handover_required"] is True
        assert not res2['reply']

    def test_owner_resumes_bot(self):
        phone = "+919876500002"
        res = ConversationService.process_message(phone, "I want to talk to an agent")
        conv = Conversation.objects.get(id=res["conversation_id"])
        assert conv.status == ConversationStatus.HUMAN_HANDOVER

        # Shop owner resumes bot via Admin/Dashboard
        conv.status = ConversationStatus.BOT_ACTIVE
        conv.save()

        # Bot now answers automatically again
        res2 = ConversationService.process_message(phone, "What are your AC service prices?")
        assert res2["handover_required"] is False
        assert "Which service are you interested in?" in res2["reply"]
        assert any(opt['title'] == "AC general servicing" for opt in res2["options"])

@pytest.mark.django_db
class TestOwnerBookingAPIs:
    def test_owner_confirm_and_reject_endpoints(self, client):
        admin = User.objects.create_superuser(username='shopowner', password='ownerpass123', email='owner@shop.com')
        customer = Customer.objects.create(name="Rohit", phone_number="+919810012345")
        svc = Service.objects.first()

        booking = Booking.objects.create(
            customer=customer,
            service=svc,
            service_address="B-12, Sector 62, Noida",
            status=BookingStatus.PENDING
        )

        # 1. Anonymous attempt -> Denied
        resp_anon = client.post(f"/api/bookings/{booking.id}/confirm/", {"owner_notes": "test"})
        assert resp_anon.status_code in (401, 403)

        # 2. Authorized owner confirms
        client.login(username='shopowner', password='ownerpass123')
        resp_confirm = client.post(
            f"/api/bookings/{booking.id}/confirm/",
            data={"owner_notes": "Confirmed for 10 AM by Tech Vijay"},
            content_type='application/json'
        )
        assert resp_confirm.status_code == 200
        booking.refresh_from_db()
        assert booking.status == BookingStatus.CONFIRMED
        assert "Vijay" in booking.owner_notes

        # 3. Authorized owner rejects another booking
        booking2 = Booking.objects.create(
            customer=customer,
            service=svc,
            service_address="Out of city area",
            status=BookingStatus.PENDING
        )
        resp_reject = client.post(
            f"/api/bookings/{booking2.id}/reject/",
            data={"owner_notes": "Address outside service coverage"},
            content_type='application/json'
        )
        assert resp_reject.status_code == 200
        booking2.refresh_from_db()
        assert booking2.status == BookingStatus.REJECTED
        assert "outside service coverage" in booking2.owner_notes

@pytest.mark.django_db
class TestSystemDesignImprovements:
    def test_name_extraction_and_personalized_greeting(self):
        phone = "+919988112233"
        res = ConversationService.process_message(phone, "Hello i am ashfaque")
        assert "ashfaque" in res["reply"].lower()
        customer = Customer.objects.get(phone_number=phone)
        assert customer.name == "Ashfaque"

        # Subsequent greeting also uses customer name
        res2 = ConversationService.process_message(phone, "hello")
        assert "ashfaque" in res2["reply"].lower()

    def test_verified_account_data_booking_status(self):
        phone = "+919988112244"
        customer = Customer.objects.create(name="Imran", phone_number=phone)
        svc = Service.objects.first()
        Booking.objects.create(
            customer=customer,
            service=svc,
            service_address="Sector 18, Noida",
            status=BookingStatus.CONFIRMED,
            preferred_time_slot="Morning (9 AM - 12 PM)",
            owner_notes="Tech Rajesh assigned"
        )

        res = ConversationService.process_message(phone, "check my booking status")
        assert "booking details" in res["reply"].lower()
        assert "confirmed" in res["reply"].lower()
        assert "tech rajesh" not in res["reply"].lower()
        assert "imran" in res["reply"].lower()

    def test_verified_account_data_no_bookings(self):
        phone = "+919988112255"
        res = ConversationService.process_message(phone, "what is my appointment status")
        assert "don't have any bookings" in res["reply"].lower()

    def test_two_turn_unresolved_escalation_rule(self):
        phone = "+919988112266"
        # Turn 1: Unrecognized query -> Fallback help given
        r1 = ConversationService.process_message(phone, "blablabla xyz 123 random meaningless text")
        assert r1["handover_required"] is False
        assert "coolair ac services" in r1["reply"].lower()

        # Turn 2: Second consecutive unrecognized query -> Rules in code escalate to human handover
        r2 = ConversationService.process_message(phone, "asdfg qwerty still gibberish")
        assert r2["handover_required"] is True
        assert "handed over" in r2["reply"].lower()

        conv = Conversation.objects.get(id=r2["conversation_id"])
        assert conv.status == ConversationStatus.HUMAN_HANDOVER

