# BankGuard Performance Report

Timing figures below are informational only — no test in this project asserts on execution time. Correctness checks (index vs. sequential scan) live in `tests/test_performance.py`.

## Account lookup by ID
```sql
SELECT * FROM accounts WHERE id = %s
```
```
Index Scan on accounts (planned cost=8.44, actual time=0.12ms, rows=1)
```

## Account lookup by account_number
```sql
SELECT * FROM accounts WHERE account_number = %s
```
```
Index Scan on accounts (planned cost=8.44, actual time=0.167ms, rows=1)
```

## Transaction history for an account
```sql
SELECT * FROM transactions WHERE account_id = %s
```
```
Index Scan on transactions (planned cost=8.62, actual time=0.162ms, rows=8)
```

## Transaction lookup by idempotency_key
```sql
SELECT * FROM transactions WHERE idempotency_key = %s
```
```
Index Scan on transactions (planned cost=8.45, actual time=0.021ms, rows=0)
```

## Transfers sent by an account
```sql
SELECT * FROM transfers WHERE from_account_id = %s
```
```
Index Scan on transfers (planned cost=8.35, actual time=0.105ms, rows=1)
```

## Transfers received by an account
```sql
SELECT * FROM transfers WHERE to_account_id = %s
```
```
Bitmap Heap Scan on transfers (planned cost=12.27, actual time=0.128ms, rows=0)
  Bitmap Index Scan on idx_transfers_to_account_id (planned cost=4.43, actual time=0.125ms, rows=0)
```

## Flagged transfers (partial index)
```sql
SELECT * FROM transfers WHERE flagged_for_review = true
```
```
Index Scan on transfers (planned cost=710.36, actual time=6.545ms, rows=3722)
```

## Audit trail for an account
```sql
SELECT * FROM audit_logs WHERE account_id = %s
```
```
Index Scan on audit_logs (planned cost=37.41, actual time=0.028ms, rows=9)
```

## Customer lookup by email
```sql
SELECT * FROM customers WHERE email = %s
```
```
Index Scan on customers (planned cost=8.44, actual time=0.625ms, rows=1)
```

## Customer lookup by full_name (no index — expect Seq Scan)
```sql
SELECT * FROM customers WHERE full_name = %s
```
```
Seq Scan on customers (planned cost=2509.99, actual time=15.226ms, rows=0)
```
