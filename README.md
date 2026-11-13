# AI-Powered WhatsApp Automation System for AC Service Shop

## Updated local workflow

Use the new Python 3.12 environment (`.venv`); the older `venv` points to a missing Python installation.

With `DJANGO_DEBUG=True`, the Gemini key and chat model explicitly set in this project's `.env` take priority over inherited terminal/IDE values. Restart Django after editing them and use the staff connection test. With debug disabled, deployment environment variables keep priority. Never paste an API key into chat or logs.

```powershell
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver
.\.venv\Scripts\python.exe -m pytest -q
```

The customer portal now provides service search, contextual actions, booking progress, AC details and date/time controls, review/edit/submit, and persisted conversations. Staff can review handoff summaries, reply personally, and resume the assistant from a conversation transcript. The simulator API requires a staff session; customers use their own authenticated portal.

Booking dates are preferences pending staff confirmation. Working hours and coverage are currently free-text business settings, so the application does not promise a slot or automated coverage validation.

Native WhatsApp address and calendar forms are implemented behind `WHATSAPP_BOOKING_FLOW_ID`. A validated Meta draft has been created; publication and activation are separate. See [WhatsApp booking forms](docs/WHATSAPP_BOOKING_FORMS.md) for the draft ID, setup and acceptance checks.

WhatsApp replies and booking status changes use a durable outbound queue visible under **Admin → WhatsApp deliveries**. Run the following command periodically (for example from your task scheduler) to retry pending or definitively failed deliveries, up to three attempts:

```powershell
.\.venv\Scripts\python.exe manage.py retry_whatsapp
```

`UNKNOWN` means the send may have reached WhatsApp; inspect it before retrying. `BLOCKED` needs staff attention. Status notifications outside the customer service window require `WHATSAPP_BOOKING_STATUS_TEMPLATE` and optionally `WHATSAPP_TEMPLATE_LANGUAGE` (default `en`). The approved template must accept two body parameters: booking reference and public status. Internal owner notes are never included. No templates are submitted for approval automatically.

For production, set `DJANGO_DEBUG=False`, explicit `DJANGO_ALLOWED_HOSTS`, a strong `DJANGO_SECRET_KEY`, and the Meta app secret. Enabled WhatsApp webhooks reject missing signatures. Local test data lives in `.preview.sqlite3`; database backups are in `.backups/`.

---

A modular, production-ready Python backend for an AC repair and mechanical service shop. It enables shop owners to manage services, prices, business info, FAQs, and bookings via Django Admin, and serves conversational customer requests using Retrieval-Augmented Generation (RAG) with Google Gemini and WhatsApp Cloud API.

---

## 1. Project Structure

```
wtspAutamation/
├── manage.py
├── pytest.ini
├── requirements.txt
├── docker-compose.yml
├── .env.example
├── .env
├── PROJECT_PLAN.md
├── ARCHITECTURE.md
├── README.md
├── config/
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/
│   ├── business/           # Business profile, hours, service areas, policies
│   ├── services/           # AC services, pricing types, database lookup helpers
│   ├── knowledge_base/     # FAQs, knowledge docs, vector sync tracker
│   ├── chatbot/            # Customers, conversations, messages, simulated chat API
│   ├── bookings/           # Booking model, owner confirm/reject workflows
│   └── whatsapp/           # Meta WhatsApp Cloud API webhooks & client
└── tests/
    ├── __init__.py
    ├── test_services.py
    ├── test_business.py
    ├── test_knowledge_base.py
    └── test_chatbot_and_bookings.py
```

---

## 2. Why Each App Exists

| App | Purpose & Responsibility |
|---|---|
| **`apps.business`** | Manages shop identity, contact details, working hours, coverage areas, brands, and policies in a single active profile. |
| **`apps.services`** | PostgreSQL source of truth for all AC services and dynamic pricing rules (`FIXED`, `STARTING_FROM`, `PRICE_RANGE`, `INSPECTION_REQUIRED`). |
| **`apps.knowledge_base`** | Admin-managed FAQs and policy documents. Tracks synchronization status (`KnowledgeSyncStatus`) with vector storage. |
| **`apps.chatbot`** | Records customers, conversations, and inbound/outbound messages. Handles bot active vs human handover states. |
| **`apps.bookings`** | Tracks customer service booking requests starting in `PENDING` status. Provides owner confirmation/rejection endpoints and admin actions. |
| **`apps.whatsapp`** | Integrates with Meta WhatsApp Cloud API (webhook verification, payload parsing, deduplication, and sending). |

