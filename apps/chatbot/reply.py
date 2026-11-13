"""Internal handler result. The public API response is built by ConversationService."""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChatReply:
    text: str
    options: Optional[list] = None
    booking_id: Optional[int] = None
    handover_required: bool = False
    booking_context: Optional[list] = None
    offer_booking_form: bool = False
