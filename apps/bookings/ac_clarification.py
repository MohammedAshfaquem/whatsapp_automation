"""Clarify short, uncertain AC-type answers without saving guesses as symptoms."""
import re
from difflib import get_close_matches

from apps.chatbot.language import say
from .models import BookingStep


def clarify_ac_type(session, message):
    from .booking_service import BookingService
    if session.step != BookingStep.AC_DETAILS or session.data.get('ac_type'):
        return None
    lang = session.conversation.customer.preferred_language
    normalized = message.strip().lower().strip('.!?')
    pending = session.data.get('pending_ac_type')
    if pending and normalized in ('yes', 'yes please', 'correct', 'yeah', 'no', 'nope'):
        session.data.pop('pending_ac_type')
        if normalized not in ('no', 'nope'):
            session.data['ac_type'] = pending
            if session.data.get('problem_description'):
                session.step = BookingStep.ADDRESS
        session.save(update_fields=['data', 'step', 'updated_at'])
        return say('clarify_ac_type', lang) if normalized in ('no', 'nope') else BookingService.prompt(session)
    types = ('window', 'split', 'inverter', 'cassette', 'tower', 'other')
    short_answer = re.sub(r'\bac\b', '', normalized).strip()
    if short_answer in types or normalized in ('not sure', 'dont know', "don't know", 'unknown'):
        if pending:
            session.data.pop('pending_ac_type')
            session.save(update_fields=['data', 'updated_at'])
        return None
    # Longer descriptions and recognizable symptoms keep their existing interpretation path.
    if not re.fullmatch(r'[a-z]{2,15}', short_answer) or re.search(
            r'cool|leak|noise|noisy|work|broken|smell|spark|trip|water|issue|problem', short_answer):
        return None
    matches = get_close_matches(short_answer, types, n=1, cutoff=0.8)
    if matches:
        session.data['pending_ac_type'] = matches[0].title() + ' AC'
        session.save(update_fields=['data', 'updated_at'])
        return say('guess_ac_type', lang).format(ac_type=session.data['pending_ac_type'])
    return say('clarify_ac_type', lang)
