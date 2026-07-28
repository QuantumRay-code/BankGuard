# Database Schema

## Migration structure

Three files, run in order by `scripts/run_migrations.py`, each tracked in a `schema_migrations` table so re-running the script only applies what's new:

| File | Contents |
|---|---|
| `001_create_tables.sql` | Bare tables — columns and types only |
| `002_add_constraints.sql` | Every FK, CHECK, and UNIQUE constraint, explicitly named |
| `003_add_indexes.sql` | Every index, including one partial index |

Separating structure from constraints from indexes (rather than one monolithic file per table) makes it possible to reason about — and rerun — each concern independently, and keeps every constraint's name searchable in one place when a test needs to reference it (e.g., `chk_transfers_no_self_transfer`).

## Design philosophy

Every column exists for one of two reasons: it enables a specific validation suite, or it's part of the minimal realistic shape an entity needs to exist coherently. Neither is "because real banks have this." Two concrete examples of where this mattered:

- **`accounts.account_type` was proposed, then removed.** No validation suite touches it, and it invites unanswerable scope questions ("why only checking/savings, why no joint accounts?") that have nothing to do with this project's purpose.
- **`transactions.transaction_type` stayed**, despite looking similar. It mirrors the two explicitly-specified API endpoints (`POST /deposit`, `POST /withdraw`) and feeds directly into Money Conservation's arithmetic (add vs. subtract) — a real, traceable justification the other one lacked.

## Tables

### `branches`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `branch_code` | `VARCHAR(20)` | UNIQUE | Gives Constraint Validation a real UNIQUE case beyond the PK |
| `name`, `city` | `VARCHAR` | — | Minimal realistic identity for a branch |

### `employees`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `branch_id` | `BIGINT` | FK → branches | Referential Integrity |
| `employee_code` | `VARCHAR(20)` | UNIQUE | Constraint Validation |
| `full_name` | `VARCHAR(150)` | — | Debuggability (`Maria Santos`, not `Employee 1`) |

### `customers`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `full_name` | `VARCHAR(150)` | — | Debuggability |
| `email` | `VARCHAR(255)` | UNIQUE | Constraint Validation |
| `phone_number` | `VARCHAR(20)` | — | Realistic entity completeness |

### `accounts`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `customer_id`, `branch_id`, `opened_by_employee_id` | `BIGINT` | FK ×3 | Referential Integrity |
| `account_number` | `VARCHAR(20)` | UNIQUE | Constraint Validation |
| `balance` | `NUMERIC(14,2)` | `CHECK >= 0` | Constraint Validation — explicitly named in the project spec's own examples |

### `transactions`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `account_id` | `BIGINT` | FK → accounts | Referential Integrity |
| `transaction_type` | `VARCHAR(20)` | `CHECK IN ('deposit','withdrawal')` | Mirrors the two spec'd endpoints; feeds Money Conservation |
| `amount` | `NUMERIC(14,2)` | `CHECK > 0` | Money Conservation |
| `idempotency_key` | `VARCHAR(100)` | UNIQUE | Duplicate Transaction Prevention |
| `performed_by_employee_id` | `BIGINT` | FK → employees, nullable | Channel modeling — always NULL from the live API (no auth), populated only by historical seed data |

### `transfers`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `from_account_id`, `to_account_id` | `BIGINT` | FK ×2 → accounts | Referential Integrity |
| `amount` | `NUMERIC(14,2)` | `CHECK > 0` | Money Conservation |
| `idempotency_key` | `VARCHAR(100)` | UNIQUE | Duplicate Transaction Prevention |
| `performed_by_employee_id` | `BIGINT` | FK → employees, nullable | Same channel modeling as transactions |
| `flagged_for_review` | `BOOLEAN` | default `false` | Large Transaction Monitoring — set when `amount >= $2,500` |
| — | — | `CHECK (from_account_id <> to_account_id)` | A defined business rule for this simulated bank, not an imported real-world assumption |

### `audit_logs`
| Column | Type | Constraint | Purpose |
|---|---|---|---|
| `id` | `BIGINT IDENTITY` | PK | — |
| `operation_type` | `VARCHAR(20)` | `CHECK IN ('deposit','withdrawal','transfer_in','transfer_out')` | Audit Log Completeness |
| `transaction_id`, `transfer_id` | `BIGINT` | FK, both nullable | Real, enforced FKs — deliberately not a single polymorphic reference (see below) |
| `account_id` | `BIGINT` | FK, NOT NULL | Balance Reconciliation (per-account trail) |
| `related_account_id` | `BIGINT` | FK, nullable | Context for transfer rows |
| `amount`, `balance_before`, `balance_after` | `NUMERIC(14,2)` | `CHECK amount > 0` | Reconciliation, Money Conservation |
| — | — | `CHECK` tying `operation_type` to exactly one of `transaction_id`/`transfer_id` | Enforces the design below at the database level |

**Why two nullable FKs instead of one polymorphic `reference_id`:** a single column pointing at either table depending on context can't have a real foreign key — which would mean the audit table itself violates Referential Integrity, the very suite it exists to help prove. Two columns, with a CHECK ensuring exactly one is set matching `operation_type`, keeps every reference genuinely enforced by Postgres, not just by application convention.

**Why transfers produce 2 audit rows (`transfer_out` + `transfer_in`), not 1:** see [architecture.md](architecture.md#database-er-diagram) — in short, a single row keyed only to the sender would make the receiving account's balance change invisible to a `WHERE account_id = X` reconciliation query.

## Precision: `NUMERIC(14,2)`, not unrestricted `NUMERIC`

Every money column uses fixed 2-decimal precision. Nothing in this system's scope produces sub-cent values — no interest calculation, no currency conversion — so a wider scale (e.g., 4 decimal places) would just invite "why 4 and not 2, if nothing here ever needs it," the same category of problem `account_type` had. 14 digits of precision (up to ~$999 billion per account) is generous headroom for a simulated regional bank without being excess for its own sake.

## Index strategy

Every FK column is indexed, plus `created_at` on the high-volume tables (supports range queries and gives the `idx_*_created_at` indexes real work to do against realistic date-distributed seed data). One partial index exists specifically for `transfers.flagged_for_review`:

```sql
CREATE INDEX idx_transfers_flagged_for_review ON transfers (flagged_for_review)
    WHERE flagged_for_review = true;
```

Since flagged transfers are a small minority (~2.5% of the seeded dataset), a partial index only indexes those rows — smaller, faster, and a legitimate demonstration of a real Postgres optimization technique rather than a blanket index over a boolean column where most values are `false`.
