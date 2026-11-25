# Production acceptance fixes implementation plan

Goal: resolve audit defects D01–D09 without changing existing account passwords, client subscriptions or sending messages.

Spec: artifacts/production-e2e/E2E-PROD-20261123T101219Z-b2ac/defects.md.

Architecture: enforce tenant configuration isolation in the resolver; consolidate both provisioning API routes; align CRM endpoints to model contracts. Keep existing response shapes, historical data, worker/delivery safeguards and uncommitted work.

- [x] Add and run failing behavioral regressions for tenant fallback, webhook private URLs, both provisioning paths, invalid plan rollback, existing identity password preservation, company creation, deal scope/stages and task completion.
- [x] Implement fixes in apps/whatsapp/models.py, apps/crm/webhook_service.py and apps/tenants/spa_api.py. No schema change is planned.
- [x] Associate request-access labels and correct unsubstantiated public readiness/isolation claims.
- [x] Run targeted regressions, full pytest, Django checks, frontend build and diff review. Record any remaining failures.
- [x] Back up production database/code, transfer only reviewed changed files, rebuild/recreate web/retry without migrations, verify health and synthetic workflows; preserve rollback image and evidence.
- [x] Update defect remediation report separately from the historical audit.

Review focus: unconfigured/disabled/inactive tenant must never inherit provider credentials; legacy unscoped config cannot select a real tenant; existing identity provisioning cannot rotate password or issue password-reset activation; invalid plan creates nothing; foreign CRM IDs cannot mutate another tenant.

Ruling: live CRM retesting exposed D10/D11, so remediation expanded to apps/crm/services.py and numeric score serializers; failing regressions and full suite were rerun before follow-up deployment.
