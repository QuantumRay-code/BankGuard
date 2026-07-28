# Testing Strategy

53 tests across 10 files, all deterministic and independent — no test depends on another, and none permanently mutates the seeded dataset (per the project spec's Database State Management rules).

## Two isolation strategies, used deliberately

**Rollback-isolated (Phases 5, 6, 8 — the large majority of tests).** A single database connection is wrapped so that any `commit()`/`rollback()` called by application code — including `ledger.py`'s own internal commits during normal operation — operates against a `SAVEPOINT` rather than the real transaction. The test fixture does exactly one real rollback at teardown, undoing everything regardless of how many times the code under test believed it was committing. This is what makes it safe to call the real API (via `httpx.AsyncClient` + `ASGITransport`, in-process, no network call) and then directly query the database afterward in the same test and see consistent state.

**Real-connection (Phase 7 — concurrency only).** A single connection can only run one query at a time; racing "concurrent" requests through it would just serialize them and prove nothing. Concurrency tests instead let the app use its real, sized connection pool (`min_size=5, max_size=20`) so multiple requests genuinely race against the same rows across separate sessions — then clean up their own dedicated test accounts explicitly, in FK-safe order, since there's no single transaction to roll back.

## Test data: two distinct concepts

- **`scripts/seed_data.py`** populates a persistent, "production-like" dataset once, directly via SQL (no API involved, since the API doesn't exist until Phase 4). This is the substrate the whole-dataset validation queries run against (e.g., "every seeded transfer conserves money").
- **`tests/factories.py`** (`create_customer`, `create_account`, `create_transfer`, etc.) creates ad-hoc, isolated records *within* a single test's rolled-back transaction — never committed, never touching the seeded baseline.

Both are needed: the seed engine proves the suites hold at realistic scale; the factories let each test set up exactly the specific scenario it's testing, in isolation.

## Determinism

The seed engine uses a fixed RNG seed, so a given profile (`small`/`medium`/`large`) always regenerates identical data. Concurrency tests are the one deliberate exception — they're inherently timing-dependent by nature, though firing 10-20 simultaneous requests makes a real race-condition bug very likely to surface even without being mathematically guaranteed on every single run.

## Suite breakdown

| File | Suite | Style |
|---|---|---|
| `test_money_conservation.py` | Money Conservation | API-level + whole-dataset aggregate |
| `test_acid_rollback.py` | ACID Rollback | API-level, asserting zero partial state on failure |
| `test_duplicate_transaction_prevention.py` | Duplicate Transaction Prevention | API-level, including payload-mismatch detection |
| `test_balance_reconciliation.py` | Balance Reconciliation | API-level + whole-dataset aggregate |
| `test_referential_integrity.py` | Referential Integrity | Direct SQL, deliberately triggering FK violations |
| `test_constraint_validation.py` | Constraint Validation | Direct SQL, deliberately triggering CHECK/UNIQUE/NOT NULL violations |
| `test_audit_log_validation.py` | Audit Log Completeness | API-level + whole-dataset aggregate |
| `test_api_to_db_consistency.py` | API-to-DB Consistency | Compares API response fields directly against DB state |
| `test_concurrency.py` | Concurrency Safety | Real `asyncio.gather()` against a real connection pool |
| `test_performance.py` | Query Plan Validation | Plain `EXPLAIN (FORMAT JSON)` — never execution time |

## A recurring pattern worth naming: recovering from expected errors

Constraint and Referential Integrity tests deliberately trigger a database rejection. Once any error occurs inside a Postgres transaction, every subsequent statement fails until a rollback happens — so `tests/helpers.py`'s `expect_db_error` context manager wraps the deliberate bad operation in its own savepoint, asserts the expected exception, then rolls back to that savepoint specifically — recovering the connection for the rest of the test without undoing any setup data created earlier in the same test.
