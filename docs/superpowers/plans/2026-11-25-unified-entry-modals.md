# Unified entry routes and modal consistency release

**Goal:** One client UI and one Super Admin UI; no Django Admin menu in normal flows; consistent accessible modal closing; remove the specified marketing subheader everywhere.
**Authorization:** User requested these fixes after prior deployment; build and deploy within the ongoing authorized release scope.

- [ ] Canonical role-aware login, authenticated home and legacy GET aliases; preserve APIs, tenant inspection, activation/email gates and customer portal as appropriate.
- [ ] Remove Django menu/footer links; move password change to native My Account. Keep technical Django endpoint for maintenance only.
- [ ] Shared modal with visible X, Escape/backdrop, topmost nested handling, focus management and scrolllock; migrate every React modal without duplicating modules or changing business actions.
- [ ] Remove exact Official Meta Cloud API & Gemini AI Workspace marketing badge.
- [ ] Backend redirect/security tests, actual rendered modal/form tests, full suite/build, PostgreSQL candidate checks, browser acceptance and independent review.
- [ ] Backup, deploy exact tested build, verify both account landing routes/public page and modal access; clean temporary deployment access and record evidence.
