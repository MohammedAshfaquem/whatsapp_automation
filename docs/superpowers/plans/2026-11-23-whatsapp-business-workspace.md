# WhatsApp Business Messaging Workspace Implementation Plan

**Goal:** Transform the Neoriz WhatsApp Automation application into an official Meta WhatsApp Cloud API business messaging workspace with conversation initiation, strict 24-hour service window enforcement, robust Bot/Human mode boundaries, rich message attribution and status tracking, and a WhatsApp Business Profile management screen.

---

## 1. Gap Assessment

| Area | Current Implementation | Required Behavior & Gaps |
|---|---|---|
| **1. Start Conversations** | Only existing conversations are listed. No "New Chat" button or contact search/creation flow. | Add "New Chat" modal. Allow searching existing contacts or adding an international phone number (validated E.164). Respect Meta's 24h customer-service window: if window closed/new, require approved template selection with variable inputs. Avoid duplicate contacts/conversations. |
| **2. Bot vs Human Mode** | Backend supports `status = BOT_ACTIVE \| HUMAN_HANDOVER`, but manual reply did not enforce `HUMAN_HANDOVER` on the backend, and automated replies did not re-verify mode right before dispatch. | Server as source of truth. In Bot mode: manual reply composer disabled with clear "Switch to Human" affordance. In Human mode: bot replies suspended; mode re-checked atomically before dispatch. Repeated claims preserve `picked_up_at`. |
| **3. Messaging Experience** | Transcript shows text, timestamp, direction. Does not show delivery states (Sent, Delivered, Read, Failed), agent attribution, retry logic, drafts, or filtered views. | Expose agent username/display name on human messages. Link outbound WhatsApp messages to `WhatsAppDelivery` to display Sent (single tick), Delivered (double tick), Read (blue double tick), and Failed/Blocked (with retry). Preserve per-conversation drafts. Add filters: All, Mine, Unassigned, Bot Active, Human Support. |
| **4. WhatsApp Business Profile** | Settings page only allows configuring credentials (phone_number_id, token, secret). No profile management. | Add WhatsApp Business Profile settings: view/edit About (max 139), Description (max 512), Address (max 256), Email (max 128), Websites (up to 2), Vertical/Category. View read-only verified display name, display phone, quality rating, and messaging limit tier. |
| **5. CRM Integration** | Phase 2 Customer Context Panel built and verified. | Seamlessly integrate with Phase 2 context panel, retaining customer details, timeline, notes, deals, and tasks. |

---

## 2. Implementation Stages

### Stage 1: Backend WhatsApp Business Profile & Template APIs
- Add `WhatsAppBusinessProfile` model in `apps/whatsapp/models.py` (or cache fields) to store verified business profile metadata.
- Create `GET /api/settings/whatsapp/profile/` and `POST /api/settings/whatsapp/profile/` in `apps/tenants/spa_api.py`:
  - Validate field limits: `about` (139 chars), `description` (512 chars), `address` (256 chars), `email` (128 chars), `websites` (list up to 2), `vertical`.
  - If live Meta credentials exist, call Meta Graph API:
    - `GET /{phone-number-id}/whatsapp_business_profile`
    - `GET /{phone-number-id}?fields=verified_name,display_phone_number,quality_rating,code_verification_status,messaging_limit_tier`
    - `POST /{phone-number-id}/whatsapp_business_profile`
  - Fall back gracefully to local tenant database in simulated or offline environments.
  - Audit log updates.
- Create `GET /api/whatsapp/templates/` in `apps/tenants/spa_api.py`:
  - Returns approved WhatsApp templates for the tenant (seed standard defaults if empty).

### Stage 2: Backend New Chat & Bot/Human Mode Hardening
- Create `POST /api/inbox/conversations/start/` in `apps/tenants/spa_api.py`:
  - Input: `contact_id` or `phone_number` (+ `name`).
  - E.164 phone validation (strip non-digits, ensure country code, validate length 8–15 digits).
  - Find or create `Customer` and `Conversation` under tenant without duplicates.
  - Check 24-hour customer service window:
    - If window closed and `template_name` provided: dispatch template delivery.
    - If window closed and no template: return `window_open: false, requires_template: true`.
    - If window open and initial message text provided: dispatch text reply.
- Harden `apps/dashboard/views.py:conversation_action_api`:
  - Disallow `action='reply'` when `conversation.status == ConversationStatus.BOT_ACTIVE`.
  - Disallow `action='reply'` for non-assigned agents if chat is already claimed by someone else (unless superuser).
  - Add explicit action `switch_to_human` (sets status to `HUMAN_HANDOVER` and assigns current user if unassigned).
  - Concurrency guard in `apps/whatsapp/events.py` and `conversation_service.py`: before creating bot delivery, verify `conversation.status == BOT_ACTIVE`.
- Update `conversation_messages_api`:
  - Batch join/prefetch message delivery statuses from `WhatsAppDelivery`.
  - Return `author_name`, `delivery_status`, `delivery_error`, `delivery_id`, `is_window_open`, `window_expires_at`.

### Stage 3: Frontend WhatsApp Messaging Workspace (`InboxPage.tsx`)
- Add **"New Chat" Modal**:
  - Contact search input + "Create New Contact" tab.
  - International phone validation with instant feedback.
  - 24-Hour Service Window banner:
    - When closed: prompts user to select an approved Meta template, shows variable inputs and live template preview.
    - Consent disclaimer: *"Saving a contact does not imply messaging consent. Ensure recipient has opted in."*
- Add **Bot / Human Mode UI Enforcement**:
  - Prominent Mode Banner at top of chat:
    - When Bot Active: banner displays *"🤖 Bot Active: Automation is handling replies"* with button *"Switch to Human"*. Composer is locked with clear hint.
    - When Human Support: banner displays *"👤 Human Mode: Assigned to @staff"*, with button *"Resume Bot"*.
- Enrich **Message Thread**:
  - Message bubbles display sender attribution (`AI Assistant` vs `Agent Name` vs `Customer`).
  - Delivery ticks (Single tick = Sent, Double tick = Delivered, Blue double tick = Read, Red alert = Failed).
  - Safe inline "Retry" button on failed messages.
  - Preserve message drafts per conversation in component state.
- Add **Filters & Search**:
  - Tabs: `All`, `Mine`, `Unassigned`, `Bot Active`, `Human Support`.
  - Instant search filter for conversations.

### Stage 4: Frontend WhatsApp Business Profile Settings
- Add **WhatsApp Business Profile** tab/section in `SettingsPage.tsx`:
  - Profile Picture, About/Bio, Description, Address, Email, Websites, Vertical Category.
  - Read-only official Meta badges: Verified Display Name, Connected Number, Quality Rating, Messaging Tier.
  - Validation matching Meta limits (character counters).

### Stage 5: Testing, Verification & Scoped Deployment Package
- Write targeted backend tests in `tests/test_whatsapp_workspace.py`:
  - `test_start_new_chat_creates_contact_and_conversation_without_duplicates`
  - `test_start_chat_closed_window_requires_template`
  - `test_bot_mode_disallows_manual_agent_reply`
  - `test_switch_to_human_and_resume_bot_lifecycle`
  - `test_bot_does_not_dispatch_reply_if_switched_to_human_during_processing`
  - `test_whatsapp_business_profile_api_validation_and_update`
  - `test_tenant_isolation_on_new_chat_and_profile`
- Write frontend component tests in `frontend/tests-whatsapp-workspace.cjs`.
- Run full pytest suite, frontend build (`npm run build`), and system checks.
- Package release archive and prepare rollback instructions.
- Stop and request approval before deploying.
