# Neoriz competitive module review and recommended product roadmap

Reviewed: 25 November 2026 (Asia/Kolkata).

## Scope and conclusion

This review compares the inspected Neoriz source and recent release records with the public product/help documentation of GetGabs, WATI, Interakt, AiSensy, respond.io, SleekFlow, Zoko, Manychat, Chatwoot and 360dialog Partner Hub. It is a representative market benchmark, not a claim to have tested every vendor or every paid plan. Vendor documentation describes advertised capabilities; account eligibility, plan restrictions and provider approvals still need verification during implementation.

Neoriz already has a useful foundation: tenant isolation, client/operator separation, activation, role/plan checks, shared WhatsApp inbox, bot/human handoff, contacts/companies/deals/tasks, service requests, grounded AI, business profile/photo management, approved text templates, scheduled broadcasts, consent records, durable deliveries and webhooks. The priority is to complete customer journeys and SaaS operations, rather than add more parallel menus.

Competitors' customer-facing administration must not be confused with their private SaaS operator consoles. Except for public partner-console examples such as 360dialog, the Super Admin recommendations below are Neoriz product/operational recommendations, not assertions about undocumented competitor internals.

This was a source/documentation review. It did not rerun every live workflow, authenticate to competitors' paid accounts, change application code or deploy features. Status terminology:

- **Existing:** implementation was found; this does not certify every operational edge case.
- **Partial:** the foundation exists, but the end-to-end capability is incomplete.
- **Not found:** no complete implementation was found in the inspected code/routes/UI.
- **Conditional:** depends on Meta, channel, account, region, business verification or access approval.

## 1. Patterns worth adopting

