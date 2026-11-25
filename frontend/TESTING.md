# Frontend component tests

Run `npm ci` and `npm test` from `frontend` (Node 20+ supported). `npm run test:watch` runs Vitest interactively, and `npm run build` compiles the production TypeScript + Vite bundle into `static/dist/`.

The Vitest suites under `frontend/tests/` import and render the actual React pages, modals, and hooks using React Testing Library and jsdom with mocked API and auth boundaries (no live Meta requests or external sends). Run the Django backend `pytest` suite separately for backend authorization, database transactions, and webhook/delivery verification.
