# Consolidated WhatsApp SaaS implementation plan

**Goal:** One grouped client workspace with Meta-first onboarding; Super Admin only software/client/access management; rename existing logins and deploy.
**Architecture:** Reuse existing Django APIs/React pages; shared authoritative readiness gate with truthful provider verification. Group existing routes, do not create duplicate modules. Keep private S3 images/profile upload from prior release.
**Authorization:** User explicitly requested autonomous implementation, account changes, latest build and production deployment.

- [ ] Backend: new client WhatsApp E164, setup lifecycle, verified connection stamp, actual Meta phone/WABA verification, setup gate for new provisioned workspaces; existing workspaces retained until deliberate enablement.
- [ ] Frontend: collapsible grouped menus; Super Admin users/clients/plans/access/audit only; client-only Meta settings/diagnostics; setup-first route guard and clear completion flow; required WhatsApp number provisioning.
- [ ] Root: move diagnostic endpoints to tenant-scoped client context, restrict super operations to usermanagement; test cross-tenant/privacy/permissions.
- [ ] Rename owner to neorizsolutions and operator to superadmin using authoritative account identities, preserve user IDs/roles/history; apply requested passwords through server account-management command (not browser UI), verify login, update local protected records.
- [ ] Full backend/frontend/build, PostgreSQL real migrations/concurrency, browser acceptance, independent review; fix findings.
- [ ] Backups, deploy tested image, verify current business/client setup and new logins; remove temporary SSH rule; final report exact limits.

**Failure focus:** new-client gate bypasses; failed/fake provider validation; number/WABA mismatch; cross-tenant diagnostics; legacy account identity migration; duplicate menus; stale client bootstrap after setup changes.
