# Inbox and Customer Workspace Implementation Plan

> For agentic workers: execute task by task using superpowers:executing-plans or superpowers:subagent-driven-development. This document is a plan, not a completed implementation.

**Goal:** Give an authorized agent a reliable journey from an assigned enquiry to customer context, a safe reply, and a recorded next action.

**Architecture:** Extend existing React pages and Django APIs. Preserve the custom router, shared fetch client, authoritative backend capabilities, CRM domain services and durable WhatsApp delivery system. Fix API consumer contracts and state synchronization before adding customer-context presentation. Keep visual changes within the existing brand, component and token conventions.

**Tech stack:** Current Django/DRF, React 18, TypeScript, Vite, existing custom routing, Lucide and CSS. Do not add React Router, TanStack Query, Tailwind, a Node production server or new realtime infrastructure implicitly.

**Spec/evidence:** artifacts/INBOX-AUDIT-20261123T113757Z/inbox-customer-workspace-audit.md, source-evidence.json, gap-matrix.csv and numbered screenshots in that audit directory.

## Global constraints

- Preserve uncommitted work, historical records, shared authentication, Super Admin provisioning and the operator/client distinction.
- Meta account checks are postponed. No live customer messages, campaigns, email or external webhooks for testing.
- Use synthetic tenant/user IDs in a manifest; explicitly empty/disabled provider configuration; deactivate only those identities after verification.
- Menus are presentation. Preserve authentication, verified identity, membership, tenant/object scope, role/action, entitlement, subscription and pause checks on every API.
- Preserve human takeover/resume, durable delivery, usage reservations, UNKNOWN/BLOCKED rules, deduplication and leases. Do not introduce replay shortcuts.
- Reuse existing service/model/API contracts. Do not delete legacy templates without reference analysis. No schema change is assumed; justify one before implementing it.
- Do not persist messages, drafts, access tokens or session credentials in localStorage. Clear tenant/user-scoped UI state during switching/logout.
- Implementation/deployment requires its own verified change set; no work below has been implemented during the audit.

## Review focus

1. Paginated, empty, malformed and failing API responses must never blank the whole application or appear as an empty success.
2. Late responses after selecting another conversation/tenant must not overwrite the active thread/customer context.
3. Staff must understand ownership restrictions; UI action affordances must agree with existing authoritative server policy.
4. 390, 768, 1280 and 1600 pixel layouts must retain access to the message composer and workflow actions.
5. SIMULATED messages and provider deliveries must remain distinct; any template/send extension must preserve service-window and consent boundaries.

## Task 1: Repair frontend data contracts and error containment (G01/G02/G11)

Files:
- Modify frontend/src/types/index.ts: add TimelineEvent, TimelinePage, ContactDetailResponse and WorkQueueData interfaces matching existing API JSON.
- Modify frontend/src/pages/ContactsPage.tsx: remove selectedContact:any, render timeline.items, use total_count/page metadata and event.text/details rather than nonexistent event.description.
- Modify frontend/src/pages/WorkQueuePage.tsx: consume api.get<WorkQueueData>() directly, not res.data; render all category/count controls and distinguish pending/error/empty state.
- Add frontend/src/components/ErrorBoundary.tsx and apply to page content in frontend/src/App.tsx so one page failure has a visible recovery path.
- Add focused component tests alongside the affected pages and an appropriate frontend test command in package.json. If no runner exists, choose a Vite-compatible runner and test utilities, pin resolved dependencies in the lockfile, and verify against official documentation during implementation.

Interfaces: get_customer_timeline returns `{items,total_count,total_pages,page,page_size,has_next,has_previous}`; fetchApi and api.get return the JSON response body. Preserve those contracts rather than changing the shared client to match one consumer.

- [ ] Write a failing component test using an independently hand-written paginated response with a note, completed task and stage-change event; View Details must render all three without losing the shell.
- [ ] Write failing empty/error contact tests and a queue fixture with unanswered_count=0, no_action_deals_count=1 and total_actionable=1; the corresponding category and item must remain reachable.
- [ ] Run tests and observe the current render failure/hidden-category behavior before changing code.
- [ ] Implement typed adapters and explicit UI states; add a recoverable error boundary without masking data errors.
- [ ] Run component tests, TypeScript check and frontend build; verify actual browser contact detail/tabs and work queue against seeded production-shaped data.

Acceptance: populated and empty contact details render; visible counts agree with the API; a failed request displays a retry state instead of a blank screen or a false clear queue.

## Task 2: Make conversation ownership and freshness reliable (G03/G04/G08)

