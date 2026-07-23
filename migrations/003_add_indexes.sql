CREATE INDEX idx_employees_branch_id ON employees (branch_id);

CREATE INDEX idx_accounts_customer_id ON accounts (customer_id);
CREATE INDEX idx_accounts_branch_id ON accounts (branch_id);

CREATE INDEX idx_transactions_account_id ON transactions (account_id);
CREATE INDEX idx_transactions_created_at ON transactions (created_at);

CREATE INDEX idx_transfers_from_account_id ON transfers (from_account_id);
CREATE INDEX idx_transfers_to_account_id ON transfers (to_account_id);
CREATE INDEX idx_transfers_created_at ON transfers (created_at);
CREATE INDEX idx_transfers_flagged_for_review ON transfers (flagged_for_review)
    WHERE flagged_for_review = true;

CREATE INDEX idx_audit_logs_account_id ON audit_logs (account_id);
CREATE INDEX idx_audit_logs_related_account_id ON audit_logs (related_account_id);
CREATE INDEX idx_audit_logs_transaction_id ON audit_logs (transaction_id);
CREATE INDEX idx_audit_logs_transfer_id ON audit_logs (transfer_id);
CREATE INDEX idx_audit_logs_created_at ON audit_logs (created_at);