---

## 3. Database Configuration

The application uses `dj-database-url` to support both **PostgreSQL** and **SQLite** without code changes:

- **PostgreSQL (Production / Docker):**
  Set `DATABASE_URL` in `.env`:
  ```bash
  DATABASE_URL=postgresql://postgres:postgrespassword@localhost:5432/ac_whatsapp_agent
  ```
  *(An optional `docker-compose.yml` is included to start a local PostgreSQL container with `docker compose up -d`)*

- **Zero-Dependency Local Testing (SQLite):**
  Default in `.env`:
  ```bash
  DATABASE_URL=sqlite:///db.sqlite3
  ```

---

## 4. Quick Start & Setup

### A. Environment & Virtualenv
```powershell
# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### B. Database Migrations
```powershell
python manage.py makemigrations
python manage.py migrate
```

### C. Seed Initial Data
Populates default Business Profile, sample AC services (General servicing, Gas filling, Installation, Repair, Uninstallation), FAQs, and policies:
```powershell
python manage.py seed_data
```

### D. Create Superuser (Admin Portal)
```powershell
python manage.py createsuperuser
```
*(A default admin user is pre-created in dev: `username: admin`, `password: adminpassword123`)*

---

## 5. Running the Application & Interactive Swagger UI

Start the local Django development server:
```powershell
python manage.py runserver
```

- **Interactive Swagger UI**: [http://localhost:8000/api/docs/](http://localhost:8000/api/docs/) or [http://localhost:8000/swagger/](http://localhost:8000/swagger/)
  *(You can test all endpoints directly in your browser with "Try it out", no Postman required!)*
- **ReDoc Documentation**: [http://localhost:8000/api/redoc/](http://localhost:8000/api/redoc/)
- **OpenAPI Schema (YAML)**: [http://localhost:8000/api/schema/](http://localhost:8000/api/schema/)
- **Django Admin Portal**: [http://localhost:8000/admin/](http://localhost:8000/admin/)
- **Services API**: [http://localhost:8000/api/services/](http://localhost:8000/api/services/)
- **Simulated Chat API**: [http://localhost:8000/api/chat/test/](http://localhost:8000/api/chat/test/)

---

## 6. How to Add & Manage AC Services in Django Admin

1. Open [http://localhost:8000/admin/](http://localhost:8000/admin/) and log in with your superuser credentials.
2. Click **AC Services** under **AC SERVICES & PRICING**.
3. Click **Add AC Service**.
4. Fill in:
   - **Name**: e.g. `AC PCB Repair & Diagnostics`
   - **Category**: e.g. `Repair`
   - **Price Type**:
     - `FIXED` (requires `Price Amount`)
     - `STARTING_FROM` (e.g. `₹500 onwards`)
     - `PRICE_RANGE` (requires both `Price Amount` and `Max Price`)
     - `INSPECTION_REQUIRED` (price is determined after inspection)
   - **Estimated Duration**: e.g. `1-2 hours`
   - **Is Active**: Checked (only active services appear in customer replies)
5. Click **Save**.

The chatbot automatically uses updated prices and services directly from PostgreSQL in real-time.

---

## 7. Running Tests

Run the full automated test suite using `pytest`:
```powershell
.\venv\Scripts\pytest
```
All 18 unit tests cover:
- Pricing validation & price type constraints
- Active/inactive service filtering
- Business profile single-active constraint & summaries
- FAQ & Knowledge document models
- Customer, conversation, and message models
- Human handover mode
- Booking creation and owner confirmation/rejection
- Simulated chat endpoint baseline

---

## 9. Django Admin Management Interface

Django Admin is the single management portal for the AC service shop owner:

1. **AC Services & Pricing** (`/admin/services/service/`):
   - Add/edit services, descriptions, categories, and estimated duration.
   - Configure pricing types (`STARTING_FROM`, `FIXED`, `PRICE_RANGE`, `INSPECTION_REQUIRED`).
   - Active/inactive toggles immediately update the chatbot's live responses.
2. **Business Profile** (`/admin/business/businessprofile/`):
   - Edit shop address, contact phone number, Google Maps link.
   - Manage working hours and scheduled holidays.
   - Update service areas, supported AC brands, and warranty policies.
3. **Customer Bookings** (`/admin/bookings/booking/`):
   - View all customer booking requests submitted through WhatsApp or test chat.
   - Change booking status (`PENDING` -> `CONFIRMED` / `REJECTED` / `COMPLETED`).
   - Add internal technician notes.
4. **Chatbot Conversations & Human Handover** (`/admin/chatbot/conversation/`):
   - Review complete conversational history with message direction inlines.
   - Switch status between `BOT_ACTIVE` and `HUMAN_HANDOVER` (pauses bot).
5. **WhatsApp Cloud API Configuration** (`/admin/whatsapp/whatsappconfig/`):
   - Configure Phone Number ID, WABA ID, Verify Token, Access Token, and Meta App Secret directly inside Django Admin without touching `.env`!
   - Master toggle to activate live WhatsApp messaging.
6. **WhatsApp Webhook Audit Logs** (`/admin/whatsapp/whatsappwebhooklog/`):
   - Trace all incoming Meta webhook payloads, message IDs, sender phone numbers, and processing status.

---

## 10. Meta WhatsApp Cloud API Setup

### Step 1: Configure Webhook in Meta App Dashboard
1. Go to your Meta Developer App (developers.facebook.com) > **WhatsApp** > **Configuration**.
2. Set Callback URL: `https://your-public-domain.com/api/whatsapp/webhook/` *(Use ngrok or Cloudflare tunnel for local testing)*.
3. Set Verify Token: The same string configured in your `.env` or Django Admin (`WHATSAPP_VERIFY_TOKEN`).
4. Click **Verify and Save**.
5. Under Webhook Fields, subscribe to **`messages`**.

