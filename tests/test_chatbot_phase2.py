import pytest
from apps.chatbot.models import Customer, Conversation, Message, ChannelChoice, ConversationStatus
from apps.chatbot.intent_service import IntentService, IntentType
from apps.chatbot.conversation_service import ConversationService
from apps.services.models import Service, PriceType
from apps.business.models import BusinessProfile
from apps.knowledge_base.models import FAQ

@pytest.fixture(autouse=True)
def setup_phase2_data(db):
    BusinessProfile.objects.all().delete()
    Service.objects.all().delete()
    FAQ.objects.all().delete()

    BusinessProfile.objects.create(
        shop_name="CoolAir AC Masters",
        contact_phone="+91 98765 00000",
        address="Shop 12, Sector 18 Market, Noida",
        working_hours="Monday to Saturday: 9:00 AM - 8:00 PM\nSunday: 10:00 AM - 4:00 PM",
        holiday_information="Closed on Holi and Diwali",
        service_areas="Noida, Greater Noida, Indirapuram, Ghaziabad",
        supported_ac_types="Split AC, Window AC, Inverter AC",
        supported_ac_brands="Daikin, Voltas, LG, Samsung, Blue Star",
        warranty_policies="30-day service warranty",
        accepted_payment_methods="Cash, UPI, Credit Card",
        general_service_policies="₹200 inspection fee if service is cancelled",
        is_active=True
    )

    Service.objects.create(
        name="AC general servicing",
        description="Filter cleaning, indoor and outdoor jet wash",
        price_type=PriceType.STARTING_FROM,
        price_amount=500.00,
        estimated_duration="45 mins",
        is_active=True
    )

    Service.objects.create(
        name="AC gas filling",
        description="Refrigerant gas top-up",
        price_type=PriceType.STARTING_FROM,
        price_amount=1500.00,
        estimated_duration="1 hour",
        is_active=True
    )

    Service.objects.create(
        name="AC installation",
        description="Wall mounting and pipe connection",
        price_type=PriceType.STARTING_FROM,
        price_amount=1000.00,
        estimated_duration="2 hours",
        is_active=True
    )

    FAQ.objects.create(
        question="Do you provide doorstep visits?",
        answer="Yes, our verified technicians provide doorstep home visits for all repairs and servicing.",
        category="General",
        is_active=True
    )

@pytest.mark.django_db
class TestPhase2IntentService:
    def test_detect_greeting(self):
        intent, entity = IntentService.detect_intent("Hello!")
        assert intent == IntentType.GREETING

    def test_detect_service_list(self):
        intent, entity = IntentService.detect_intent("What services do you offer?")
        assert intent == IntentType.SERVICE_LIST

    def test_detect_specific_service_gas(self):
        intent, entity = IntentService.detect_intent("How much for ac gas filling?")
        assert intent == IntentType.SERVICE_PRICE
        assert entity is not None
        assert "gas" in entity.name.lower()

    def test_detect_working_hours(self):
        intent, entity = IntentService.detect_intent("What are your timings on Sunday?")
        assert intent == IntentType.WORKING_HOURS

    def test_detect_service_areas(self):
        intent, entity = IntentService.detect_intent("Do you serve in Indirapuram?")
        assert intent == IntentType.SERVICE_AREAS

    def test_detect_location(self):
        intent, entity = IntentService.detect_intent("Where is your shop located?")
        assert intent == IntentType.SHOP_LOCATION

    def test_detect_payment(self):
        intent, entity = IntentService.detect_intent("Can I pay via UPI Google Pay?")
        assert intent == IntentType.PAYMENT_METHODS

    def test_detect_warranty(self):
        intent, entity = IntentService.detect_intent("What is your warranty policy?")
        assert intent == IntentType.WARRANTY_POLICY

    def test_detect_booking(self):
        intent, entity = IntentService.detect_intent("I want to book an appointment for repair")
        assert intent == IntentType.BOOKING_START

    def test_detect_faq_match(self):
        intent, entity = IntentService.detect_intent("Do you provide doorstep visits?")
        assert intent == IntentType.FAQ_MATCH
        assert entity is not None
        assert "doorstep" in entity.question.lower()

