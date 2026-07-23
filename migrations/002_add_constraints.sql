ALTER TABLE branches
    ADD CONSTRAINT uq_branches_branch_code UNIQUE (branch_code);

ALTER TABLE employees
    ADD CONSTRAINT fk_employees_branch
        FOREIGN KEY (branch_id) REFERENCES branches (id),
    ADD CONSTRAINT uq_employees_employee_code UNIQUE (employee_code);

ALTER TABLE customers
    ADD CONSTRAINT uq_customers_email UNIQUE (email);

ALTER TABLE accounts
    ADD CONSTRAINT fk_accounts_customer
        FOREIGN KEY (customer_id) REFERENCES customers (id),
    ADD CONSTRAINT fk_accounts_branch
        FOREIGN KEY (branch_id) REFERENCES branches (id),
    ADD CONSTRAINT fk_accounts_opened_by_employee
        FOREIGN KEY (opened_by_employee_id) REFERENCES employees (id),
    ADD CONSTRAINT uq_accounts_account_number UNIQUE (account_number),
    ADD CONSTRAINT chk_accounts_balance_non_negative
        CHECK (balance >= 0);

ALTER TABLE transactions
    ADD CONSTRAINT fk_transactions_account
        FOREIGN KEY (account_id) REFERENCES accounts (id),
    ADD CONSTRAINT fk_transactions_performed_by_employee
        FOREIGN KEY (performed_by_employee_id) REFERENCES employees (id),
    ADD CONSTRAINT uq_transactions_idempotency_key UNIQUE (idempotency_key),
    ADD CONSTRAINT chk_transactions_transaction_type
        CHECK (transaction_type IN ('deposit', 'withdrawal')),
    ADD CONSTRAINT chk_transactions_amount_positive
        CHECK (amount > 0);

ALTER TABLE transfers
    ADD CONSTRAINT fk_transfers_from_account
        FOREIGN KEY (from_account_id) REFERENCES accounts (id),
    ADD CONSTRAINT fk_transfers_to_account
        FOREIGN KEY (to_account_id) REFERENCES accounts (id),
    ADD CONSTRAINT fk_transfers_performed_by_employee
        FOREIGN KEY (performed_by_employee_id) REFERENCES employees (id),
    ADD CONSTRAINT uq_transfers_idempotency_key UNIQUE (idempotency_key),
    ADD CONSTRAINT chk_transfers_amount_positive
        CHECK (amount > 0),
    ADD CONSTRAINT chk_transfers_no_self_transfer
        CHECK (from_account_id <> to_account_id);

ALTER TABLE audit_logs
    ADD CONSTRAINT fk_audit_logs_transaction
        FOREIGN KEY (transaction_id) REFERENCES transactions (id),
    ADD CONSTRAINT fk_audit_logs_transfer
        FOREIGN KEY (transfer_id) REFERENCES transfers (id),
    ADD CONSTRAINT fk_audit_logs_account
        FOREIGN KEY (account_id) REFERENCES accounts (id),
    ADD CONSTRAINT fk_audit_logs_related_account
        FOREIGN KEY (related_account_id) REFERENCES accounts (id),
    ADD CONSTRAINT chk_audit_logs_operation_type
        CHECK (operation_type IN ('deposit', 'withdrawal', 'transfer_in', 'transfer_out')),
    ADD CONSTRAINT chk_audit_logs_amount_positive
        CHECK (amount > 0),
    ADD CONSTRAINT chk_audit_logs_reference_matches_type
        CHECK (
            (operation_type IN ('deposit', 'withdrawal')
                AND transaction_id IS NOT NULL
                AND transfer_id IS NULL
                AND related_account_id IS NULL)
            OR
            (operation_type IN ('transfer_in', 'transfer_out')
                AND transfer_id IS NOT NULL
                AND transaction_id IS NULL
                AND related_account_id IS NOT NULL)
        );
