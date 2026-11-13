# WhatsApp service workspace improvements

Goal: accurate, actionable customer replies and a professional interactive Django portal.

Design: retain Django templates and existing service data; use a navy navigation rail, teal actions, generous whitespace, and a responsive service workspace. Chat shows contextual choices, booking progress, review/edit/submit controls, recoverable errors, and human-readable option labels. No new frontend framework.

Implementation sequence:
- [x] Add regression coverage for booking validation, context changes, missing policies, private notes, access control, webhook deduplication and delivery failures.
- [x] Implement deterministic business replies, guided booking with date parsing and review, customer booking actions, and honest attachment handling.
- [x] Restrict management actions and simulator; make handover actionable and delivery state explicit.
- [x] Redesign shared navigation, dashboard, login and customer chat; connect contextual choices and progress to backend state.
- [x] Run the full suite, Django checks, migration checks and browser smoke tests.

Constraints: preserve existing data; use additive migrations; never send messages to real customers during verification. External WhatsApp delivery remains dependent on the configured account and credentials. Booking dates are preferences pending staff confirmation, not guaranteed available slots. Working hours are free text and cannot reliably support automated availability validation without a structured calendar.

Review focus: side questions must not fill booking fields; new service requests override previous context; customers cannot access other customers' records; repeated events must not resend successful replies; invalid schedules must not create bookings.

Environment: the original Python 3.11 virtual environment is broken. Create a separate Python 3.12 environment, leaving the original untouched. The directory is not a Git checkout; commit/worktree steps do not apply.

Verification: 97 tests passed using the isolated Python 3.12 environment. Django system checks and migration drift checks passed. Browser checks covered service selection, booking side questions, date/time controls, review/edit/submit, booking-list updates, human handover, automatic receipt of a staff reply, staff resume, and staff confirmation. Desktop and mobile layouts were inspected; the mobile page had no horizontal overflow.

Independent review: four additional issues reproduced with failing tests and fixed: staff account collisions, symptom/weekday routing, changing services during booking, and revalidating time at submission. Existing shop data was backed up to `.backups/` before applying additive migrations. Browser testing used `.preview.sqlite3` with live messaging disabled.

Operational setup: schedule `manage.py retry_whatsapp` if automatic queue retries are desired; configure an approved status template for messages outside the customer service window. These account/scheduler settings were not changed during development. Appointment availability and service-area coverage remain subject to staff confirmation because the existing business settings are free text.
