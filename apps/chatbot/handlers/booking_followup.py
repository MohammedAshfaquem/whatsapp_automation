"""Small, read-only follow-ups about the bookings just shown to this customer."""
import re

from apps.bookings.models import Booking, BookingStatus
from ..language import say, choice
from ..models import MessageDirection
from ..reply import ChatReply


def is_approval_question(message):
    normalized = message.strip().lower()
    return bool(re.search(r'\b(?:approv\w*|confirm\w*|contact|call)\b', normalized)
                and re.match(r'^(?:when|how long|how soon|will|would|could|can|is|has|have|any|approv|confirm)', normalized))


def generate_reply(message, conversation):
    reference = re.fullmatch(r'(?:booking\s*)?#(\d{1,10})[?!.]*', message.strip(), re.I)
    if not is_approval_question(message) and not reference:
        return None
    previous = conversation.messages.filter(direction=MessageDirection.OUTBOUND).order_by('-pk').first()
    context = previous.response_data.get('booking_context') if previous else None
    if not context:
        return None
    # Even persisted context IDs must be rechecked against the current customer.
    bookings = list(Booking.objects.filter(customer=conversation.customer, pk__in=context).order_by('-created_at', '-pk'))
    if reference:
        bookings = [item for item in bookings if item.pk == int(reference[1])]
    if not bookings:
        return None
    lang = conversation.customer.preferred_language
    options = [choice('booking status', 'status', lang), choice('talk to agent', 'human', lang)]
    if len(bookings) > 1:
        return ChatReply(say('which_booking_followup', lang), options=options,
                         booking_context=[item.pk for item in bookings])
    booking = bookings[0]
    if booking.status == BookingStatus.PENDING:
        answer = say('pending_booking_followup', lang).format(id=booking.pk)
    elif booking.status == BookingStatus.CONFIRMED:
        answer = say('confirmed_booking_followup', lang).format(id=booking.pk)
    else:
        answer = f'Booking #{booking.pk}: {booking.get_status_display()}. ' + say('inspection_team', lang)
    return ChatReply(answer, options=options, booking_context=[booking.pk])
