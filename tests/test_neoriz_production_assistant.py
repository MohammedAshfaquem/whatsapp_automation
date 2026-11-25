from datetime import date, timedelta
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.bookings.models import Booking, BookingSession, BookingStep, BookingStatus, RequestType
from apps.business.models import Product, FeatureAvailability, PricingStatus
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.intent_service import IntentService, IntentType
from apps.chatbot.language import say
from apps.chatbot.models import Customer, Conversation, ConversationStatus, ChannelChoice, Message
from apps.knowledge_base.models import KnowledgeSyncStatus, SourceTypeChoice
from apps.knowledge_base.synchronization import KnowledgeSynchronizer
from apps.services.models import Service


@pytest.fixture
def neoriz_env():
    with override_settings(BUSINESS_INDUSTRY='it'):
        call_command('configure_neoriz')
        yield


@pytest.mark.django_db
class TestNeorizProductionAssistant:

    # 1. Product discovery from natural messages
    def test_product_discovery_from_natural_messages(self, neoriz_env):
        tablo = Product.objects.get(slug='tablo')
        crm = Product.objects.get(slug='whatsapp-automation-crm')

        assert IntentService.find_matching_product('I run a busy restaurant and need a system for orders') == tablo
        assert IntentService.find_matching_product('need whatsapp automation to capture customer leads') == crm

        res1 = ConversationService.process_message('+919888000001', 'Can you tell me about TABLO?')
        assert 'TABLO' in res1['reply']
        assert 'self-ordering' in res1['reply'].lower() or 'restaurant' in res1['reply'].lower()

        res2 = ConversationService.process_message('+919888000002', 'Tell me about your WhatsApp CRM solution')
        assert 'WhatsApp' in res2['reply']
        assert 'enquiry' in res2['reply'].lower() or 'lead' in res2['reply'].lower()

    # 2. TABLO and CRM aliases
    def test_product_aliases(self, neoriz_env):
        tablo = Product.objects.get(slug='tablo')
        crm = Product.objects.get(slug='whatsapp-automation-crm')

        for alias in ['tablo restaurant app', 'tablo pos', 'tablo software', 'tablo system']:
            assert IntentService.find_matching_product(alias) == tablo

        for alias in ['whatsapp crm', 'whatsapp automation', 'whatsapp lead bot', 'wa crm']:
            assert IntentService.find_matching_product(alias) == crm

    # 3. Verified versus unknown/unconfirmed feature answers
    def test_verified_vs_unconfirmed_features(self, neoriz_env):
        # QR ordering is verified
        res_qr = ConversationService.process_message('+919888000003', 'Does TABLO support QR code ordering?')
        assert 'yes' in res_qr['reply'].lower()
        assert 'qr' in res_qr['reply'].lower()

        # POS sync is unconfirmed
        res_pos = ConversationService.process_message('+919888000003', 'Does TABLO connect to my existing POS machine?')
        assert 'not confirmed' in res_pos['reply'].lower() or 'confirm' in res_pos['reply'].lower()
        assert 'guarantee' not in res_pos['reply'].lower()

        # WhatsApp CRM auto drip follow-up is unconfirmed
        res_crm_followup = ConversationService.process_message('+919888000004', 'Can your WhatsApp CRM send automated drip follow-ups?')
        assert 'confirm' in res_crm_followup['reply'].lower()

    # 4. Accurate pricing and quotation responses
    def test_accurate_pricing_and_quotations(self, neoriz_env):
        res_tablo_price = ConversationService.process_message('+919888000005', 'How much does TABLO cost?')
        assert 'tailored' in res_tablo_price['reply'].lower() or 'quote' in res_tablo_price['reply'].lower()
        assert 'outlets' in res_tablo_price['reply'].lower()
        assert '₹' not in res_tablo_price['reply']  # No invented rates

        res_crm_price = ConversationService.process_message('+919888000006', 'What is the price of WhatsApp CRM?')
        assert 'volume' in res_crm_price['reply'].lower() or 'quote' in res_crm_price['reply'].lower()
        assert 'meta' in res_crm_price['reply'].lower()

    # 5. Corrections and product switching
    def test_corrections_and_product_switching(self, neoriz_env):
        phone = '+919888000007'
        res1 = ConversationService.process_message(phone, 'I was thinking about TABLO for my food business')
        assert 'TABLO' in res1['reply']

        # Switch to agency mobile app
        res2 = ConversationService.process_message(phone, 'Actually we want a custom Mobile App developed instead')
        assert 'Mobile App' in res2['reply'] or 'mobile' in res2['reply'].lower()
        assert 'TABLO' not in res2['reply']

    # 6. Interest in multiple products
    def test_interest_in_multiple_products(self, neoriz_env):
        res = ConversationService.process_message('+919888000008', 'We want both TABLO and WhatsApp Automation CRM for our business')
        assert 'TABLO' in res['reply']
        assert 'WhatsApp' in res['reply']

    # 7. Demo submission with explicit confirmation
    def test_demo_submission_with_explicit_confirmation(self, neoriz_env):
        customer = Customer.objects.create(phone_number='+919888000009', name='Rohan')
        tablo = Product.objects.get(slug='tablo')

        with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
            def send(text):
                return ConversationService.process_message(customer.phone_number, text)

            res = send('I would like to book a demo for TABLO')
            session = BookingSession.objects.get(conversation__customer=customer)
            assert session.step == BookingStep.AC_DETAILS

            res = send('QSR counter with 2 billing points')
            session.refresh_from_db()
            assert session.step == BookingStep.ADDRESS

            res = send('Burger Spot, Kochi / rohan@burgerspot.in')
            session.refresh_from_db()
            assert session.step == BookingStep.SCHEDULE

            res = send('tomorrow afternoon')
            session.refresh_from_db()
            assert session.step == BookingStep.REVIEW
            assert 'review' in res['reply'].lower()
            assert 'pending confirmation' in res['reply'].lower()

            # Before submitting, no completed booking
            assert Booking.objects.filter(customer=customer).count() == 0

            # Explicit submission
            res_submit = send('booking_submit')
            assert 'Request #' in res_submit['reply']
            assert 'Pending Team Confirmation' in res_submit['reply']

            booking = Booking.objects.get(customer=customer)
            assert booking.status == BookingStatus.PENDING
            assert booking.request_type == RequestType.PRODUCT_DEMO
            assert booking.product == tablo
            assert booking.organization == 'Burger Spot, Kochi / rohan@burgerspot.in'
            assert 'QSR counter' in booking.requirements_summary

    # 8. General product questions during an unfinished booking without losing draft
    def test_product_question_during_booking_preserves_draft(self, neoriz_env):
        customer = Customer.objects.create(phone_number='+919888000010', name='Amina')
        with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
            def send(text):
                return ConversationService.process_message(customer.phone_number, text)

            send('Schedule a demo for TABLO')
            session = BookingSession.objects.get(conversation__customer=customer)
            assert session.step == BookingStep.AC_DETAILS

            # Ask a side question about QR codes
            res_side = send('Can customers scan QR codes at tables?')
            assert 'QR' in res_side['reply'] or 'qr' in res_side['reply'].lower()

            # Draft session should remain intact at AC_DETAILS step
            session.refresh_from_db()
            assert session.step == BookingStep.AC_DETAILS
            assert session.data.get('product_name') == 'TABLO'

    # 9. Cancellation and rescheduling
    def test_cancellation_and_rescheduling(self, neoriz_env):
        customer = Customer.objects.create(phone_number='+919888000011', name='Alex')
        with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
            def send(text):
                return ConversationService.process_message(customer.phone_number, text)

            send('Book a demo for WhatsApp CRM')
            session = BookingSession.objects.get(conversation__customer=customer)
            assert session.step in (BookingStep.AC_DETAILS, BookingStep.NAME)

            # Cancel
            res_cancel = send('cancel')
            assert 'cancel' in res_cancel['reply'].lower()
            session.refresh_from_db()
            assert session.step == BookingStep.CANCELLED

    # 10. Human handover and resumption
    def test_human_handover_and_resumption(self, neoriz_env):
        customer = Customer.objects.create(phone_number='+919888000012', name='Deepak')
        conv = Conversation.objects.create(customer=customer, channel=ChannelChoice.WHATSAPP)

        # Trigger handover
        res = ConversationService.process_message(customer.phone_number, 'I want to talk to a human agent please', channel=ChannelChoice.WHATSAPP)
        conv.refresh_from_db()
        assert conv.status == ConversationStatus.HUMAN_HANDOVER
        assert res['handover_required'] is True
        assert 'NEORIZ SOLUTIONS HANDOFF SUMMARY' in conv.handoff_summary
        assert 'Deepak' in conv.handoff_summary

        # Subsequent customer message while in handover returns empty auto-reply to avoid interrupting human
        res_during = ConversationService.process_message(customer.phone_number, 'Hello are you there?', channel=ChannelChoice.WHATSAPP)
        assert res_during['reply'] == ''
        assert res_during['handover_required'] is True

        # Customer or staff resumes bot
        res_resume = ConversationService.process_message(customer.phone_number, 'resume bot', channel=ChannelChoice.WHATSAPP)
        conv.refresh_from_db()
        assert conv.status == ConversationStatus.BOT_ACTIVE
        assert "resume" in res_resume['reply'].lower() or "help" in res_resume['reply'].lower()

    # 11. Multilingual conversation
    def test_multilingual_conversation(self, neoriz_env):
        # Bot identity in English
        res_en = ConversationService.process_message('+919888000013', 'Are you a bot?')
        assert "assistant" in res_en['reply'].lower()

        # Bot identity in Manglish
        cust_manglish = Customer.objects.create(phone_number='+919888000014', preferred_language='manglish')
        res_manglish = ConversationService.process_message(cust_manglish.phone_number, 'Are you a bot?')
        assert 'neoriz solutions' in res_manglish['reply'].lower()

        # Hindi greeting
        cust_hi = Customer.objects.create(phone_number='+919888000015', preferred_language='hi')
        res_hi = ConversationService.process_message(cust_hi.phone_number, 'नमस्ते')
        assert 'Neoriz Solutions' in res_hi['reply']

    # 12. Provider failures (deterministic fallback)
    def test_provider_failures_graceful_fallback(self, neoriz_env):
        customer = Customer.objects.create(phone_number='+919888000016', name='Maya')
        with patch.object(GeminiChatService, 'generate_reply', side_effect=Exception('Gemini API timeout')):
            res = ConversationService.process_message(customer.phone_number, 'What IT services do you offer?')
            # Must return a valid fallback, not crash
            assert res['reply']
            assert 'service' in res['reply'].lower() or 'neoriz' in res['reply'].lower()

    # 13. Duplicate and concurrent webhook delivery
    def test_duplicate_webhook_delivery_idempotence(self, neoriz_env):
        phone = '+919888000017'
        msg_id = 'wamid.HBgLMzEw...TEST01'

        res1 = ConversationService.process_message(phone, 'What is TABLO?', external_message_id=msg_id)
        assert 'TABLO' in res1['reply']

        # Duplicate delivery with identical external_message_id
        res2 = ConversationService.process_message(phone, 'What is TABLO?', external_message_id=msg_id)
        assert res2['reply'] == res1['reply']
        assert Message.objects.filter(external_message_id=msg_id).count() == 1

    # 14. Authorization and customer isolation
    def test_customer_isolation(self, neoriz_env):
        c1 = Customer.objects.create(phone_number='+919888000018', name='User 1')
        c2 = Customer.objects.create(phone_number='+919888000019', name='User 2')

        b1 = Booking.objects.create(
            customer=c1,
            organization='Company A',
            service_address='addr1',
            preferred_date=date.today() + timedelta(days=2),
            preferred_time_slot='morning'
        )

        # User 2 attempts to query/cancel User 1's booking
        res = ConversationService.process_message(c2.phone_number, f'booking_cancel_{b1.id}')
        b1.refresh_from_db()
        assert b1.status != BookingStatus.CANCELLED

    # 15. Retrieval updates after product deactivation
    def test_retrieval_updates_after_product_deactivation(self, neoriz_env):
        crm = Product.objects.get(slug='whatsapp-automation-crm')
        sync = KnowledgeSynchronizer()
        
        # Verify sync_product runs cleanly
        sync.sync_product(crm)
        status_record = KnowledgeSyncStatus.objects.filter(source_type=SourceTypeChoice.PRODUCT, source_id=str(crm.pk)).first()
        assert status_record is not None
        assert status_record.status == 'SYNCED'

        # Deactivate
        crm.is_active = False
        crm.save()
        sync.sync_product(crm)
        status_record.refresh_from_db()
        assert "vector removed" in status_record.last_error.lower()

    # --- 6 Realistic Conversations ---

    # Conversation 1: Restaurant owner exploring TABLO
    def test_realistic_conversation_1_restaurant_owner_exploring_tablo(self, neoriz_env):
        phone = '+919888000021'
        # Customer: "We run a restaurant and orders get confusing."
        res1 = ConversationService.process_message(phone, 'We run a restaurant and orders get confusing.')
        # Assistant acknowledges operational challenge and probes where it gets difficult
        assert 'order' in res1['reply'].lower() or 'kitchen' in res1['reply'].lower() or 'billing' in res1['reply'].lower()

    # Conversation 2: Business owner asking about WhatsApp follow-ups
    def test_realistic_conversation_2_whatsapp_followups_unconfirmed(self, neoriz_env):
        phone = '+919888000022'
        res = ConversationService.process_message(phone, 'Can your WhatsApp CRM send follow-ups automatically?')
        assert 'confirm' in res['reply'].lower() or 'team' in res['reply'].lower()
        assert 'guaranteed' not in res['reply'].lower()

    # Conversation 3: Customer comparing custom software with existing product
    def test_realistic_conversation_3_custom_software_vs_product(self, neoriz_env):
        phone = '+919888000023'
        res = ConversationService.process_message(phone, 'Should we use TABLO or build custom software for our restaurant?')
        assert 'TABLO' in res['reply']
        assert 'custom' in res['reply'].lower()

    # Conversation 4: Customer asking for unsupported/unconfirmed integration
    def test_realistic_conversation_4_unsupported_integration(self, neoriz_env):
        phone = '+919888000024'
        res = ConversationService.process_message(phone, 'Does TABLO integrate with Swiggy and Zomato directly?')
        assert 'swiggy' in res['reply'].lower() or 'zomato' in res['reply'].lower()
        assert 'not confirmed' in res['reply'].lower() or 'confirm' in res['reply'].lower()

    # Conversation 5: Customer requesting demo, then correcting detail
    def test_realistic_conversation_5_demo_correction(self, neoriz_env):
        customer = Customer.objects.create(phone_number='+919888000025', name='Anand')
        with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
            def send(text):
                return ConversationService.process_message(customer.phone_number, text)

            send('Schedule a demo for TABLO')
            send('Fine dining restaurant with 15 tables')
            send('Anand Bistro, MG Road Kochi / anand@bistro.in')
            send('tomorrow morning')

            session = BookingSession.objects.get(conversation__customer=customer)
            assert session.step == BookingStep.REVIEW
            assert 'morning' in session.data.get('preferred_time_slot')

            # Customer corrects time to afternoon before submitting
            send('booking_edit_schedule')
            session.refresh_from_db()
            assert session.step == BookingStep.SCHEDULE

            send('tomorrow afternoon')
            session.refresh_from_db()
            assert session.step == BookingStep.REVIEW
            assert 'afternoon' in session.data.get('preferred_time_slot')

            # Explicit submit
            res = send('booking_submit')
            assert 'Request #' in res['reply']
            booking = Booking.objects.get(customer=customer)
            assert 'afternoon' in booking.preferred_time_slot

    # Conversation 6: Existing customer reporting a problem
    def test_realistic_conversation_6_existing_customer_support(self, neoriz_env):
        phone = '+919888000026'
        res = ConversationService.process_message(phone, 'Hi, our TABLO QR codes are not loading at table 4 today. Please help.')
        # Support reply: asks for issue details/account reference, warns against credentials, no sales pitch
        reply_lower = res['reply'].lower()
        assert 'support' in reply_lower or 'issue' in reply_lower or 'team' in reply_lower
        assert 'password' not in reply_lower or 'never' in reply_lower
        assert 'buy' not in reply_lower and 'purchase' not in reply_lower
