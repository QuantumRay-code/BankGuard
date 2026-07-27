from contextlib import contextmanager
from decimal import Decimal

import psycopg
import pytest
import json


def get_balance(conn: psycopg.Connection, account_id: int) -> Decimal:
    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM accounts WHERE id = %s", (account_id,))
        row = cur.fetchone()
    if row is None:
        raise ValueError(f"Account {account_id} not found")
    return row[0]


def get_audit_logs_for_account(conn: psycopg.Connection, account_id: int) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, operation_type, transaction_id, transfer_id, related_account_id,
                   amount, balance_before, balance_after, created_at
            FROM audit_logs
            WHERE account_id = %s
            ORDER BY created_at, id
            """,
            (account_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "id": r[0],
            "operation_type": r[1],
            "transaction_id": r[2],
            "transfer_id": r[3],
            "related_account_id": r[4],
            "amount": r[5],
            "balance_before": r[6],
            "balance_after": r[7],
            "created_at": r[8],
        }
        for r in rows
    ]


def count_rows(conn: psycopg.Connection, table: str, **where) -> int:
    """
    table is always a hardcoded literal at the call site, never
    request/user-supplied, so building the query string directly is safe.
    """
    clause = " AND ".join(f"{key} = %({key})s" for key in where) if where else "TRUE"
    with conn.cursor() as cur:
        cur.execute(f"SELECT COUNT(*) FROM {table} WHERE {clause}", where)
        return cur.fetchone()[0]


def audit_trail_is_reconciled(conn: psycopg.Connection, account_id: int) -> bool:
    balance = get_balance(conn, account_id)
    logs = get_audit_logs_for_account(conn, account_id)
    if not logs:
        return balance == Decimal("0.00")
    return logs[-1]["balance_after"] == balance


@contextmanager
def expect_db_error(conn, error_type):
    with conn.cursor() as cur:
        cur.execute("SAVEPOINT expect_error_boundary")
    with pytest.raises(error_type):
        yield
    with conn.cursor() as cur:
        cur.execute("ROLLBACK TO SAVEPOINT expect_error_boundary")
        cur.execute("RELEASE SAVEPOINT expect_error_boundary")


def get_query_plan(conn, query: str, params=None) -> dict:
    with conn.cursor() as cur:
        cur.execute(f"EXPLAIN (FORMAT JSON) {query}", params)
        row = cur.fetchone()
    raw = row[0]
    plan_data = json.loads(raw) if isinstance(raw, str) else raw
    return plan_data[0]["Plan"]


def plan_contains_seq_scan(plan: dict) -> bool:
    if plan.get("Node Type") == "Seq Scan":
        return True
    return any(plan_contains_seq_scan(child) for child in plan.get("Plans", []))