| Reference | Public product pattern | Recommended Neoriz application |
| --- | --- | --- |
| [GetGabs](https://getgabs.com/) | WhatsApp growth suite with broadcasts, visual conversation flows, drip sequences, forms, commerce and connectors. | Expand existing Broadcasts/Templates and Automation screens; add personalized audiences and genuine forms/integration workflows. |
| [WATI](https://www.wati.io/pricing-comparison/) | Marketing, team inbox, no-code automation, commerce, analytics, calling and coexistence capabilities. | Stronger agent operations, channel onboarding, campaign analytics and reusable messaging tools. |
| [WATI role documentation](https://support.wati.io/en/articles/11463020-understanding-different-roles-and-permissions-in-wati) | Distinct operational roles, including template, automation, billing and reporting access. | Add action-level custom roles inside the existing Team & Roles area. |
| [Interakt](https://www.interakt.shop/sales-crm/) | WhatsApp sales pipeline, lead assignment, custom data, campaigns and commerce. | Preserve the CRM already built; connect custom fields, segmentation and deal/order events to conversations. |
| [AiSensy](https://www.aisensy.com/features) | Broadcast marketing, visual chatbots, forms, catalog/payment experiences and acquisition tools. | Build campaign personalization, forms and lead-source tracking before a full advertising interface. |
| [respond.io](https://respond.io/) and [workflow documentation](https://respond.io/help/workflows/workflow-steps) | Multichannel customer journeys, routing and workflow steps including branches and waits. | One shared workflow engine with durable waits, reply events, assignment and failure paths. |
| [SleekFlow](https://help.sleekflow.io/en_US/getting-started/welcome-to-sleekflow) | Unified messaging, flow builders, AI, ticketing, mobile and analytics areas. | Consolidated navigation with capabilities implemented as tabs, not duplicated modules. |
| [Zoko](https://www.zoko.io/) | Shopify-focused conversations, catalog synchronization and checkout/order automation. | A genuine commerce connector before offering cart recovery or order-aware bots. |
| [Manychat](https://manychat.com/product/whatsapp) | Automated lead qualification, nurture and re-engagement across messaging journeys. | Reusable lead-capture entry points and trigger-based journeys. |
| [Chatwoot](https://www.chatwoot.com/features) | Support operations: shared queues, macros, canned replies, capacity, business hours, SLA and CSAT reporting. | Improve everyday agent productivity and service measurement within the existing inbox. |
| [360dialog Partner Hub](https://docs.360dialog.com/partner/partner-hub/overview) | Public example of a partner console for client/account onboarding, integration operations and billing. | A useful reference for Neoriz software operations, distinct from clients' customer messaging. |

These are patterns to evaluate, not a recommendation to duplicate each vendor's product or marketing claims.

## 2. Current implementation findings that affect the roadmap

1. **Campaign personalization is shared, not per recipient.** Campaign.template_parameters is a single list and the worker applies it to each selected contact. Audience filtering currently uses lifecycle and category-specific consent. Launch/schedule/pause/cancel and delivery tracking already exist; they should be extended. [Broadcast service](</C:/Ashfaq WA Auto/whatsapp_automation/apps/crm/broadcasts.py:28>), [campaign model](</C:/Ashfaq WA Auto/whatsapp_automation/apps/crm/models.py:1020>).
2. **External connectors are not complete integrations.** The API supplies Calendar, CRM and Commerce cards with UNCONFIGURED defaults and stored statuses. Signed outbound webhooks are real, but those cards do not prove OAuth, object synchronization or recovery jobs. [Connector API](</C:/Ashfaq WA Auto/whatsapp_automation/apps/tenants/spa_api.py:3743>).
3. **The workflow engine is a CRM rule engine.** Actions found include assignment, tasks, notes, onboarding checklists, stage changes and escalation tasks. A general message/send/wait/reply/branch conversational journey is not present in that action model. [Actions](</C:/Ashfaq WA Auto/whatsapp_automation/apps/crm/models.py:731>).
4. **Reports are basic counts.** Current reports aggregate conversations, deals, tasks and bookings; this is not a complete first-response/SLA/CSAT/campaign-attribution system. [Reports API](</C:/Ashfaq WA Auto/whatsapp_automation/apps/tenants/spa_api.py:2636>).
5. **Platform health needs semantic correction.** The stalled-leases metric filters processing_until greater than now, which counts active leases rather than expired ones. Historical failure totals also need separation from current incidents and failure rates. [Monitoring API](</C:/Ashfaq WA Auto/whatsapp_automation/apps/tenants/spa_api.py:3820>).
6. **Billing is not automated collections.** TenantSubscription manages approval, plan and validity dates. That is a foundation for billing, not a payment-gateway, invoice, renewal or reconciliation implementation. [Subscription model](</C:/Ashfaq WA Auto/whatsapp_automation/apps/tenants/models.py:306>).
7. **Broadcast entitlement is coupled to an unrelated module.** The growth capability requires scheduling_quotations. This previously hid broadcasts for a plan missing that module. Separate marketing entitlements from quotation/scheduling entitlements without adding duplicate menus. [Capability rule](</C:/Ashfaq WA Auto/whatsapp_automation/apps/tenants/capabilities.py:280>).
8. **Channel/number modeling is narrow.** The current client configuration selects a WhatsApp configuration through the tenant context and stores a phone/WABA pair; channels are WhatsApp and simulator. Multiple numbers and multiple providers require explicit connection identifiers throughout routing, conversations, credentials and quota handling. [Configuration](</C:/Ashfaq WA Auto/whatsapp_automation/apps/whatsapp/models.py:4>).
9. **Knowledge ingestion is primarily text.** The document model stores content text and the SPA creation endpoint takes title/content. A document label is not a finished PDF/website ingestion and synchronization pipeline. [Knowledge model](</C:/Ashfaq WA Auto/whatsapp_automation/apps/knowledge_base/models.py:32>).
10. **Security needs a product layer beyond existing authorization.** DRF's global permission default is AllowAny, although many views explicitly override it. Audit all intended public endpoints and make private access deny-by-default. Reviewed credential fields are ordinary model fields; document infrastructure encryption and add application-level secret management where required. MFA, scoped client developer tokens and a session-management console were not found. [DRF defaults](</C:/Ashfaq WA Auto/whatsapp_automation/config/settings.py:190>).
11. **Some functions exist outside the modern journey.** Legacy CSV import/export routes exist, but the current Contacts page has no complete import job wizard. Consolidate the implementation into the current UI rather than create a second contact manager.
12. **Inbox updates poll.** The UI polls approximately every five seconds. That can remain a fallback, while presence, notifications and lower-latency updates need a more complete realtime design. [Inbox polling](</C:/Ashfaq WA Auto/whatsapp_automation/frontend/src/pages/InboxPage.tsx:195>).

## 3. Client module gap matrix

P0 = essential onboarding/daily-use foundation. P1 = next competitive expansion. P2 = later or demand-driven. Priorities indicate recommended order, not a promise of effort or a claim every feature belongs in the initial plan.

| Client area | Current state | Recommended completion | Priority |
| --- | --- | --- | --- |
| Account onboarding and recovery | Activation/password setup and manual link generation exist. | Transactional activation email delivery status, resend/recovery, expiry guidance, invite progress and a complete setup checklist. | P0 |
| Meta connection | Manual credentials, verification gate, profile and photo exist. | Supported Embedded Signup, asset selection, callback completion, permissions diagnostics, reconnect/expiry alerts and actionable setup errors. | P0 |
| Multiple WhatsApp numbers | Current journey operates around a selected phone configuration. | Tenant connection/number directory, branch labels, default sender, number-specific templates/quality/routing, safe disconnect and migration workflows. | P1; design schema in P0 |
| Business App coexistence | Complete onboarding/support path not found. | Eligible-number coexistence onboarding, actual capability detection, history/event support and clear unsupported states. | P1 / conditional |
| Everyday inbox messaging | Text replies, takeover/assignment, transcript, delivery states exist; image/interactive handling exists in parts of the backend. | Manual image/document/audio/video sending and previews, recordings where supported, file download/retention, search, draft preservation across reloads and attachment errors. | P0 |
| Agent productivity | Notes, ownership and handoff foundations exist. | Saved replies, macros, mentions, snooze/reminders, inbox labels, agent presence/capacity and notification preferences. | P1 |
| Routing and service hours | Basic least-workload/round-robin assignment exists. | Teams/departments, skills/language routing, shift/business hours, holidays, availability, routing queues and timeout escalation. | P1 |
| Template library | BODY-text utility/marketing draft/submission/sync exist. | Rich headers/media/buttons, template previews/examples, language variants, rejection/quality reasons, categories, automatic status/quality webhook synchronization and lifecycle history. | P0 text/rich-media essentials; P1 advanced formats |
| Authentication messaging | Broadcasts correctly exclude authentication templates. | Separate OTP/authentication workflow with verification/expiry/rate limits; never route it through marketing broadcasts. | P2 / demand-driven |
| Broadcast audiences | Lifecycle/consent selection and frozen audiences exist. | Saved segments by tags/fields/activity, CSV mapping preview, per-recipient variable mapping, exclusions and validated consent evidence. | P0 |
| Campaign operations | Draft/launch/schedule/pause/cancel and recipient states exist. | Frequency caps, quiet hours, adaptive batching, test-send to consenting numbers, approval workflow, preflight and paginated/exportable results. Keep uncertain sends non-retryable without review. | P1 |
| Campaign optimization | Delivery/read counts exist. | Link/CTA tracking where feasible, conversion events, A/B tests, attribution and controlled retargeting of eligible recipients. | P1 |
| Automation journeys | Durable CRM event/action rules exist. | Visual multi-step builder with messages, conditions, durable waits, reply/timeouts, HTTP actions, failure paths, versioning and publish/rollback. | P1 |
| Chatbot design | Grounded assistant and guided booking paths exist. | Reusable conversation nodes, branches, reusable subflows, simulator coverage and state inspection. Share execution infrastructure with workflows. | P1 |
| WhatsApp Forms / Flows | A specific booking Flow integration exists. | General form design, validation, preview/publish, version history, secure data exchange and submission-to-CRM mapping. | P1 / conditional |
| AI workspace | Business-grounded AI and handoff summaries exist. | Per-client bot policies, reply copilot, approved tools/actions, citations/source inspection, confidence fallback, evaluations and AI usage limits. | P1 |
| Knowledge sources | FAQs/text documents and indexing exist. | PDF/file/URL ingestion, scheduled source sync, indexing progress/errors, provenance, deletion/unindexing and permission-aware retrieval. | P1 |
| CRM data | Contacts, companies, tags, lifecycle, deals and notes exist. | Typed custom fields, saved views/segments, bulk edits, unified import/export validation and reliable deduplication/merge experience. | P0/P1 |
| Sales and appointments | Deals, quotations, tasks and booking/service foundations exist. | Streamlined current-UI quote approval/delivery, booking calendar, configurable availability, reminder journeys and real external calendar sync. | P1 |
| Customer support | Basic tickets, internal notes and onboarding checklists exist. | Business-hours SLA timers, escalation, CSAT/NPS where appropriate, help-center/self-service and service quality reporting. | P1 |
| Commerce | Internal services catalog exists; actual external commerce connector is not complete. | Meta catalog/Shopify/WooCommerce sync, product cards, order status, checkout/payment links and reconciled order/payment events. | P2; prioritize earlier for retail clients |
| Commerce automation | Complete order/cart event integration not found. | Cart recovery, COD confirmation, shipping updates and post-purchase journeys after commerce data is reliable. | P2 |
| Lead acquisition | Complete acquisition attribution toolkit not found. | QR/wa.me/widget generation, campaign/source tags, CTWA referral ingestion, lead forms and opt-in/source capture. | P1 |
| Advertising | External Meta management links exist. | Start with attribution and account links; add in-app ad operations only after permissions, business demand and billing scope are established. | P2 / conditional |
| Integrations/developer tools | Signed outbound webhooks and session-backed app APIs exist. | Actual OAuth connectors, tenant-scoped developer keys/scopes, idempotency, rate limits, API docs, webhook history/replay and sync conflict handling. | P0 API boundary; P1 connectors |
| Analytics | Basic conversation/deal/task/booking and delivery totals exist. | Response/resolution times, agent/queue performance, SLA, bot containment/escalation, campaign outcomes and export/scheduled reporting. | P1 |
| Team access | Owner/Admin/Staff and seat/request controls exist. | Granular action roles, team-scoped visibility, template/campaign approvers, restricted exports and owner self-service invitations within plan limits. | P0/P1 |
| Subscription and costs | Usage/plan foundations exist. | Client subscription management, invoices/receipts, usage breakdowns, cost alerts and clear separation between Neoriz fees and Meta fees. | P0 |
| Notifications/mobile | Complete notification hub/native agent app not found. | In-app/browser/email notifications, mobile responsive inbox and later PWA/native push based on usage. | P1/P2 |
| Other channels and calling | Instagram/Messenger/calling adapters not found. | One shared customer profile/inbox with channel adapters; add calling when eligible and valuable. | P2 / conditional |
| Data controls | Basic audit/consent foundations exist. | Own-workspace exports, retention settings, customer erasure/export workflow, communication preferences and attachment governance. | P0/P1 |

## 4. Super Admin module gap matrix

Super Admin manages the Neoriz software service and its client accounts. Client phone credentials, business profiles, templates, bots and campaigns remain client-owned and client-scoped. Operator troubleshooting should use explicit, time-limited, audited inspection rather than silently opening tenant data.

| Operator area | Current state | Recommended completion | Priority |
| --- | --- | --- | --- |
| Client directory/lifecycle | Provisioning, activation links, status and inspection exist. | Trials, onboarding owner/checklist, renewal/grace states, suspension reasons, offboarding/archive and service history. | P0 |
| Plans and menus | Plans/bundles, overrides and bulk assignment exist. | Independent capability entitlements, plan versioning, upgrade/downgrade previews, overage policy and reliable published plan/menu consistency. | P0 |
| Subscription billing | Plan/status dates exist. | Gateway checkout/subscriptions, verified payment webhooks, invoices, refunds/credits, renewal reminders, failed-payment recovery and reconciliation. | P0 |
| Usage and cost ledger | Monthly message reservation/counting exists. | Append-only billable usage events for messages, AI, storage, agents/API resources; rollups, budgets and reconciliation with providers. | P0 |
| Platform integration configuration | Configuration is spread across settings/env/manual client setup. | Neoriz-owned app/OAuth infrastructure, callback configuration, provider versions, app-review/deprecation checklist and status monitoring. Keep client asset credentials in client scope. | P0 |
| Email/notifications infrastructure | Manual setup links exist; generic email plumbing is not a finished delivery console. | SMTP/provider configuration, branded templates, queue, retry, bounce/suppression handling, delivery evidence and operational alerts. | P0 |
| Operations and incidents | Aggregate counts and queue/lease foundations exist. | Correct health semantics, worker heartbeat/lag, tenant/provider error rates, dead-letter inspection, scoped safe replay and incident lifecycle. | P0 |
| Fairness and sending controls | Basic queues, quotas and campaign limits exist. | Separate priority for interactive replies/bulk jobs, per-tenant/number rate control, fair scheduling, provider backoff and circuit breakers. | P0 |
| Operator identities/security | Superusers and security audit exist. | Support/Billing/Operations roles, MFA, session revoke, login protection, least-privilege access and emergency access procedure. | P0 |
| Secret lifecycle | Credentials are masked in important interfaces, but application-level secret wrapping was not found. | Document infrastructure protection; managed/encrypted secrets, rotation, least-privilege retrieval and access audit. Verify claims rather than infer certification. | P0 |
| Backups and recovery | Deployment backups and rollback images exist. | Off-instance encrypted backups, restore drills, retention, recoverability evidence and defined recovery targets. | P0 |
| Privacy and compliance operations | Legal/consent/audit foundations exist. | Versioned legal acceptance, controlled exports/erasure, retention jobs, storage purges and incident/request tracking. | P0/P1 |
| Client support/success | Staff approvals exist; dedicated SaaS client support lifecycle was not found. | Client-facing support requests, onboarding assistance, ownership, escalation, subscription context and consented diagnostic access. This is separate from a client's customer ticketing. | P1 |
| Integration lifecycle | Connector cards and webhook foundation exist. | Global connector definitions, OAuth app lifecycle, scopes, version compatibility and credential-health rollups; per-client settings stay local. | P1 |
| Release/feature operations | Scripted deployment/rollback exists. | Staging/canary checks, tenant-targeted feature flags, migration visibility, change log, rollout approval and rollback evidence. | P1 |
| Business analytics | Tenant/user/message totals exist. | Active/paying/trial clients, activation funnel, churn/retention, recurring revenue from reconciled billing, cohort usage and gross-margin visibility. | P1 |
| Agency/reseller layer | Complete delegated reseller hierarchy not found. | Optional sub-account ownership, delegated client onboarding, branding and commercial settlements. Build only if that business model is selected. | P2 |
| Software configuration | Basic application/branding settings exist. | Central notification defaults, system quotas, status page, maintenance windows, localization and safe configuration audit. | P1 |

A prepaid wallet is a business-model decision, not a mandatory checkbox. Start with clear SaaS subscription billing and a truthful usage view. If clients pay Meta directly, do not represent subscription message counts as a Meta cash balance. Reconcile fee calculations against [Meta's actual pricing documentation](https://whatsappbusiness.com/products/platform-pricing/), rather than copied brochure rates.

## 5. Recommended menu structure

Expand existing modules and relocate overlapping screens. Avoid a new menu for every table, feature or connector.

### Client workspace

| Main menu | Pages/tabs |
| --- | --- |
| Overview | Setup progress, operating summary, actionable alerts |
| WhatsApp | Inbox; Campaigns & Templates; Automation & AI (workflows, bots, knowledge, forms, logs); Channels & Business Profile |
| CRM | Contacts & Companies; Deals & Quotes; Tasks & Appointments; Customer Support |
| Business | Products & Services; Orders & Payments; Integrations |
| Reports | Messaging/campaigns; agents/service; sales; bot outcomes; exports |
| Settings | Team & Roles; Workspace & Branding; Usage & Billing; Security; My Account |

Knowledge belongs in one AI/knowledge area, not repeated under Business and Automations. Campaign templates remain tabs within Campaigns & Templates. Consent is available from contact context and campaign audience tools using the same underlying records. Real Meta product catalogs can be linked from Products & Services without presenting the existing services list as an already-synced catalog.

### Super Admin console

| Main menu | Pages/tabs |
| --- | --- |
| Overview | Revenue/activation summaries, current incidents and platform health |
| Clients | Workspaces; onboarding; client support; explicitly audited inspection |
| Plans & Billing | Plans & menu entitlements; subscriptions; invoices/payments; usage ledger |
| Platform Operations | Workers/queues; provider health; incidents; releases; backup/restore |
| Security & Audit | Operator roles; sessions; audit trail; privacy/retention requests |
| System Settings | Platform integration infrastructure; transactional email; feature flags; software branding |

My Account can remain a profile action. Customer-facing business messaging belongs to clients; software provider configuration belongs to Super Admin. For example, Neoriz's shared Meta app/OAuth configuration is software infrastructure, while a client's number, business profile and template approvals are that client's assets.

## 6. Recommended implementation sequence and acceptance gates

### Phase A — Make client onboarding and the paid SaaS journey complete

- Correct the current entitlement and monitoring inconsistencies.
- Implement activation email delivery/recovery and invitation progress.
- Design connection/phone identities; implement supported Meta onboarding/reconnect.
- Add baseline operator security, secret lifecycle and private API defaults.
- Implement subscription payments and usage reconciliation; exercise restore/rollback.

Acceptance: a new independent client can be provisioned, receive/set credentials, connect only its own assets, see the correct menus, reach first-message readiness, manage its own staff and pay/renew. Another tenant cannot read/change its records. Failure/expiry/payment callbacks are idempotent and recoverable.

### Phase B — Make daily messaging and campaigns commercially useful

- Complete media composer, saved replies and notification basics.
- Expand templates to the required supported rich components.
- Add typed contact fields, saved segments, CSV variable mapping and recipient-specific personalization.
- Add consent-aware preflight, quiet hours/frequency caps, usable result pagination and export.

Acceptance: a named consenting test recipient receives the intended personalized message and supported attachment; provider callbacks update the same transcript. Unapproved templates, revoked consent and ambiguous duplicate sends are rejected. Campaigns respect tenant quotas and do not starve interactive replies.

### Phase C — Build automation and service depth

- Add a shared visual journey engine, not separate incompatible bot/workflow engines.
- Add durable wait/reply/timeout branches, test/publish/version/rollback.
- Generalize booking Flows into forms, source ingestion and governed AI/copilot tools.
- Add teams, hours/capacity, SLA and response-time analytics.

Acceptance: a real lead traverses a versioned form/journey, creates or updates its CRM record, reaches the correct available agent and exits safely on human takeover. Restarting workers does not duplicate actions or lose waits. Bot quality and operational performance can be measured.

### Phase D — Add one validated commerce/acquisition vertical

- Implement one real commerce or CRM connector first.
- Add order-aware messaging and cart recovery only after source events are reliable.
- Add QR/widget/referral source tracking and measured campaign outcomes.

Acceptance: connect a real test store/account, synchronize objects, process duplicate/out-of-order webhooks, recover from disconnect, and attribute a real consented lead/order to the correct client and campaign.

### Phase E — Expand by demand

- Instagram/Messenger, calling, advanced ad operations, native mobile and reseller features.
- Add OTP capabilities only when there is a clear authentication product requirement.

Acceptance depends on channel eligibility, permissions, data ownership and channel-specific testing. These modules should not delay the earlier paid-client journey.

## 7. Meta-specific implementation boundaries

Use the supported [Embedded Signup v4 documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/version-4). Meta documents the v2/v3 deprecation date as 15 October 2026; building a new integration against those older versions would be the wrong starting point for this review date.

[Meta's coexistence documentation](https://developers.facebook.com/documentation/business-messaging/whatsapp/embedded-signup/onboarding-business-app-users) describes onboarding eligible WhatsApp Business App customers while retaining app usage. It also documents evolving account identities. Model the client connection so onboarding responses and supported account changes do not require hard-coded assumptions about one legacy WABA/phone pair.

Coexistence, calls, commerce, authentication and advanced templates need supported account capabilities and proper review. A UI switch cannot itself confer those capabilities. Keep application subscription quotas distinct from Meta account limits, permissions, approval status and provider fees.

## Recommended next scope

Begin with Phase A and the Phase B messaging essentials. Specifically: onboarding/recovery, supported Meta connect, entitlement/monitoring corrections, media messaging, personalized campaigns and the billing/usage foundation. Preserve the current CRM and shared inbox rather than rebuilding them. Complete one measurable end-to-end client journey before expanding into advertising, omnichannel and a broad integration marketplace.
