from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.intent_service import IntentService
from apps.chatbot.language import say
from apps.chatbot.models import Customer, ChannelChoice
from apps.chatbot.prompts import get_system_instruction, get_booking_instruction
from apps.services.models import Service


@pytest.fixture
def it_business():
    with override_settings(BUSINESS_INDUSTRY='it'):
        call_command('configure_neoriz')
        yield


@pytest.mark.django_db
def test_catalog_is_idempotent_and_retains_historical_service(it_business):
    old = Service.objects.create(name='AC repair', price_amount=500)
    call_command('configure_neoriz')
    call_command('configure_neoriz')
    old.refresh_from_db()
    assert not old.is_active
    assert Service.objects.filter(is_active=True).count() == 6
    assert Service.objects.get(name='Website Development').formatted_price == 'Quote after requirements review'


@pytest.mark.django_db
def test_it_website_request_and_greeting_use_it_catalog(it_business):
    assert IntentService.find_matching_service('I need an ecommerce website').name == 'Ecommerce'
    assert IntentService.find_matching_service('revamp my website').name == 'Website Revamp'
    assert IntentService.find_matching_service('need an Android mobile app').name == 'Mobile App Development'
    response = ConversationService.process_message('+919999777101', 'Hi')
    assert 'Neoriz Solutions' in response['reply']
    assert 'IT project' in response['reply']
    response = ConversationService.process_message('+919999777101', 'price for a website')
    assert 'requirements' in response['reply']
    assert 'inspection' not in response['reply'].lower()


@pytest.mark.django_db
def test_it_consultation_completes_through_normal_chat(it_business):
    customer = Customer.objects.create(phone_number='+919999777102', name='Sam')
    service = Service.objects.get(name='Website Development')
    with patch.object(GeminiChatService, 'interpret_booking_turn', return_value=None):
        def send(text):
            return ConversationService.process_message(customer.phone_number, text)
        response = send(f'book_service_{service.pk}')
        assert 'requirements' in response['reply'].lower()
        response = send('I need a five page website for my cafe')
        session = BookingSession.objects.get(conversation__customer=customer)
        assert session.step == BookingStep.ADDRESS
        assert 'organization' in response['reply'].lower()
        response = send('sam@example.com')
        session.refresh_from_db()
        assert session.step == BookingStep.SCHEDULE
        send('tomorrow evening')
        session.refresh_from_db()
        assert session.step == BookingStep.REVIEW
        send('booking_submit')
    booking = Booking.objects.get(customer=customer)
    assert booking.status == 'PENDING'
    assert booking.ac_type == 'Project consultation'
    assert booking.service_address == 'sam@example.com'
    assert 'five page website' in booking.problem_description


@override_settings(BUSINESS_INDUSTRY='it')
@pytest.mark.parametrize('language', ['en', 'manglish', 'ml', 'hi'])
def test_it_prompts_are_not_air_conditioner_questions(language):
    assert 'IT services company' in get_system_instruction()
    assert 'project category' in get_booking_instruction()
    for key in ('greeting', 'details', 'identity', 'address', 'inspection_price', 'details_label'):
        assert 'AC' not in say(key, language)