Files:
- Modify frontend/src/pages/InboxPage.tsx: store selectedConversationId; derive header from the current list/detail data instead of retaining a stale selected object.
- Modify frontend/src/types/index.ts: represent assigned_staff_id, assigned_staff_username, display name, stable updated timestamps and available_actions explicitly.
- Modify apps/tenants/spa_api.py chat_conversations_list_api and apps/dashboard/views.py transcript/action responses only as needed to expose those fields without secrets.
- Reuse existing can_perform_action and conversation ownership policy; centralize availability computation if several responses need it.
- Add tests/test_inbox_workspace_api.py plus component tests for action completion, conflict and out-of-order requests.

Interfaces: keep legacy `/conversations/<id>/messages/` and `/conversations/<id>/action/` compatible; add fields rather than changing existing display fields unexpectedly. Server-derived available_actions may include claim, release, pause, resume and reply under current policy; changing manager reassignment policy is a separate explicit task.

- [ ] Write failing tests proving claim success immediately changes header/assignee/actions, and 409 leaves current ownership intact with a visible explanation.
- [ ] Test user A → user B conversation switches where A's response arrives late; test tenant switching while fetches are outstanding.
- [ ] Implement canonical selection state, request cancellation/stale-response guards, and reload/reconciliation after mutations.
- [ ] Add a visible Refresh action and bounded 5–10 second refresh while the page is visible; pause when hidden, avoid overlapping requests, back off on errors and cancel on unmount/tenant switch.
- [ ] Preserve drafts in scoped component memory while switching threads; never carry a draft to a different tenant/contact accidentally.
- [ ] Verify a new seeded SIMULATED message appears in both list preview and selected transcript without reopening; verify no provider calls occur.

Acceptance: no stale Claim Chat control after success; displayed ownership agrees with persisted state; other-owned chats explain restrictions; an agent sees fresh work without manual navigation. SSE/WebSockets are not required for this phase.

## Task 3: Recover desktop/mobile access to core actions (G05/G12)

Files:
- Modify frontend/src/components/Layout/Shell.tsx and existing application stylesheet for responsive navigation.
- Modify InboxPage.tsx; extract ConversationList.tsx and ConversationThread.tsx under frontend/src/components/inbox/ if doing so reduces state/rendering complexity.
- Reuse current colors, spacing and Lucide icons. Do not introduce an unrelated visual redesign or new icon/asset system.

- [ ] Capture baseline viewport regressions at 390/768/1280/1600 with the existing source screenshots as visual references.
- [ ] Put the AI simulator behind a clearly labeled optional test tool or reuse its existing setup/knowledge destination. The normal agent workspace must prioritize the conversation and customer context.
- [ ] Make list/context panels collapsible; use list → thread → context navigation on narrow screens, with an obvious back action. Support long tenant/contact names.
- [ ] Make conversation rows native keyboard-operable controls; give search/composer/icon actions accessible names, visible focus and status announcements.
- [ ] For contact dialogs, implement role=dialog, aria-modal/name, Escape, focus containment and focus return; test after G01 is fixed.
- [ ] Verify no clipped composer or hidden claim/resume controls at each breakpoint; run keyboard and measured contrast checks for relevant controls. Do not claim WCAG compliance from screenshots alone.

Acceptance: agents can reach claim/reply/next-action controls at laptop and mobile sizes; layout changes preserve the existing product identity.

## Task 4: Bring existing customer context and next actions into the inbox (G06/G07)

Files:
- Add frontend/src/components/inbox/CustomerContextPanel.tsx and a small scoped customer data hook if useful.
- Reuse the typed detail/timeline presentation from Task 1 rather than making a second inconsistent customer model.
- Modify InboxPage.tsx and chat_conversations_list_api to expose tenant-scoped customer_id and a usable handoff summary.
- Reuse contact detail/notes, companies, deal creation, activities and ticket APIs; modify responses only if a verified required field is missing.
- Add a small custom-router URL helper in frontend/src/routing.ts if needed; update App.tsx and WorkQueuePage.tsx to support safe contact/deal/task deep links without replacing the router.

Proposed context: customer/company, lifecycle/score where permitted, conversation assignee, handoff summary, open deals, next pending activity, notes and relevant ticket information. Show only fields authorized for the active user.

