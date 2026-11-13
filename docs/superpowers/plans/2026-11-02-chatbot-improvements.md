# Chatbot improvements implementation plan

**Goal:** Implement the five improvements approved from the website review.
**Spec:** `docs/CHATBOT_IMPROVEMENT_REVIEW.md` and the user's request to implement all five priorities.
**Architecture:** Extend existing Django services and portal; structured model output proposes booking fields, code validates them, and only explicit review submission creates a booking. Persist provider readiness and human ownership without new dependencies.
**Constraints:** Keep text/images scope, existing customer authorization, original messages, delivery deduplication, and no automatic appointment confirmation. No new paid service. This workspace has no git repository, so worktree/commit steps do not apply.

## Tasks

1. AI readiness: failing tests for safe error classification, changed credentials, staff-only connection checks; implement persisted status in `apps/chatbot/ai_status.py`, model/migration, Gemini recording, dashboard endpoint and status panel. Credentials and raw provider errors never enter responses or saved diagnostics.
2. Booking extraction/corrections: failing dialogue and validation tests; extend interpreter schema/prompt, add focused `apps/bookings/booking_fields.py`, route structured updates before single-step fallbacks. Validate service/name/type/address/schedule, recompute first missing step, retain valid fields, keep review explicit. Include rich initial booking requests and free-text review corrections.
3. Handover ownership: failing authorization/conflict/lifecycle tests; add nullable assigned staff and picked-up time to Conversation, transactional claim/release/reply handling, clear ownership on resume, display owner in staff list/transcript. Preserve existing handover summaries and enrich with draft/missing step.
4. Dialogue coverage and verification: test typos, multilingual structured replies, side questions, incomplete/invalid fields, provider failure, and ownership boundaries. Provide an opt-in live dialogue evaluation command that cannot create customer bookings or send messages. Run full pytest, Django checks, migration drift check, JS syntax, migration against backed-up local SQLite. Document results and remaining live-provider limitations.

## Review focus

- A new date must not carry forward an inappropriate old time.
- A question/correction must never silently fill an address or symptom.
- A rich initial friend request must not lose its supplied details.
- Competing staff must not claim or reply over each other's assignment.
- Provider status must be scoped to current credentials/model and never disclose credentials.

## Progress

- Planning: complete. Proceeding within the implementation authorization already given.
- AI readiness: implemented; rejected-access, empty-response, unavailable-provider, changed-config, staff-only API, and dashboard tests passed.
- Structured booking fields: implemented in a focused validator; initial combined details, review corrections, out-of-order fields, date/time validation, private account ownership and explicit submission preserved.
- Human ownership: implemented with transactional staff pickup/release/conflict protection and owner visibility in staff queue/transcripts; bot resume clears assignment.
- Conversation evaluation: 25 fictional cases and an opt-in interpreter evaluation command. Offline listing verified; live evaluation not claimed because the last provider credential check failed.
- Ruling: a friend visit requires the recipient's name; an unnamed requester remains identified by their customer phone rather than being renamed or repeatedly prompted for a recipient name.
- Review: independent reviewer identified fresh-friend name loop, empty-name exception, and unpunctuated clarification fallback; each reproduced with a failing regression test and fixed. All 16 booking-field tests then passed.
- Migration: 0006 applied to local SQLite after `.backups/before-chatbot-improvements-20261103.sqlite3` was created using SQLite backup.
- Verification: Django checks and migration drift check passed; extracted dashboard JavaScript passed Node syntax check. Full test result is recorded below after final verification.
- Final verification: `.venv/Scripts/python.exe -m pytest -q --tb=short` completed with **263 passed**. No live provider-quality result is claimed. All five implementation tasks are complete.
