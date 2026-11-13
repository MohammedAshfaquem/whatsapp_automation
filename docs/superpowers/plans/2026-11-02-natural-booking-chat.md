# Natural booking chat implementation plan

User approved the sample conversation in chat. Native WhatsApp Flows and voice replies are deferred.

1. Add failing conversation tests for casual greetings, inspection quotes, separate AC type/problem collection, date/time across turns, context-preserving questions, quiet booking controls, and retry idempotency.
2. Fix the existing handlers and guided booking service. Keep state in the existing BookingSession JSON; do not add a model, framework, or AI dependency for booking validation.
3. Preserve price data, multilingual controls, booking review/editing, ownership checks, handover, image handling, date validation, and duplicate delivery protection.
4. Document behavior with sample dialogs and links to Google Conversation Design and Microsoft Fluent guidance.
5. Run targeted tests, the full suite, Django checks, and review the resulting changes.

Dates use the application's configured local timezone. Partial dates must not imply technician availability. A request becomes PENDING only after review and explicit submission. Attachments and greetings must not fill booking fields.

## Completed

- Added `docs/CHAT_BEHAVIOR.md` with the agreed dialogue, boundaries, design principles, and Google/Microsoft references.
- Corrected casual greetings, inspection quote wording, separate AC type/symptom collection, quiet data-entry controls, partial scheduling, business side questions, and stale schedule recovery. Website controls retain the collected type/day.
- Added 27 natural-conversation cases. Reproduced failing cases before fixing them. Full final suite: **173 passed**. Django system check and JavaScript syntax check passed.
- Independent review found capacity metadata mistaken for symptoms and expired review dates retained; both were covered with failing tests and corrected, then verified by the reviewer. A final regression check also covers a symptom description ending in a question mark.
- Webhook replay produced one outbound reply. The pasted live duplicate messages were not reproduced; the behavior guide explains the live identifiers needed if they recur. No broad suppression of identical text was added.
- No new dependencies, schema migrations, voice functionality, or native WhatsApp Flow integration.