- [ ] Write failing tests for opening the exact customer from an inbox conversation and queue item; test foreign IDs and tenant-switch resets.
- [ ] Present the existing handoff summary and customer context alongside the thread on wide screens and in an accessible drawer on small screens.
- [ ] Add explicit Internal note and Schedule follow-up actions using existing APIs. Notes must never create outgoing customer messages.
- [ ] Include note/task forms with clear related contact/deal, assignee, due date/timezone and validation; link the created activity back into the visible timeline and queue.
- [ ] Add Open customer / Open deal navigation preserving selected IDs through refresh/back/forward. Ensure App's custom path matching handles query parameters consistently.
- [ ] Reuse existing quote/PDF and support screens as linked actions; do not imply direct WhatsApp PDF delivery exists.

Acceptance: from an enquiry, an agent can see context, add an internal note and schedule a follow-up without losing the conversation. The note/task appears in the existing CRM timeline/queue with no duplicate identity or external send.

## Task 5: Present honest workload, reply-window and delivery states (G09/G13)

Files:
- Modify InboxPage.tsx, MessageItem/Conversation interfaces and the existing message/list API serializers.
- Reuse apps/whatsapp/models.py WhatsAppDelivery and current dispatch safeguards; keep provider calls outside long transactions.
- Extend backend tests for membership/ownership, closed windows, failed/blocked/unknown deliveries and configured/unconfigured channels.

- [ ] Define Mine, Unassigned, Team, Waiting and Closed with documented predicates. Waiting must not simply mean HUMAN_HANDOVER after an agent has replied.
- [ ] Do not display fabricated unread counts; use an actual read-state model only if a separately justified requirement needs one.
- [ ] Expose processing status separately from provider delivery state and show sender identity for human replies. Batch delivery lookup to avoid per-message queries and never expose raw tokens/errors.
- [ ] For WHATSAPP, show service-window availability and a clear server-validated send restriction. For SIMULATED, label the composer/reply as simulated and never create a WhatsApp delivery.
- [ ] If implementing approved-template selection, add explicit tenant-scoped approved-template APIs/action permission and tests first; preserve consent and current subscription/usage controls. Do not implement arbitrary out-of-window free-text sends.
- [ ] Preserve UNKNOWN and BLOCKED staff-review behavior; no blind Retry action. Live provider acceptance stays BLOCKED until controlled recipients and explicit send authorization are available.

Acceptance: counts and labels reflect real work; staff understand whether a reply was saved, queued, sent, delivered, blocked or uncertain. Provider-sensitive extensions can follow the core workspace repair as a separately verified increment.

## Task 6: Make the normal entry point and errors consistent (G10/G11)

Files:
- Inspect existing authentication/dashboard routes and redirects in apps/dashboard/views.py, apps/tenants/signup_views.py and App.tsx.
- Modify only the verified default post-login destination and relevant links; retain public/auth/legal/Admin/fallback templates unless reference analysis authorizes removal.

- [ ] Write regressions for owner/staff default login, explicit safe next URLs, multi-tenant selection and Super Admin platform context.
- [ ] Route supported client daily work into the SPA without changing account usernames/passwords or dropping inspection context.
- [ ] Remove unrelated default business wording from active follow-up affordances using tenant-approved details; do not invent contact information.
- [ ] Ensure stale session, forbidden action and network failures have clear inline recovery and preserve unsent drafts appropriately.

Acceptance: agents enter the intended workspace consistently, while Super Admin and client contexts remain separate and historical routes retain defined behavior.

## Task 7: Acceptance, cleanup and deployment handoff

- [ ] Run component/contract tests, full Django suite, Django checks and frontend build. A successful build alone is not frontend workflow acceptance.
- [ ] Fresh browser journey: owner/staff login → find Mine/Unassigned → claim → see handoff/customer → add internal note → schedule next activity → see queue/timeline → safe simulated reply → see fresh inbound message.
- [ ] Verify foreign-tenant denial, another agent's ownership conflict, unavailable plan capabilities, revoked membership and stale request cancellation.
- [ ] Capture each important desktop/mobile step, including loading/error/empty and conflict recovery; inspect screenshots and record actual outcomes without promoting blocked cases to PASS.
- [ ] Preserve manifest IDs, disable only synthetic accounts/workspaces/rules and verify no synthetic send queues or enabled provider configurations remain.
- [ ] Review the exact production diff, create database/code/image rollback artifacts and deploy only the approved change set. No deployment is part of the current audit task.
- [ ] Recheck live UI/API contracts after deployment. Keep controlled provider and full-worker-origin E2E boundaries separately labeled.

## Completion gates

Phase A (Tasks 1–3): repair the daily-work blockers and responsive access. Phase B (Task 4): connect existing customer/CRM capabilities into the inbox. Phase C (Tasks 5–6): guided operational states and consistent entry. Task 7 applies to each release increment. Estimates and commercial commitments require a separate assessment; none are promised here.
