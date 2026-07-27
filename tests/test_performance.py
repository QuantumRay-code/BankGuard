import pytest

pytestmark = pytest.mark.performance

from datetime import timedelta

from helpers import get_query_plan, plan_contains_seq_scan


def _sample_account(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT id, account_number FROM accounts LIMIT 1")
        return cur.fetchone()


def test_account_lookup_by_id_uses_index(db_connection):
    account_id, _ = _sample_account(db_connection)
    plan = get_query_plan(
        db_connection, "SELECT * FROM accounts WHERE id = %s", (account_id,)
    )
    assert not plan_contains_seq_scan(plan), plan


def test_account_lookup_by_account_number_uses_index(db_connection):
    _, account_number = _sample_account(db_connection)
    plan = get_query_plan(
        db_connection,
        "SELECT * FROM accounts WHERE account_number = %s",
        (account_number,),
    )
    assert not plan_contains_seq_scan(plan), plan


def test_transaction_history_for_account_uses_index(db_connection):
    account_id, _ = _sample_account(db_connection)
    plan = get_query_plan(
        db_connection, "SELECT * FROM transactions WHERE account_id = %s", (account_id,)
    )
    assert not plan_contains_seq_scan(plan), plan


def test_transaction_lookup_by_idempotency_key_uses_index(db_connection):
    plan = get_query_plan(
        db_connection,
        "SELECT * FROM transactions WHERE idempotency_key = %s",
        ("nonexistent-key",),
    )
    assert not plan_contains_seq_scan(plan), plan


def test_transfers_sent_by_account_uses_index(db_connection):
    account_id, _ = _sample_account(db_connection)
    plan = get_query_plan(
        db_connection,
        "SELECT * FROM transfers WHERE from_account_id = %s",
        (account_id,),
    )
    assert not plan_contains_seq_scan(plan), plan


def test_transfers_received_by_account_uses_index(db_connection):
    account_id, _ = _sample_account(db_connection)
    plan = get_query_plan(
        db_connection, "SELECT * FROM transfers WHERE to_account_id = %s", (account_id,)
    )
    assert not plan_contains_seq_scan(plan), plan


def test_flagged_transfers_uses_partial_index(db_connection):
    plan = get_query_plan(
        db_connection, "SELECT * FROM transfers WHERE flagged_for_review = true", None
    )
    assert not plan_contains_seq_scan(plan), plan


def test_audit_trail_for_account_uses_index(db_connection):
    account_id, _ = _sample_account(db_connection)
    plan = get_query_plan(
        db_connection, "SELECT * FROM audit_logs WHERE account_id = %s", (account_id,)
    )
    assert not plan_contains_seq_scan(plan), plan


def test_audit_log_lookup_by_transaction_id_uses_index(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT transaction_id FROM audit_logs WHERE transaction_id IS NOT NULL LIMIT 1"
        )
        (transaction_id,) = cur.fetchone()
    plan = get_query_plan(
        db_connection,
        "SELECT * FROM audit_logs WHERE transaction_id = %s",
        (transaction_id,),
    )
    assert not plan_contains_seq_scan(plan), plan


def test_recent_transactions_query_uses_index(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT MAX(created_at) FROM transactions")
        (latest,) = cur.fetchone()

    plan = get_query_plan(
        db_connection,
        "SELECT id FROM transactions WHERE created_at > %s",
        (latest - timedelta(days=7),),
    )
    assert not plan_contains_seq_scan(plan), plan


def test_customer_lookup_by_email_uses_index(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT email FROM customers LIMIT 1")
        (email,) = cur.fetchone()
    plan = get_query_plan(
        db_connection, "SELECT * FROM customers WHERE email = %s", (email,)
    )
    assert not plan_contains_seq_scan(plan), plan


def test_query_on_unindexed_column_uses_seq_scan(db_connection):
    plan = get_query_plan(
        db_connection,
        "SELECT id FROM customers WHERE full_name = %s",
        ("Definitely Not A Real Name XYZ999",),
    )
    assert plan.get("Node Type") == "Seq Scan", plan
