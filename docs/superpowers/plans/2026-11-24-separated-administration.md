# Separated Client and Platform Administration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement task-by-task.

**Goal:** Deploy distinct client settings/Meta/media workflows and native platform operations, client management and menu controls.
**Architecture:** Existing Django session/tenant authorization and React shell; explicit allowlisted platform API; private tenant-keyed S3 media; Meta resumable profile upload.
**Tech Stack:** Django, React/TypeScript/Vitest, PostgreSQL, boto3/Pillow, AWS S3/Lightsail.
**Spec:** User request 2026-11-24 in this chat; user requested autonomous implementation and production deployment.

## Global Constraints
Preserve prior repairs and dirty work. No customer test sends. Never expose tokens/raw credentials in operations. Platform-only menus and client-only Meta settings require server authorization, not hidden links alone. S3 private/encrypted; no public ACL. Mark Meta photo updated only after provider success. Back up production; promote tested image; restore temporary firewall changes.

## Review Focus
Cross-tenant read/write, malformed image/decompression bombs, provider partial failures, secret redaction in diagnostic errors, stale UI and privilege escalation.

### Task 1: Platform operations
Files: apps/tenants/platform_operations.py, tests/test_platform_operations.py, frontend/src/pages/PlatformOperationsPage.tsx and rendered tests.
- [ ] Write denial/filter/detail/redaction/user-update tests and observe failure.
- [ ] Implement allowlisted paginated resource reads and audited identity edits; no bypass retries.
- [ ] Build native operations UI with filters, error details and context links; rendered tests pass.

### Task 2: Client media and Meta photo
Files: apps/tenants/media_api.py, apps/whatsapp/profile_media.py, tests/test_client_media.py, config/settings.py, requirements.txt, SettingsPage.tsx.
- [ ] Tests: unauthorized/foreign tenant, oversized/invalid image, S3 error, Meta upload/reject/confirmed success.
- [ ] Implement private tenant-scoped S3 writes/presign, workspace logo persistence, Meta resumable upload/profile handle update.
- [ ] Add actual file inputs, preview, explicit save/sync result and setup guidance.

### Task 3: Account/context separation
Files: apps/tenants/middleware.py, apps/tenants/account_api.py, spa_urls.py, App.tsx, account settings component and tests.
- [ ] Test client cannot call platform API and platform needs explicit inspect context for client API.
- [ ] Add server context guard, frontend route guard, self profile email/display name editing; platform manages client menus via existing matrix/overrides.
- [ ] Keep client credentials/settings owner/admin scoped.

### Task 4: Provision, verify, deploy
- [ ] Provision private S3 bucket with encryption/public access block/TLS requirement and limited app object permissions; store credentials only deployment secrets/server env.
- [ ] Run full backend, PostgreSQL migration/concurrency, frontend and build checks; independent review fixes.
- [ ] Browser acceptance synthetic or read-only production; no real customer sends/provider profile changes without chosen image.
- [ ] Back up, deploy tested image, verify public health/auth APIs/storage upload using labelled test media, clean temporary access; report limits truthfully.
