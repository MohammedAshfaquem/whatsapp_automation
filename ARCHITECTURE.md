# System Architecture: AC Service WhatsApp Automation

## 1. Architectural Overview

The system is designed with a clean separation of concerns, separating relational persistence, vector retrieval, LLM generation, and messaging integrations.

```
                           +------------------------+
                           |  Customer (WhatsApp)   |
                           +-----------+------------+
                                       |
                                       v
                           +------------------------+
                           | Meta WhatsApp Cloud API|
                           +-----------+------------+
                                       |
                                       v Webhook
                           +------------------------+
                           | apps.whatsapp (Webhook)|
                           +-----------+------------+
                                       |
                                       v
+-----------------------+  +-----------+------------+  +-----------------------+
|  apps.chatbot (Views) |->| Conversation Manager   |<-| Postman / Test Client |
+-----------------------+  +-----------+------------+  +-----------------------+
                                       |
         +-----------------------------+-----------------------------+
         |                             |                             |
         v                             v                             v
+------------------+         +--------------------+        +--------------------+
| Intent Detection |         | Real-time Database |        | Semantic Retrieval |
|  & Slot-Filling  |         | (PostgreSQL / ORM) |        |    (ChromaDB)      |
+--------+---------+         +---------+----------+        +---------+----------+
         |                             |                             |
         |                             | Ground Truth Services       | Relevant Chunks
         |                             | & Active Pricing            | & Policies
         +-----------------------------+-----------------------------+
                                       |
                                       v
                         +----------------------------+
                         | Prompt Assembly & Guardrail|
                         +-------------+--------------+
                                       |
                                       v
                         +----------------------------+
                         |     Google Gemini LLM      |
                         +-------------+--------------+
                                       |
                                       v
                         +----------------------------+
                         | Outbound Reply Generation  |
                         | (WhatsApp / Simulated API) |
                         +----------------------------+
```

## 2. Core Components

### 2.1 PostgreSQL (Relational Source of Truth)
- **`apps.business`**: Manages business details, hours, coverage areas, warranty policies.
- **`apps.services`**: Source of truth for AC services and dynamic pricing (`FIXED`, `STARTING_FROM`, `PRICE_RANGE`, `INSPECTION_REQUIRED`). Pricing queries directly hit PostgreSQL to eliminate stale data.
- **`apps.knowledge_base`**: FAQs and documents editable via Django Admin. Tracks `KnowledgeSyncStatus` to synchronize changes to vector storage.
- **`apps.chatbot`**: Customer profiles, conversations (`BOT_ACTIVE`, `HUMAN_HANDOVER`, `CLOSED`), and raw inbound/outbound messages with idempotency keys.
- **`apps.bookings`**: Service booking requests created as `PENDING`, confirmed/rejected by the shop owner.

### Chatbot code layout

`ConversationService.process_message()` remains the entry point for WhatsApp and website chat. It serializes customer messages, handles duplicates and old events, loads the conversation, routes the message, and saves the response. `_route_message()` lists routing priority explicitly; `_build_controls()` adds shared buttons.

```text
apps/chatbot/
  conversation_service.py   Message lifecycle, routing, handover, shared controls
  handlers/
    text.py                 Business answers, knowledge retrieval, AI fallback
    image.py                Photo understanding and unclear-image fallback
    attachments.py          Audio, video, and unsupported-file responses
    booking.py              Chat during an active booking
    services.py             Service selection, price buttons, service menu
  prompts.py                Shared AI instructions and prompt construction
  gemini_service.py         Gemini API calls for text and images
  memory.py                 Persistent rolling summaries and recent exchanges
  reply.py                  Small internal result shared by handlers
```

Handlers are plain functions with explicit inputs. There is no handler registry, plugin framework, or inheritance hierarchy. `ChatReply` carries reply text, optional buttons, booking ID, and handover status; the conversation service builds the existing public response format. Booking validation and transitions remain in `apps.bookings`.

`memory.py` summarizes completed batches of ten customer exchanges into `Conversation.memory_summary`, recording the last summarized Message ID. Original messages remain stored. Failed summarization leaves the cursor unchanged and retains pending history. The shared context builder supplies summary, recent exchanges, current draft, and verified customer-owned records to text, image and structured booking-dialogue interpretation. Historical summaries never override current prices or booking records.

The booking interpreter returns only answer/conversation/recipient-correction classifications. It does not execute booking actions. Explicit confirmation and field validation remain in the booking service. `Booking.recipient_name` identifies a service recipient when someone else arranges the visit; the WhatsApp customer remains the owner. `docs/CHAT_BEHAVIOR.md` describes fallback behavior and the configured API-key validation issue found during live testing.

Handover is checked before media or commands. Images and unsupported attachments are handled before booking answers, so they cannot accidentally fill a name, address, or schedule. Audio currently asks the customer to type a description; add transcription in the attachment handler only when that feature is needed. Keep prompts in one file until their size justifies a package.

### 2.2 ChromaDB (Vector Store)
- Stores chunked embeddings of FAQs, service descriptions, and policy documents.
- Uses deterministic document IDs (`faq_<id>`, `service_<id>`, `doc_<id>`) to prevent duplicate embeddings.
- Filter metadata ensures inactive records are filtered out from semantic queries.

### 2.3 Google Gemini AI
- Embeddings: `text-embedding-004` generates semantic query and document vectors.
- Chat Completion: `GEMINI_CHAT_MODEL` (default `gemini-flash-latest`) generates text and image responses using the shared business instructions.

### 2.4 Django Admin
- Single unified portal for shop owners to manage services, update prices, answer customer bookings, and toggle human handover.
