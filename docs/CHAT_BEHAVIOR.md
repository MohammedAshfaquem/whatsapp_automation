# Chatbot behavior guide

This is the expected product behavior for the AC service assistant. The bot speaks warmly as an automated service assistant. It never pretends to be a technician or promises availability it cannot verify.

## Principles and references

- Ask one concrete question at a time. Keep turns brief and relevant. Accept multiple useful details when supplied together. [Google Conversation Design: learn about conversation](https://developers.google.com/assistant/conversation-design/learn-about-conversation).
- Acknowledge a preference naturally and continue; do not ask the customer to confirm every field. Review the full request before submission. [Google Conversation Design: confirmations](https://developers.google.com/assistant/conversation-design/confirmations).
- Ask only for missing information, keep task context, and give a specific next step when input cannot be used. [Microsoft Fluent: interaction behavior](https://fluent2.microsoft.design/content-engineering/design-interaction-behavior/).

These sources guide wording and interaction choices; they do not guarantee an AI response is correct. The booking flow validates data in code and uses the actual service records for prices.

## ChatMitra reference review

Reviewed the complete [Conversational Components guide](https://chatmitra.com/learn/messaging/conversational-components/) and relevant linked material. Its focus is the start of a chat: first-contact welcome, a few useful starters, and optional shortcut commands. It recommends avoiding repeated fresh greetings for returning visitors. For this product, starter choices should reflect real needs: service information, arranging a visit, and booking status. They supplement typed conversation rather than replace it. Platform-native pre-chat starters and slash-command configuration are distinct features; this reference review does not implement them.

The [auto-reply examples](https://chatmitra.com/blog/whatsapp-auto-reply-examples-small-business/) support natural wording, one consolidated reply and access to a person. Our application of that guidance: acknowledge the customer's correction, answer their question, then ask one missing detail. Do not copy example business hours, prices, response deadlines, or promises of availability into this shop's replies.

The [AI chatbot documentation](https://chatmitra.com/features/ai-chatbot/) distinguishes personality, recent history, memory duration and failure handling. Our ten-exchange batches normally represent about twenty customer/assistant messages, with summaries retained separately. This is our chosen design, not a universal required history length. A valid provider configuration and live dialogue testing remain necessary; prompt improvements cannot repair an invalid API key. No additional provider or paid subscription has been added.

The [Flows and Webviews guide](https://chatmitra.com/learn/messaging/whatsapp-flows-and-webviews/) describes structured forms for bookings. Native WhatsApp address/calendar forms are now implemented behind a published Flow ID; the Meta draft is validated but publication/activation remains pending. See `WHATSAPP_BOOKING_FORMS.md`. The website's existing controls are separate.

Examples specific to our assistant:

| Situation | Clear response pattern |
| --- | --- |
| A returning greeting | Welcome the customer back once and invite their request; preserve any unfinished draft. |
| “Not mine, my friend's AC” | Acknowledge the recipient correction; keep known AC details; ask only the missing recipient or issue. |
| “Who are you?” during booking | Identify the automated assistant before offering to continue. Do not save the question as a field. |
| A status question typed instead of tapped | Read the same customer-owned booking records. Do not start a new booking. |
| AI unavailable | Keep deterministic facts/controls usable and offer clarification or the team without inventing an answer. |

These are design references. Provider-specific product settings, prices and marketing claims are not copied as WhatsApp API requirements or implemented features.

## Conversation memory and AI availability

All original messages stay in the database. One exchange means a customer message plus its associated assistant/team replies. After ten completed exchanges, a new turn triggers a compact summary of that batch. The next batch merges into the previous summary. The summary and newer raw exchanges are supplied to text, image and booking-dialogue prompts through one shared context builder; the current customer message appears separately, once.

The summary cursor advances only after a valid generated summary is saved. If generation fails, retain the original summary, cursor and unsummarized messages for retry. Pending history can temporarily exceed ten exchanges during API failure or legacy-history catch-up; preserving context is preferable to silently discarding it. Memory never crosses conversation/customer boundaries.

Current booking fields and verified customer-owned booking records override old summaries. Historical prices, diagnoses or appointment statuses are not authoritative. Summaries/history are data, never instructions. Staff can still inspect all original messages.

Free-text booking turns may be interpreted by Gemini as a field answer, a conversational question, or an explicit recipient correction. Conversational replies do not fill fields or advance the draft. This interpreter cannot submit, confirm, cancel or reschedule bookings; validated code and explicit controls still perform those actions. Deterministic paths handle identity, basic corrections, dates, prices/status and handover when AI is unavailable.

An earlier live check returned HTTP 400 for an invalid key. On 4 November, diagnostics found that an inherited terminal/IDE key was overriding the newly edited `.env` key. Local debug configuration now prioritizes the project's explicit Gemini key/model; production retains deployment-environment priority. The latest alias returned temporary 503 responses; the local model was pinned to `gemini-3.5-flash-lite`, which passed a live connection probe and analysis of the latest received WhatsApp photo. Check the current staff connection status for future failures; a configured key alone is not proof of provider readiness. API secrets must not be pasted into chat or printed in logs.

## Booking for another person

Keep the WhatsApp customer as the requester and account owner. Store the service recipient separately in the draft and final booking, and show that recipient in review, status and staff records. A friend’s name must not rename the requester or give access to the friend’s account.

For “I want to book another service for my friend,” ask for the recipient’s name and missing service. Do not silently assume the friend wants the same service as the requester’s last booking. If they later say “Not mine, my friend’s AC,” acknowledge the correction, preserve the AC type already collected, and ask for only the missing recipient/detail. Ownership corrections are never symptoms or service addresses. Ask about “their AC” and the recipient’s address, rather than “your AC.”

“Who are you?” is answered as an identity question, including during a booking. It does not become a name, symptom or address. Original booking state stays intact until the customer supplies the missing information.

## Greetings

A first greeting welcomes the customer to the configured shop. A returning customer's greeting includes their name when known and welcomes them back. Casual greetings such as “hey bro” count as greetings without forcing slang into every answer. A greeting must not dump the selected service's price or diagnosis.

An unfinished booking is preserved: welcome the customer and offer Continue Booking, Start Fresh, or Talk to Team. Greetings never become names, symptoms, addresses, or times.

## Price enquiries

For a service with a numeric price, quote the current configured fixed price, starting price, or range. For inspection-based repair:

> For AC repair, we can give you an exact quote after a technician inspects the issue.

Show configured duration when present. Never call “Inspection required” a price. There is no separate inspection-fee field in the current service model, so the bot must not invent a fee or describe inspection as free. A separate configured fee would require an explicit supported representation before being quoted.

## AC complaints

A reported symptom is not automatically a price enquiry. Recognize common cooling complaints such as “my AC isn't cooling,” “doesn't get cold,” “blowing hot air,” and the reported “didnt get any cool” wording. Acknowledge poor cooling, explain that inspection is needed to identify the cause, and offer an active repair service. Do not label poor cooling as a confirmed gas leak or promise gas filling will fix it. If no repair service is listed, offer the team instead of inventing one. A generic “I have a problem with my AC” asks for the missing symptom.

These recognized complaints work without an AI response and do not increment the unknown-message escalation counter. Explicit booking, price, location, coverage, working-hours, payment, warranty, and human-support requests keep their existing routes. A complaint during AC-detail collection is saved as a symptom; during other booking steps it is answered without replacing the name, address, or schedule. See `tests/test_ac_problem_chat.py`.

## Booking dialogue

For a short unclear type such as “widow,” ask “Did you mean a Window AC?” and retain only a pending suggestion. Yes accepts it; no clears it and requests clarification. Unknown short type answers explain that the type was not understood instead of silently saving them as symptoms or repeating the original prompt. Exact types, recognizable symptoms, booking controls, and normal AI interpretation keep their existing paths.

With a working AI provider, the booking interpreter extracts multiple explicit details and corrections from one message, including an initial booking request. The validator accepts supported fields only, resolves active services from the database, checks names/type/address/schedule, and recomputes the first missing step. A correction at review edits the draft; it never submits the request. Changing the day clears an old time preference unless a new time is supplied too. Questions about configured prices and policies retain deterministic answers.

For friend visits, the recipient's name is required. A first-time requester may arrange the visit using their phone identity without supplying their own name; the recipient must never rename that requester. Invalid proposed values preserve valid existing fields. Empty model values cannot update identity. Obvious clarification questions are kept out of fallback name, address, and symptom collection even without a question mark.

Known names and the selected service are reused. Ask for the AC type, then the problem, then address, then visit preference. If type and problem arrive together, keep both and skip the redundant question. If the problem arrives first, keep it and ask only for the type. Explicit “not sure” is accepted as an unknown type for technician confirmation.

Example:

| Customer | Assistant behavior |
| --- | --- |
| Book a Visit | Start the selected service request; ask for AC type. Explain once that cancel and team support can be requested by typing. |
| I have window AC | Remember Window AC; ask what issue they are facing. |
| Not cooling | Remember the problem; ask for a complete service address. |
| House: Maliyekkal House / Street: VK Padi / PIN: 676306 | Preserve the multiline address; ask for the preferred visit date. |
| Could u come today? | Save today's date and ask what time would suit them. State that the team confirms availability. |
| 3 PM | If still in the future, show the full request for review. Do not create a booking yet. |
| Submit Request | Create one PENDING request and state that staff will confirm. |

## Dates and corrections

Selecting Another date (the `choose date` action, or its typed label) clears both the old day and old time preference before asking for a new date. If the customer then says Morning, retain only that preference and ask for the day; do not reuse the previously selected Today. This control bypasses AI booking interpretation.

Interpret today/tomorrow using Asia/Kolkata. An explicit date, relative day, or weekday may arrive separately from the time. Remember the first valid part and ask only for the missing part. Support AM/PM, 24-hour times, and morning/afternoon/evening preferences. The preset labels are preferences, not live technician slots.

Reject invalid dates, dates beyond 180 days, and elapsed times. A preferred day that expires overnight must be collected again. Revalidate the full schedule on submission. A price, shop-location, or working-hours question must not overwrite the preferred day. Answer the business question, then resume the missing booking detail.

## Booking status questions

After a booking lookup or submission, short approval questions such as “when it will approve?” use the IDs from the last reply's booking context, rechecked against the current customer and current database status. For a pending request, explain that the team will review it and contact the customer to confirm the visit; do not invent an approval time or resume an unfinished draft. Multiple displayed bookings require a booking reference before answering a specific approval question. An unrelated assistant reply clears this small follow-up context. This is a focused deterministic fallback, not general semantic intent routing.

“Booking list please,” “all my bookings,” “show my bookings,” and “appointment history” are existing-booking lookups, not new-booking requests. All-history queries use pages of five records with Older/Newer controls. “My last booking” selects only the most recent record; an unqualified Check Status retains the recent-three overview. Every page remains scoped to the current customer.

History/status lookup runs before active draft collection and does not call the AI interpreter or memory summarizer. It leaves an unfinished draft unchanged and does not append the missing AC/address/date question. Continue Booking is available as an explicit action. Booking changes and new-booking requests keep their separate paths.

The Check Status button and typed status questions use the same customer-owned booking lookup. Accept different word orders such as “what is the current status of my last booking,” “my booking current status,” and “any update on my appointment.” Treat status lookup before the new-booking route so the word “booking” alone cannot start a new request when the customer is asking for an update.

Allow close misspellings of booking/appointment only within a personal status question, including the reported “what is the current status my last booming.” Do not globally rewrite customer text. Preserve the original message in history. New bookings, change requests, and unrelated words such as cooking must not become status requests because of typo matching.

Status is read from the database at reply time, scoped to the current customer. Never ask the AI to invent booking state, expose another customer's booking, or create a new draft to answer a status question. These checks are in `tests/test_booking_status_language.py`.

## Controls and media

Do not describe a photo as unclear when the image service failed. Missing/unavailable media asks for a resend or description; a missing/rejected AI configuration or failed analysis explains that image analysis is unavailable and offers typed details/team support. Only an actual image-model assessment may ask for a clearer photo because the visual evidence is blurry or inconclusive. Check the staff AI connection status before diagnosing repeated image fallbacks as a customer photo-quality issue.

Keep name, AC-detail, and address turns free of repeated service/cancel/team button menus. Typing cancel or talk to team remains supported. Offer Today, Tomorrow, and Another date when a day is missing; offer future time-of-day preferences when time is missing. Keep Submit Request, Edit Details, and Cancel on review.

The website's existing AC and scheduling controls remain available, with collected type/day prefilled. WhatsApp can offer the native address→calendar form when a published Flow ID is configured; typed replies remain available. Valid form completion saves the draft and returns to review, without submitting a booking. Incoming photos keep their current image handler; unsupported audio/video requests a typed description. Attachments do not fill booking fields. During human handover, automated replies stop until resumed.

## Duplicate replies and checks

WhatsApp requests a native typing indicator before processing a new inbound message that the bot will answer. The request also marks that message as read. It uses a short, best-effort HTTP call; rejection or timeout cannot block the reply. Duplicates, ignored older messages, delivery/read callbacks, website chat and paused human handover do not trigger bot typing. There is no artificial waiting period. WhatsApp clears the indicator when a reply arrives or after its timeout, so it may be brief for quick deterministic replies. Set `WHATSAPP_TYPING_INDICATOR_ENABLED=False` to disable it. [Meta request example](https://www.postman.com/meta/whatsapp-business-platform/request/lhf0duq/send-typing-indicator-and-read-receipt)

One inbound WhatsApp message ID has one persisted response and one outbound delivery key. Replayed webhooks or failed-delivery retries reuse that response. Do not suppress distinct customer messages merely because they contain identical text. An ambiguous outbound timeout is not blindly resent.

Duplicate replies from the pasted conversation were not reproduced with webhook replay tests. If they recur live, compare inbound message IDs, outbound provider IDs, and running webhook consumers before changing deduplication behavior.

`tests/test_natural_booking_chat.py` exercises this guide, together with the existing booking, image, handover, authorization, and delivery tests.

## Staff connection checks and human pickup

The staff dashboard shows the last AI provider result for the current key/model configuration. Changing either invalidates the displayed readiness result. Test connection sends a small diagnostic request; normal provider calls also update the result and latency. Missing configuration, rejected access, unavailable provider, empty response, and successful connection have separate messages. Keys and raw provider errors are not exposed in diagnostics. Successful connection proves connectivity, not language quality.

Human support has a visible queue. Staff can pick up and release a chat; sending the first human reply also picks up an unassigned chat. Another staff member cannot claim, reply, or resume over the owner's assignment. A superuser may release or resume an assigned chat. Resuming the assistant clears ownership and pickup time. The handoff summary includes collected booking details and the next missing question. No callback deadline is invented.

`tests/test_booking_fields.py` checks complete booking transitions with mocked interpretation, including combined details, corrections, multilingual canonical fields, and provider failure. These tests verify application behavior, not live model accuracy.

List the 25 fictional language-evaluation dialogues without network calls:

```powershell
.\.venv\Scripts\python.exe manage.py evaluate_chatbot_dialogues
```

After testing provider readiness, opt in to a single live case or the full set:

```powershell
.\.venv\Scripts\python.exe manage.py evaluate_chatbot_dialogues --live --case combined-friend
.\.venv\Scripts\python.exe manage.py evaluate_chatbot_dialogues --live
```

Live evaluation checks the interpreter using fictional context and an in-memory draft/history. It creates no bookings and sends no customer messages; it does record provider readiness. It is not a WhatsApp delivery or complete production-flow test. Provider usage limits apply. A rejected credential must be corrected on the server before live evaluation can succeed.