### Step 2: Testing with Meta Test Number
- In Meta App Dashboard > **API Setup**, add your personal WhatsApp number as a recipient.
- Send a message like *"What is the price of AC gas filling?"* to the Meta test number.
- The system verifies the HMAC signature, loads the conversation, retrieves real-time pricing from PostgreSQL and ChromaDB, and replies automatically via WhatsApp!

### Incoming WhatsApp photos
- JPEG and PNG photos (up to 5 MB) are downloaded from Meta into memory and sent to the existing Gemini model with their caption, recent chat, and active services/prices.
- Configure `GEMINI_API_KEY` and an image-capable `GEMINI_CHAT_MODEL`, plus the WhatsApp access token. Image bytes are not saved to disk.
- The assistant is instructed to describe visible evidence, suggest a possible issue and an existing service, and ask for a description or clearer photo when inconclusive. A gas leak requires technician inspection; a photo cannot confirm it.
- Failed downloads or unavailable AI return a request to describe the issue. Photos do not advance booking steps, and the bot stays silent during human handover.
- This supports WhatsApp photos; the website chat remains text-only.

For conversation rules, example booking dialogs, and the design references used, see [Chatbot behavior guide](docs/CHAT_BEHAVIOR.md).

Conversation memory uses a persistent rolling summary after each ten completed exchanges, plus newer raw history. Text, image and booking-dialogue prompts share this context. Summaries preserve all original messages and retry safely on AI failure. Run `python manage.py migrate` when deploying the memory/recipient fields. Gemini requires a provider-valid API key; an `AIzaSy` prefix alone does not verify access. Bookings arranged for another person keep that recipient separate from the WhatsApp account owner.

---

## 11. Modern Frontend Admin Portal & RBAC

In addition to Django Admin and Swagger UI, the system includes a web portal at `http://localhost:8000/`:

### Key Features
1. **Glassmorphic Modern UI**:
   - Dark theme with Google Inter typography, emerald/indigo accents, and responsive layout.
2. **Role-Based Access Control (RBAC)**:
   - **Superadmin (`is_superuser=True`)**:
     - Can view all KPI metrics (Active Services, Customers, Bookings, System Users).
     - Can create and invite new team members (Staff or Admin) via the **Team & RBAC** tab.
     - Can add/toggle services and manage customer bookings.
   - **Staff Member (`is_staff=True`)**:
     - Can log in at `/login/`.
     - Can view dashboard metrics, add new AC services, and toggle service availability.
     - Can view WhatsApp customers, inspect chat transcripts, and confirm/reject bookings.
     - RBAC prevents staff members from viewing or creating other user accounts.
3. **Interactive WhatsApp Chat Inspector**:
   - One-click modal to inspect any customer's real-time conversational timeline (Customer messages vs AI Bot vs Human Support).
4. **Instant Vector Store Sync**:
   - Adding a new service automatically synchronizes it with the ChromaDB vector database so the WhatsApp AI bot can quote the new service and its price immediately!

"# whatsapp_automation" 
