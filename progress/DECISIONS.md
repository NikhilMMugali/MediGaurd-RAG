# MediGaurd RAG — Decisions Log

Record of non-obvious implementation choices, in case a later session needs the "why."

## 2026-10-08 — Python 3.12 instead of 3.14 for the backend virtualenv
The machine's default `python3` is 3.14, but `psycopg2-binary` and several ML packages had no prebuilt wheel for it yet, causing source builds to fail (missing `pg_config`, etc.). Switched to the already-installed Python 3.12 interpreter, which installed every dependency cleanly from wheels. If 3.14 wheel coverage improves later, this can be revisited, but there's no functional reason to chase the newest interpreter here.

## 2026-10-08 — psycopg3 instead of psycopg2
Following from the above: rather than fight `psycopg2-binary`'s build requirements, switched the SQLAlchemy URL scheme to `postgresql+psycopg` and the dependency to `psycopg[binary]==3.2.3`, which ships wheels for 3.12. No behavioral difference for this project's usage.

## 2026-10-08 — bcrypt pinned to 4.0.1
`passlib==1.7.4` reads `bcrypt.__about__.__version__`, which was removed in `bcrypt>=4.1`. Without the pin, every password hash/verify call raised `ValueError: password cannot be longer than 72 bytes` (a misleading downstream symptom of the version-detection failure, not an actual length issue). Pinning `bcrypt==4.0.1` restores compatibility. Revisit if upgrading passlib later.

## 2026-10-08 — SQLite `StaticPool` for Phase 1 tests
`sqlite:///:memory:` without `StaticPool` gives each connection checkout a fresh, empty in-memory database under SQLAlchemy's default pooling, so tables created in one connection are invisible to the next ("no such table" errors). `StaticPool` forces a single shared connection for the test engine, which fixes this without requiring a real PostgreSQL instance just to run Phase 1 tests.

## 2026-10-08 — Role verified against the database on every authenticated request, not just at login
A JWT's `role` claim is treated as a convenience cache, not a trust boundary: `get_current_user` re-reads the user's role from PostgreSQL on every request and rejects if it no longer matches the token. This means a role downgrade takes effect immediately without waiting for token expiry, and a forged/stale token claiming a role the account no longer has is rejected. Chosen because the spec's central rule is that authorization must never be decided from client-supplied or client-cached state.

## 2026-10-08 — Upload endpoint restricted to DOCTOR/NURSE/ADMIN
The original spec says "an authorized user" can upload without naming exact roles for this action. Interpreted conservatively: FINANCE and RECEPTION (who have no clinical access) should not be able to introduce new clinical documents. Revisit if the hackathon demo needs a different uploader role (e.g. a dedicated records-clerk role) — currently ADMIN covers that gap.
