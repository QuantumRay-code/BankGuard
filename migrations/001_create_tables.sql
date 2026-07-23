CREATE TABLE branches (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch_code VARCHAR(20)  NOT NULL,
    name        VARCHAR(150) NOT NULL,
    city        VARCHAR(100) NOT NULL,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE employees (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    branch_id      BIGINT       NOT NULL,
    employee_code  VARCHAR(20)  NOT NULL,
    full_name      VARCHAR(150) NOT NULL,
    created_at     TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE customers (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    full_name     VARCHAR(150) NOT NULL,
    email         VARCHAR(255) NOT NULL,
    phone_number  VARCHAR(20)  NOT NULL,
    created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE accounts (
    id                     BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    customer_id            BIGINT        NOT NULL,
    branch_id              BIGINT        NOT NULL,
    opened_by_employee_id  BIGINT        NOT NULL,
    account_number         VARCHAR(20)   NOT NULL,
    balance                NUMERIC(14,2) NOT NULL DEFAULT 0,
    created_at             TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE transactions (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    account_id                BIGINT        NOT NULL,
    transaction_type          VARCHAR(20)   NOT NULL,
    amount                    NUMERIC(14,2) NOT NULL,
    idempotency_key           VARCHAR(100)  NOT NULL,
    performed_by_employee_id  BIGINT,
    created_at                TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE transfers (
    id                        BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    from_account_id           BIGINT        NOT NULL,
    to_account_id             BIGINT        NOT NULL,
    amount                    NUMERIC(14,2) NOT NULL,
    idempotency_key           VARCHAR(100)  NOT NULL,
    performed_by_employee_id  BIGINT,
    flagged_for_review        BOOLEAN       NOT NULL DEFAULT false,
    created_at                TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE audit_logs (
    id                  BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    operation_type      VARCHAR(20)   NOT NULL,
    transaction_id      BIGINT,
    transfer_id         BIGINT,
    account_id          BIGINT        NOT NULL,
    related_account_id  BIGINT,
    amount              NUMERIC(14,2) NOT NULL,
    balance_before      NUMERIC(14,2) NOT NULL,
    balance_after       NUMERIC(14,2) NOT NULL,
    created_at          TIMESTAMPTZ   NOT NULL DEFAULT now()
);
