"""Behavior checks for routes whose priority must survive code cleanup."""
import pytest

from apps.bookings.models import Booking, BookingSession, BookingStep
from apps.chatbot.conversation_service import ConversationService
from apps.chatbot.models import Conversation, Customer
from apps.services.models import Service


pytestmark = pytest.mark.django_db


@pytest.fixture
def conversation():
    customer = Customer.objects.create(phone_number='+919999111130', name='Afi')
    return Conversation.objects.create(customer=customer)


@pytest.mark.parametrize('kind,expected', [
    ('audio', 'cannot listen to audio'),
    ('video', 'cannot inspect it'),
    ('document', 'attachment is not supported'),
])
def test_attachment_never_fills_booking_name(conversation, kind, expected):
    session = BookingSession.objects.create(conversation=conversation, step=BookingStep.NAME)
    result = ConversationService.process_message(conversation.customer.phone_number, f'[attachment:{kind}]')
    session.refresh_from_db()
    assert expected in result['reply']
    assert session.step == BookingStep.NAME
    assert session.data == {}
    assert result['booking_id'] is None


def test_service_buttons_keep_selected_service_and_exact_price(conversation):
    service = Service.objects.create(name='AC inspection', price_amount=500)
    result = ConversationService.process_message(conversation.customer.phone_number, f'service_{service.pk}')
    assert [option['id'] for option in result['options']] == [f'check_price_{service.pk}', f'book_service_{service.pk}']
    result = ConversationService.process_message(conversation.customer.phone_number, f'check_price_{service.pk}')
    assert service.formatted_price in result['reply']
    assert [option['id'] for option in result['options']] == [f'book_service_{service.pk}', 'view_services']
    conversation.refresh_from_db()
    assert conversation.service == service


def test_menu_resets_booking_but_does_not_create_one(conversation):
    BookingSession.objects.create(conversation=conversation, step=BookingStep.ADDRESS)
    ConversationService.process_message(conversation.customer.phone_number, 'main menu')
    conversation.refresh_from_db()
    assert conversation.service is None
    assert not Booking.objects.exists()
    assert BookingSession.objects.get(conversation=conversation).step == BookingStep.CANCELLED


def test_cancellation_requires_explicit_confirmation_and_customer_ownership(conversation):
    booking = Booking.objects.create(customer=conversation.customer, service_address='House 12')
    result = ConversationService.process_message(conversation.customer.phone_number, f'cancel_booking_{booking.pk}')
    booking.refresh_from_db()
    assert booking.status == 'PENDING'
    assert result['options'][0]['id'] == f'confirm_cancel_{booking.pk}'
    other = Customer.objects.create(phone_number='+919999111131')
    ConversationService.process_message(other.phone_number, f'confirm_cancel_{booking.pk}')
    booking.refresh_from_db()
    assert booking.status == 'PENDING'
    ConversationService.process_message(conversation.customer.phone_number, f'confirm_cancel_{booking.pk}')
    booking.refresh_from_db()
    assert booking.status == 'CANCELLED'


def test_handover_takes_priority_over_attachment_and_menu(conversation):
    conversation.status = 'HUMAN_HANDOVER'
    conversation.save()
    for message in ('[attachment:audio]', 'main menu', 'hello'):
        result = ConversationService.process_message(conversation.customer.phone_number, message)
        assert result['reply'] == ''
        assert result['handover_required'] is True
        assert result['options'] is None
