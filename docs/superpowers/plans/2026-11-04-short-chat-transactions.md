# Short chat transactions and safe webhook retries

**Problem:** ConversationService holds a database transaction across typing, media downloads, retrieval and Gemini calls. SQLite blocks concurrent writers, and the webhook's error-log write can fail too. Provider 503/504 failures are separate, but prolong this contention.

**Approach:** Receive/persist the inbound message, prepare slow AI results outside the write transaction, then atomically apply validated state changes and save the exact reply. Use a short database-backed per-customer processing lease to serialize turns across processes without holding a database lock during HTTP calls. Existing short booking transactions and response deduplication remain.

**Constraints:** No new service/package or database replacement. No customer-message sending for diagnosis. Preserve all existing booking, image, handover, form, account-access and idempotency behavior. Failed/uncompleted inbound IDs must resume safely; only a committed response is considered complete.

## Work

- [x] Reproduce blocked concurrent writes, unsafe interrupted-message recovery, and error-log save failure in tests.
- [x] Add customer processing lease fields/helper, bounded lease with safe release, retryable busy errors.
- [x] Add a small PreparedTurn object; prepare text/photo/booking interpretation and memory outside write transactions. Apply business state and response together in a short final transaction.
- [x] Make failed webhook processing return503 for retry; error-log persistence failure must not cause a second unhandled exception. Keep definitive outbound failures in the existing durable delivery queue.
- [x] Configure SQLite's short atomic sections with IMMEDIATE transactions and a bounded busy timeout. Keep PostgreSQL configuration untouched.
- [x] Run full regression and concurrency tests, review, back up SQLite, apply additive migration, and record practical limits.

## Review focus

No network operation may run inside the final write transaction. A completed booking must never be applied twice after interruption. A customer's busy lease must not serialize unrelated customers. Human handover initiated during AI preparation must suppress the prepared bot answer. Expired/crashed leases must recover, and an old owner must not clear a newer owner's lease.

## Result and operational limits

- Full suite: **357 passed**; Django system check passes. Local SQLite was backed up before applying migrations 0007 and 0008. Test output: `artifacts/chatbot-full-tests.txt`.
- AI preparation runs outside write transactions. Final booking/state changes and the exact inbound/outbound response commit together. A three-minute customer lease expires after a crashed process; finalization and memory updates check ownership. Unrelated customers can write while a provider call waits.
- A persisted unfinished inbound with an external ID deliberately blocks later turns for that customer until the original event retries. This preserves booking order across interruptions. If retries stop after a persistent application failure, staff must inspect the webhook log and recover the original event; do not blindly delete pending messages or resubmit bookings.
- Completed external IDs replay before the timestamp guard. An interrupted message stays attached to its original conversation; staff closing it suppresses further bot actions.
- Webhook processing failures return 503 for provider retry. A failure to write the error log is logged to the server without causing a second unhandled exception. The existing outbound delivery queue retains its own delivery rules.
- Provider 503/504 errors remain possible. Gemini generation has a 20-second HTTP timeout and one attempt per call; it uses the existing fallback when unavailable. Conversation summarization can be a separate call. No extra service, dependency, or paid provider was added.
- A fresh minimal provider probe returned READY for the configured `gemini-3.5-flash-lite`; no WhatsApp reply was sent by the probe. This is a point-in-time result, not an availability guarantee.
- SQLite still permits one writer at a time. Short IMMEDIATE transactions with a 20-second busy timeout address this specific long-lock failure; they do not turn SQLite into a multi-writer production database.
