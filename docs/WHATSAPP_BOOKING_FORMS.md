# WhatsApp booking forms

WhatsApp-only native forms are implemented. The website portal is unchanged. No additional package or form provider is required. Gemini is not used to interpret form submissions.

## Customer journey

1. Choose the service and provide the AC type and problem as before.
2. At the address step, tap **Enter address** to open the native form. Fill house/flat, street, locality/town, six-digit PIN and an optional landmark.
3. Tap **Choose date** inside the form. Select a date from the calendar and morning, afternoon or evening. These are preferences; staff confirm availability.
4. Tap **Review request**. The complete form is validated and saved to the draft together. The chat displays the existing booking review.
5. Only **Submit Request** creates a pending booking. Form completion never confirms a technician visit.

If an address has already been typed in chat, the bot opens the scheduling screen directly. Customers can continue typing instead of opening the form. Cancel and team-support commands remain available. Unrelated replies, status lookups and booking-cancellation confirmation buttons are not replaced with forms.

## Meta draft and activation

Created and uploaded to the configured WABA:

- Flow ID: **1626358799035920**
- Meta status at validation: **DRAFT**
- Validation: **no errors reported** after connecting ADDRESS to SCHEDULE
- Publication and server activation: **pending**
- Live handset completion: **not yet verified**

Publication was subsequently authorized and attempted. Meta rejected it with HTTP 400 / code **139000**. A read-only account-health check still reports DRAFT with no JSON validation errors, and business health LIMITED with error **141010**: “The Business has not passed business verification.” Resolve business verification in Meta Business Settings, then retry. The local Flow ID was not enabled after the failed publication, and the server was not restarted unnecessarily.

Open this draft in WhatsApp Manager → Flows and preview both screens. Once it is published, add the following server setting and restart Django:

```dotenv
WHATSAPP_BOOKING_FLOW_ID=1626358799035920
```

Keep this setting blank to retain typed booking. Do not configure a draft or deprecated Flow ID for customer traffic. Use the existing Meta access token and WABA; managing Flows requires account permissions that allow Flow creation/upload/publication.

The uploadable source is `apps/whatsapp/flows/booking_details.json`. A static Flow connects its screens locally and returns the final response to the existing signed Meta webhook. No data-exchange endpoint or extra encryption keys are needed for this implementation. [WhatsApp Flows concepts](https://docs.aws.amazon.com/social-messaging/latest/userguide/managing-flows.html)

## Developer commands

Show the source path without network calls:

```powershell
.\.venv\Scripts\python.exe manage.py setup_booking_flow
```

Revalidate this draft after editing its JSON:

```powershell
.\.venv\Scripts\python.exe manage.py setup_booking_flow --flow-id 1626358799035920
```

For a different WABA, `--create` creates a new draft and uploads the source. It never publishes or modifies `.env`. If creation times out, inspect WhatsApp Manager before retrying so another draft is not accidentally created. Published Flows cannot be updated by this command; create a new draft for changes.

Read status and account health without publishing:

```powershell
.\.venv\Scripts\python.exe manage.py publish_booking_flow --flow-id 1626358799035920 --inspect
```

After the account blocker is resolved, publication and activation are already authorized by the user:

```powershell
.\.venv\Scripts\python.exe manage.py publish_booking_flow --flow-id 1626358799035920 --enable
```

This separate deployment command publishes only a validated draft, verifies PUBLISHED status and messaging health, and only then writes the local `.env` setting. It does not send customer messages. Reload Django after a successful activation.

Transport follows Meta's official Flow message and asset-upload formats. [Meta API examples](https://github.com/WhatsApp/WhatsApp-Flows-Tools/blob/main/postman/v1/whatsapp-cloud-api.postman_collection.json)

## Validation and safety

- Each form token is signed, expires after two hours and binds the customer, conversation, draft session, step and current draft revision.
- An old form cannot overwrite a typed correction, cancelled/completed draft, or a different customer's record. Typed address corrections invalidate old structured defaults.
- Dates are validated in the configured business timezone (Asia/Kolkata), up to 180 days ahead. Elapsed date/time preferences are rejected again at final booking submission.
- Address/schedule fields are checked before applying the combined update. Invalid responses retain the draft and allow a fresh form or typed correction.
- Replayed webhook IDs reuse the stored result and outbound delivery key. Form messages use the existing delivery queue and ambiguous-timeout handling.
- Human handover suppresses automatic form responses and draft updates until the bot is resumed.
- Raw `nfm_reply.response_json` is parsed as bounded structured input. It does not become a name, symptom, arbitrary command or Gemini prompt.

## Acceptance before live use

Preview and complete the form on a test WhatsApp handset. Verify new-booking address→calendar, typed-address→calendar, friend addresses, invalid PIN/date, cancel/back, old forms, typed fallback, review/edit, one explicit submission, handover, and delivery receipts. Meta JSON validation and mocked backend tests do not establish handset behavior.
