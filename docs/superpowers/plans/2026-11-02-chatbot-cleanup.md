# Chatbot cleanup implementation plan

**Goal:** Make message handling easier to follow while preserving all existing behavior.

**Architecture:** Keep persistence and routing in ConversationService. Use plain handler functions grouped by responsibility in one handlers package. Keep the existing prompts.py and Gemini client; no new framework, dependency, database table, or audio processing.

**Scope:** User authorized a small refactor with discretion about folders. Prefer focused Python modules over nested packages containing one file each.

1. Run the existing test suite and add characterization checks for routing priority, service controls, attachments, and booking actions before moving code.
2. Move text and image response generation into separate handlers. Keep public entry points stable.
3. Extract booking chat and service choices. Replace the large inline branch with explicit early-return routing and one small reply value object.
4. Keep message ordering, transactions, duplicate responses, handover, languages, pricing, booking review, and response fields unchanged.
5. Run the full suite, Django checks, and review handler dependencies. Document where each responsibility lives.

**Verification:** Existing tests plus routing characterization tests; external APIs remain mocked. No claim of new audio or website image-upload support.

## Result

All five steps completed. The baseline suite passed 139 tests; seven added routing checks passed before and after the refactor. The final full suite passed 146 tests, and `manage.py check` reported no issues. An independent read-only review against the saved original found no actionable regressions, including text/image generation, controls, persistence, handover, and booking ownership checks.

`_process_message` decreased from 359 to 132 lines. The conversation service decreased from 818 to 385 lines. Public message-processing entry points and response fields remain unchanged. No dependencies, database migrations, or new media capabilities were added.
