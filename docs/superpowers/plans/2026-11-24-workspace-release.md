# WhatsApp workspace release repair plan

Goal: repair the five verified blockers and deploy the tested scoped release.

1. Add failing API/delivery regressions. Introduce consistent customer → conversation → delivery → quota lock ordering; hold the dispatch gate until provider outcome is recorded. Human takeover waits for requests already in flight, and blocks pending/failed bot deliveries. Persist explicit conversation/message origin in new deliveries and fail closed for ambiguous legacy origins.
2. Serialize New Chat resolution using the customer row; require explicit human takeover for sending on existing bot chats. Make retry validate ownership, mode, window, known origin and immutable attempt history; fail closed for orphan/ambiguous records.
3. Fetch complete validated Meta template snapshots, sync name+language, revoke stale approvals only on complete successful sync, and reject unsupported template components. No Meta writes.
4. Replace duplicate-logic frontend tests with rendered components. Run full pytest, frontend tests/build, migration checks, browser desktop/mobile synthetic acceptance, and an independent review. Verify PostgreSQL concurrency using an isolated test database.
5. Inspect live source diffs and release manifest; snapshot code/image/database, deploy only application files and additive migrations, verify public health/static assets/authenticated read-only APIs. No Meta registration changes or customer messages. Retain rollback artifacts.
