"""Opt-in language checks using fictional chats; never sends messages or creates bookings."""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.chatbot.gemini_service import GeminiChatService
from apps.chatbot.prompts import build_rag_prompt


def matches_expected(actual, expected):
    """Compare extracted facts, allowing capitalization differences, not exact reply wording."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        if not expected:
            return not actual
        return all(key in actual and matches_expected(actual[key], value) for key, value in expected.items())
    if isinstance(expected, str):
        return isinstance(actual, str) and actual.casefold().strip() == expected.casefold().strip()
    return actual == expected


class Command(BaseCommand):
    help = 'List fictional dialogue checks, or run provider interpretation checks with --live. No customer messages are sent.'

    def add_arguments(self, parser):
        parser.add_argument('--live', action='store_true', help='Call the configured AI provider; provider usage limits apply.')
        parser.add_argument('--case', help='Run one named dialogue instead of the complete set.')

    def handle(self, *args, **options):
        path = Path(settings.BASE_DIR) / 'docs' / 'chatbot-dialogue-cases.json'
        cases = json.loads(path.read_text(encoding='utf-8'))
        if options['case']:
            cases = [case for case in cases if case['name'] == options['case']]
        if not cases:
            raise CommandError('No matching dialogue case.')
        if not options['live']:
            self.stdout.write(f'{len(cases)} dialogue cases available. Use --live to evaluate interpretation with the configured provider.')
            for case in cases:
                self.stdout.write(case['name'])
            return
        if not GeminiChatService.is_configured():
            raise CommandError('Configure the AI key before running live checks.')
        failures = 0
        for case in cases:
            draft = {'name': 'Ashfaque', 'service_name': 'AC repair', **case.get('draft', {})}
            history = []
            passed = True
            for turn in case['turns']:
                prompt = build_rag_prompt(customer_message=turn['message'], customer_name='Ashfaque',
                    business_summary=f'Fictional AC test shop. Server local time: {timezone.localtime().isoformat()}',
                    active_services_text='AC repair: exact price after inspection. Team confirms availability.',
                    retrieved_knowledge_text='No additional facts.', conversation_history=history,
                    booking_context=json.dumps({'step': 'AC_DETAILS', 'details': draft}, ensure_ascii=False))
                result = GeminiChatService.interpret_booking_turn(prompt)
                if result is None:
                    raise CommandError('Provider returned no usable interpretation. Check AI connection status before retrying.')
                passed = passed and matches_expected(result, turn['expected'])
                for field in result.get('clear_fields', []):
                    draft.pop(field, None)
                draft.update(result.get('fields', {}))
                if result['recipient'] in ('self', 'other'):
                    draft['booking_for_other'] = result['recipient'] == 'other'
                history.extend([{'direction': 'INBOUND', 'text': turn['message']},
                                {'direction': 'OUTBOUND', 'text': result['reply'] or 'Details noted in this evaluation.'}])
            failures += not passed
            self.stdout.write(f"{'PASS' if passed else 'FAIL'} {case['name']}")
        self.stdout.write(f'{len(cases) - failures}/{len(cases)} dialogue cases passed.')
        if failures:
            raise CommandError('Some language expectations failed. Inspect these cases before activation.')
