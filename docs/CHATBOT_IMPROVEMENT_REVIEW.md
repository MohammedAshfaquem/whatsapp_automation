# Chatbot improvement review

Reviewed 2 November 2026. This is a comparison of broader ChatMitra guidance with our implementation, not a claim that every ChatMitra feature is needed. No runtime behavior changed in this review.

Implementation follow-up: the five approved priorities are now implemented in code: persisted AI readiness and staff testing, validated multi-field extraction/corrections, expanded conversation regression tests plus an opt-in live evaluation set, and staff handover pickup/release controls. The sections below preserve the original review and rationale. Live model quality still needs evaluation with accepted provider credentials; mocked application tests are separate evidence. Operational metrics, rate limits, native forms, and extra providers outside these five priorities remain proposals.

## What we should keep

Our separate text/image handlers, shared conversation context, rolling memory, service knowledge retrieval, database-backed booking status, booking review, customer ownership checks, human handover, and delivery deduplication are useful foundations. Keep these rather than introducing another framework. Buttons should remain shortcuts to actions customers can also request in text.

ChatMitra describes combining fixed paths with AI interpretation and human support. That supports our architecture, but does not establish that our current language handling is complete. [AI agent versus chatbot](https://chatmitra.com/blog/whatsapp-ai-agent-vs-chatbot/)

## Recommended priorities

### 1. Make AI readiness visible

ChatMitra describes testing provider credentials during setup and testing the chatbot before activation. [AI chatbot setup](https://chatmitra.com/features/ai-chatbot/)

Our `GeminiChatService.is_configured()` checks the key's shape, not whether the provider accepts it. The last live check rejected the configured key. A rejected credential must be reported to staff as a configuration problem, rather than appearing as a customer misunderstanding.

Add a small staff-only connection test and readiness result. Distinguish invalid credentials, temporary provider errors, and genuinely unclear customer input. Preserve the draft during failures and retain available deterministic actions. Do not send raw provider errors to customers. Fixing credentials is a prerequisite for evaluating live text interpretation, summaries, and images.

### 2. Understand details before advancing the booking

ChatMitra's lead-collection guide separates field extraction from business rules, accepts information outside the expected order, and leaves missing facts empty. [AI lead collection](https://chatmitra.com/blog/qualify-whatsapp-leads-with-ai-agent/)

Our interpreter currently classifies an answer, conversation, or recipient correction. Much of the subsequent field collection still parses the original text with rules. History alone cannot resolve this limitation.

Extend the existing structured interpreter to propose explicit field values and corrections. Let `BookingService` validate and apply them. Unknown values stay empty; a conversational question must never become a symptom or address. Keep customer account access and final booking creation controlled by code.

Example, after AC repair is selected:

> Customer: It's for my friend John, Window AC, not cooling, tomorrow evening.
>
> Assistant: Got it—AC repair for John's Window AC, which isn't cooling. What is the complete service address?

Capture the supplied recipient, type, issue, and visit preference. Do not ask them again. Availability remains subject to team confirmation.

### 3. Test whole conversations with a working model

The same lead-collection guide recommends a 20–30-dialogue trial, including vague replies, information supplied together, interruptions, mixed language, and requests for a person. [Dialogue testing guidance](https://chatmitra.com/blog/qualify-whatsapp-leads-with-ai-agent/)

Use the customer's reported chats as regression cases. Check saved fields, skipped questions, customer ownership, and actions—not exact generated wording. Retain the automated tests, but distinguish mocked provider checks from live language-quality checks.

Minimum acceptance cases:

| Input or sequence | Required behavior |
| --- | --- |
| “didnt get any cool whenthe temparture in 16” | Recognize poor cooling; avoid a confirmed gas-leak diagnosis. |
| “status my last booming” | Look up this customer's booking; do not start another request. |
| “Not mine, my friend's AC” | Correct recipient context; preserve known AC details. |
| “Who are u?” during address collection | Answer identity; keep the address missing. |
| “could u come today?” then “evening” | Collect date and preference; do not promise a slot. |
| “Actually tomorrow, not today” | Replace the date; revalidate the schedule. |
| Price question during booking | Answer using configured pricing; preserve the draft. |
| Unclear photo | Ask for a clearer photo or description; do not invent a visible fault. |

### 4. Tighten the prompt using examples

ChatMitra recommends separating identity, instructions, examples, and business facts, with concrete limits and explicit escalation triggers. [Prompt-writing guide](https://chatmitra.com/blog/ai-prompts-for-whatsapp-chatbots/)

Audit our existing prompt for repeated or conflicting instructions before adding more. Include a few short examples from these AC-service cases. Usually answer the immediate question and ask one necessary follow-up. Match the customer's language where supported. Use supplied prices, coverage, hours, and policies; never infer them from another business's examples.

### 5. Make human handover actionable

We already pause automation and prepare handover context. A useful next addition is a simple staff owner and picked-up state, so a transferred chat does not sit unnoticed. Show the recipient, issue, collected details, and remaining question. Do not promise a callback time unless configured and operationally supported.

ChatMitra's team guidance supports individual access and responsibility. Reuse our existing staff permissions rather than building a larger permissions system. [Team roles](https://chatmitra.com/features/role-management/)

### 6. Expose failures and measure the actual journey

ChatMitra documents message delivery states and webhook feedback. We already store delivery attempts and receipts; surface that existing information. [Message status guide](https://chatmitra.com/learn/messaging/webhooks-and-message-status/), [Webhook integration](https://chatmitra.com/features/webhook-api-integration/)

Our proposed additions are small: record reply source, provider failure category, and response time; show unfinished booking steps and unclaimed handovers. Keep delivery status separate from appointment status: a read message does not mean a confirmed visit. Preserve current handling of ambiguous send timeouts.

Add lightweight limits on expensive AI calls per customer if real usage requires them. ChatMitra exposes similar controls, but its defaults are not requirements for us. A second paid provider is unnecessary for the current scope. [AI controls](https://chatmitra.com/features/ai-chatbot/)

## Later, when needed

Message formats should serve a specific task: text for natural conversation, buttons/lists for convenient choices, and photos for visible context. [Message types](https://chatmitra.com/learn/messaging/message-types/), [Media messages](https://chatmitra.com/learn/messaging/media-messages/)

Native booking forms could help repeated structured entry, but are optional and must allow normal typed replies. [Flows and webviews](https://chatmitra.com/learn/messaging/whatsapp-flows-and-webviews/)

Keep voice replies deferred as requested. Preserve the existing ten-exchange memory approach while evaluating real dialogues; increasing memory alone will not fix field extraction or invalid credentials.

## Suggested implementation order

1. Restore provider readiness and make failures visible to staff.
2. Extend structured interpretation and validated field updates within the current handlers and booking service.
3. Run the dialogue acceptance set with a working model; refine examples and business knowledge from observed failures.
4. Add basic handover ownership and operational reporting if staff workflow needs it.

This sequence is our recommendation from the code comparison, rather than a requirement imposed by ChatMitra. No new package is inherently needed for these changes; provider usage and WhatsApp service costs remain separate from package choice.