@pytest.mark.django_db
class TestPhase2ConversationService:
    def test_process_greeting_flow(self):
        res = ConversationService.process_message(
            phone_number="+919876512345",
            message_text="Hi there",
            channel=ChannelChoice.SIMULATED
        )
        assert res['conversation_id'] is not None
        assert "CoolAir AC Masters" in res['reply']
        assert res['handover_required'] is False

    def test_process_specific_gas_enquiry(self):
        res = ConversationService.process_message(
            phone_number="+919876512345",
            message_text="How much for AC gas filling?",
            channel=ChannelChoice.SIMULATED
        )
        assert "AC gas filling" in res['reply']
        assert "₹1,500 onwards" in res['reply']
        assert "1 hour" in res['reply']

    def test_process_working_hours(self):
        res = ConversationService.process_message(
            phone_number="+919876512345",
            message_text="When are you open?",
            channel=ChannelChoice.SIMULATED
        )
        assert "Monday to Saturday: 9:00 AM - 8:00 PM" in res['reply']

    def test_process_service_areas(self):
        res = ConversationService.process_message(
            phone_number="+919876512345",
            message_text="Which areas do you cover?",
            channel=ChannelChoice.SIMULATED
        )
        assert "Noida, Greater Noida, Indirapuram" in res['reply']

    def test_message_deduplication(self):
        ext_id = "wamid.HBgLMTIzNDU2Nzg5MA=="
        res1 = ConversationService.process_message(
            phone_number="+919876512345",
            message_text="Hello",
            channel=ChannelChoice.WHATSAPP,
            external_message_id=ext_id
        )
        res2 = ConversationService.process_message(
            phone_number="+919876512345",
            message_text="Hello",
            channel=ChannelChoice.WHATSAPP,
            external_message_id=ext_id
        )
        assert res1['conversation_id'] == res2['conversation_id']
        # Database only stored 1 inbound message with this external ID
        assert Message.objects.filter(external_message_id=ext_id).count() == 1

    def test_human_handover_flow(self):
        customer = Customer.objects.create(phone_number="+919000011111")
        conv = Conversation.objects.create(
            customer=customer,
            channel=ChannelChoice.SIMULATED,
            status=ConversationStatus.HUMAN_HANDOVER
        )

        res = ConversationService.process_message(
            phone_number="+919000011111",
            message_text="Can someone help me urgently?",
            channel=ChannelChoice.SIMULATED
        )
        assert res['handover_required'] is True
        assert not res['reply']

@pytest.mark.django_db
class TestPhase2SimulatedEndpoint:
    @pytest.fixture(autouse=True)
    def authenticated_simulator(self, client, db):
        from django.contrib.auth.models import User
        client.force_login(User.objects.create_user('simulator-operator', is_staff=True))

    def test_api_chat_test_services(self, client):
        payload = {
            "phone_number": "+919876512345",
            "message": "What services do you provide?"
        }
        response = client.post('/api/chat/test/', data=payload, content_type='application/json')
        assert response.status_code == 200
        data = response.json()
        assert "Which service are you interested in?" in data['reply']
        assert data.get('options') is not None
        assert any(opt['title'] == "AC general servicing" for opt in data['options'])
        assert any(opt['title'] == "AC gas filling" for opt in data['options'])

    def test_whatsapp_interactive_button_full_flow(self, client):
        phone = "+919876500001"
        
        # Step 1: User asks for services
        step1_res = client.post('/api/chat/test/', data={"phone_number": phone, "message": "Hi, what are your packages?"}, content_type='application/json')
        assert step1_res.status_code == 200
        step1_data = step1_res.json()
        assert "Which service are you interested in?" in step1_data['reply']
        assert len(step1_data['options']) > 0
        service_id = step1_data['options'][0]['id']

        # Step 2: User taps a service option button (e.g. "service_1" or "AC general servicing")
        step2_res = client.post('/api/chat/test/', data={"phone_number": phone, "message": service_id}, content_type='application/json')
        assert step2_res.status_code == 200
        step2_data = step2_res.json()
        assert "Would you like to check the service price or book an appointment?" in step2_data['reply']
        assert any(opt['title'] == "Check Price" for opt in step2_data['options'])
        assert any(opt['title'] == "Book a Visit" for opt in step2_data['options'])
        check_price_id = next(opt['id'] for opt in step2_data['options'] if opt['title'] == "Check Price")

        # Step 3: User taps "Check Price"
        step3_res = client.post('/api/chat/test/', data={"phone_number": phone, "message": check_price_id}, content_type='application/json')
        assert step3_res.status_code == 200
        step3_data = step3_res.json()
        assert "₹" in step3_data['reply']
        assert any(opt['title'] == "Book a Visit" for opt in step3_data['options'])
        book_btn_id = next(opt['id'] for opt in step3_data['options'] if opt['title'] == "Book a Visit")

        # Step 4: User taps "Book a Visit"
        step4_res = client.post('/api/chat/test/', data={"phone_number": phone, "message": book_btn_id}, content_type='application/json')
        assert step4_res.status_code == 200
        step4_data = step4_res.json()
        assert "appointment" in step4_data['reply'].lower() or "booking" in step4_data['reply'].lower()
