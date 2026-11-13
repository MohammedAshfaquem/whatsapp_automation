# WhatsApp booking forms implementation plan

**Goal:** Native WhatsApp address and calendar forms, using existing booking review/submission.
**Scope:** WhatsApp only, as selected by the user. No website edits or additional provider/package.
**Design:** One static Flow definition with connected ADDRESS (house/flat, street, locality, six-digit PIN, optional landmark) and SCHEDULE (date picker and morning/afternoon/evening preference) screens. Enter at SCHEDULE if an address is already collected. The terminal scheduling screen returns all fields through the existing authenticated Meta webhook. Code validates the combined update before saving; form completion never creates a booking. Time preferences remain subject to team confirmation.
**Activation:** An unset published Flow ID keeps typed booking unchanged. Supply an uploadable Flow JSON and deployment instructions; do not claim Meta validation/publication or live handset verification without evidence.

## Implementation

- [x] Add failing tests for WhatsApp-only flow offers, outgoing payload, structured submissions, server validation, replay, wrong customer, expired/stale forms, handover, and explicit final submission.
- [x] Add focused `apps/whatsapp/booking_flows.py`: signed two-hour tokens bound to customer/conversation/session/step/draft revision, form defaults, strict field validation, draft updates. No schema migration needed.
- [x] Connect Flow transport to the existing outbound queue and structured `nfm_reply` parsing to ConversationService, preserving deduplication and ordering.
- [x] Add versioned Flow JSON with DatePicker, required address fields, optional landmark and initial values/date limits from server data. Add environment settings and setup guide.
- [x] Verify focused/full tests, Django checks, drift check, and fresh review. Separate local evidence from external activation.

## Edge cases

Old forms cannot overwrite edits, new drafts, completed/cancelled bookings, or another person's booking. Replayed webhook IDs reuse the stored response. Invalid input retains the draft and allows correction. Human handover remains quiet. Native form payloads bypass Gemini interpretation. Secrets/tokens are not printed to the customer. Date validation uses Asia/Kolkata and is repeated before final submission.

## Results

- Initial failing flow tests reproduced missing feature paths; focused tests later passed.
- Independent code review found form offers replacing cancellation confirmation controls and stale structured address defaults. Added failing regressions, then fixed with explicit handler offer flags and source-address matching.
- Meta created draft **1626358799035920**. Initial upload rejected disconnected terminal screens; changed to connected ADDRESS→SCHEDULE with combined completion validation. Reuploaded to the same draft: **no validation errors reported**. No publication or server activation performed.
- Added offline-by-default setup command; explicit create/update uploads drafts only, never publishes or edits secrets.
- Final full suite: **317 passed**. Django check and migration drift check passed. No new dependency or schema migration.
- Remaining deployment step: customer-facing publication and setting the published Flow ID. Handset testing is separate from schema validation/backend tests.
- Publication approved by user. Added tested explicit publication/inspection command. Meta rejected the publication request (HTTP 400, 139000); read-only inspection confirms DRAFT with no schema errors and business health error141010 (business verification incomplete). Local activation did not run. Retry after account verification is resolved; no repeat publication approval is required.
