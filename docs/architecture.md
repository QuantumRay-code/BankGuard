# Architecture & Design Decision

## The core reframe

BankGuard's schema and seed data aren't the product - they're the fixture.

---

## Database ER Diagram

```mermaid
erDiagram
    BRANCHES ||--o{ EMPLOYEES : employs
    BRANCHES ||--o{ ACCOUNTS : hosts
    CUSTOMERS ||--o{ ACCOUNTS : owns
    EMPLOYEES ||--o{ ACCOUNTS : opens
    EMPLOYEES ||--o{ TRANSACTIONS : "may assist"
    EMPLOYEES ||--o{ TRANSFERS : "may assist"
    ACCOUNTS ||--o{ TRANSACTIONS : has
    ACCOUNTS ||--o{ TRANSFERS : "sends/receives"
    ACCOUNTS ||--o{ AUDIT_LOGS : affects
    TRANSACTIONS ||--|| AUDIT_LOGS : generates
    TRANSFERS ||--|{ AUDIT_LOGS : "generates (exactly 2)"

    BRANCHES {
        bigint id PK
        varchar branch_code UK
        varchar name
        varchar city
    }
    EMPLOYEES {
        bigint id PK
        bigint branch_id FK
        varchar employee_code UK
        varchar full_name
    }
    CUSTOMERS {
        bigint id PK
        varchar full_name
        varchar email UK
        varchar phone_number
    }
    ACCOUNTS {
        bigint id PK
        bigint customer_id FK
        bigint branch_id FK
        bigint opened_by_employee_id FK
        varchar account_number UK
        numeric balance "CHECK >= 0"
    }
    TRANSACTIONS {
        bigint id PK
        bigint account_id FK
        varchar transaction_type
        numeric amount "CHECK > 0"
        varchar idempotency_key UK
        bigint performed_by_employee_id FK "nullable"
    }
    TRANSFERS {
        bigint id PK
        bigint from_account_id FK
        bigint to_account_id FK
        numeric amount "CHECK > 0"
        varchar idempotency_key UK
        boolean flagged_for_review
    }
    AUDIT_LOGS {
        bigint id PK
        varchar operation_type
        bigint transaction_id FK "nullable"
        bigint transfer_id FK "nullable"
        bigint account_id FK
        bigint related_account_id FK "nullable"
        numeric amount
        numeric balance_before
        numeric balance_after
    }
```

**Why `audit_logs` has two nullable FKs instead of one polymorphic reference:** a single `reference_id` column pointing at either `transactions` or `transfers` depending on context can't have a real foreign key constraint — which directly contradicts the Referential Integrity suite this table is supposed to help prove. Two separate nullable FKs, with a `CHECK` constraint enforcing exactly one is set matching `operation_type`, keeps every reference genuinely enforced.

**Why transfers generate 2 audit rows, not 1:** Balance Reconciliation needs "give me account X's full history" to be a uniform `WHERE account_id = X` query for *every* account. A single row keyed only to the sender would mean the receiving account's balance change never appears in any row keyed to its own `account_id` — reconciliation would silently break for every account that only ever receives transfers.

---

## Transfer Request Flow

```mermaid
sequenceDiagram
    participant Client
    participant API as FastAPI /transfer
    participant Ledger as ledger.py
    participant DB as PostgreSQL

    Client->>API: POST /transfer
    API->>Ledger: transfer(from, to, amount, idempotency_key)
    Ledger->>DB: SELECT existing transfer by idempotency_key
    alt Key already used
        DB-->>Ledger: existing row found
        Ledger-->>API: (result, created=False)
        API-->>Client: 200 OK
    else New request
        Note over Ledger,DB: Accounts locked in ASCENDING id order,<br/>regardless of transfer direction — prevents<br/>deadlock between concurrent opposite-direction transfers
        Ledger->>DB: UPDATE first account (debit if sender, WHERE balance >= amount)
        Ledger->>DB: UPDATE second account (credit if receiver)
        Ledger->>DB: INSERT INTO transfers
        Ledger->>DB: INSERT INTO audit_logs (transfer_out)
        Ledger->>DB: INSERT INTO audit_logs (transfer_in)
        DB-->>Ledger: commit
        Ledger-->>API: (result, created=True)
        API-->>Client: 201 Created
    end
```

**Why the sufficiency check lives inside the `UPDATE`'s `WHERE` clause** (`WHERE balance >= amount`), rather than a separate `SELECT` then `UPDATE`: a read-then-write pattern lets two concurrent requests both read the same balance, both pass the check, and both succeed — leaving the account negative. Making the check part of the `UPDATE` itself means Postgres evaluates it against the current, row-locked value, so concurrent requests against the same account serialize safely at the database level with no additional application-side locking.

---

## Test Isolation Strategy

Two different approaches, used deliberately for different purposes:

```mermaid
flowchart TD
    subgraph Standard["Phases 5, 6, 8 — Rollback-Isolated Tests"]
        T1[Test] --> Conn1[Single wrapped connection]
        Conn1 --> SP["SAVEPOINT (per request)"]
        SP --> Real1[(PostgreSQL)]
        T1 -.teardown: one real rollback.-> Real1
    end

    subgraph Concurrency["Phase 7 — Concurrency Tests"]
        T2[Test] --> Pool[Real connection pool]
        Pool --> ConnA[Connection A]
        Pool --> ConnB[Connection B]
        Pool --> ConnN[Connection N ...]
        ConnA --> Real2[(PostgreSQL)]
        ConnB --> Real2
        ConnN --> Real2
        T2 -.teardown: explicit DELETE, FK-safe order.-> Real2
    end
```

Most tests use a single connection wrapped so the application code's own `commit()`/`rollback()` calls operate on a `SAVEPOINT` instead of the real transaction — meaning `ledger.py` can commit as normal, while the test fixture undoes everything with one real rollback at teardown. This keeps the seeded dataset untouched no matter how many tests run.

Concurrency tests can't use this: a single connection can only run one query at a time, so racing "concurrent" requests through it would just serialize them — defeating the entire point. Those tests use the app's real connection pool instead (genuinely separate sessions, genuinely racing the same rows) and clean up their own dedicated test accounts explicitly afterward.

---

## CI/CD Pipeline

```mermaid
flowchart LR
    Push["Push / PR"] --> Smoke["Smoke Tests<br/>small dataset, ~2s"]
    Smoke --> RuffCheck["Ruff + Format Check"]
    Smoke --> DockerBuild["Docker Build + Trivy Scan"]

    Schedule["Nightly Schedule"] --> Regression["Regression Tests<br/>medium dataset"]

    Manual["Manual Trigger"] --> Performance["Performance Tests<br/>large dataset, 1.25M+ rows"]
    Performance --> Report["Performance Report<br/>(build artifact)"]
```

Full breakdown in [cicd.md](cicd.md).
