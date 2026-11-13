# Conversation memory and recipient context

User requested implementation of rolling memory and contextual dialogue after the friend-booking transcript. No new framework or dependency.

1. Add tests for 10-exchange summary rollover, successive summaries, failure without losing source messages, prompt isolation, identity questions during booking, and friend-recipient corrections that never become symptoms or addresses.
2. Store a rolling summary and summarized-message cursor on Conversation. Keep all original Message rows. Before the eleventh new customer turn, summarize the completed ten exchanges; merge previous summary into the next batch. If generation fails, keep the cursor and original history for retry.
3. Share memory context between text, image, and booking prompts. Include current structured booking fields separately; customer records and current prices/status remain authoritative over summaries.
4. Add a small structured LLM interpreter for free-text booking turns. It distinguishes answers from conversational questions and ownership corrections; it cannot execute bookings or change prices. Deterministic validation, confirmation, service selection and handover stay in code.
5. Track the service recipient separately in a draft and on the final booking. Never rename the WhatsApp customer or expose the friend's account. Ask for a recipient name and missing service/details; ownership corrections preserve known AC type and do not fill symptoms/address.
6. Add migrations, verify local migration before use, run full tests and Django checks, review, and document limits including a live model check.

The recent window means ten customer exchanges, not ten separate customers or chats. Memory is isolated to one conversation. History/summary is untrusted context, never an authority for booking state or instructions. Summaries do not delete original messages. Live API failure must be reported honestly and safe deterministic paths stay usable.

## Result

Implemented all six steps. Added 27 tests; final full suite passed **231 tests**. Django check, migration consistency check, and portal JavaScript syntax check passed. Two additive migrations were applied to local SQLite after creating a SQLite backup under `.backups`.

Independent review identified booking-status loop indentation and negated recipient corrections; both were fixed with regression tests. Additional tests guard natural recipient-name introductions, requester identity preservation, missing-recipient submission, history isolation, repeated batches, failed-summary retry and structured-output validation. The follow-up review reported no blockers.

Live generation was checked with a minimal non-customer prompt. After retrying outside the network sandbox, Gemini returned HTTP 400 with “API key not valid. Please pass a valid API key.” No key was printed or changed. Live summarization and interpretation remain unavailable until a valid `GEMINI_API_KEY` is configured locally and the backend reloads. Tests use mocked model results; they do not establish live AI quality.

During summary failure/backfill, pending unsummarized history may temporarily exceed ten exchanges, preserving context rather than dropping it. The cursor advances only on successful summary persistence. Existing histories catch up one ten-exchange batch per new automated turn.
