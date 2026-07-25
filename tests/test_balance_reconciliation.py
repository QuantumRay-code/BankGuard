import uuid
from decimal import Decimal

from factories import create_account
from helpers import audit_trail_is_reconciled


async def test_deposit_keeps_account_reconciled(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("300.00"))
    await api_client.post(
        "/deposit",
        json={
            "account_id": account["id"],
            "amount": "150.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert audit_trail_is_reconciled(db_connection, account["id"])


async def test_transfer_keeps_both_accounts_reconciled(db_connection, api_client):
    from_account = create_account(db_connection, balance=Decimal("400.00"))
    to_account = create_account(db_connection, balance=Decimal("100.00"))
    await api_client.post(
        "/transfer",
        json={
            "from_account_id": from_account["id"],
            "to_account_id": to_account["id"],
            "amount": "150.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert audit_trail_is_reconciled(db_connection, from_account["id"])
    assert audit_trail_is_reconciled(db_connection, to_account["id"])


def test_all_seeded_accounts_reconcile_with_audit_trail(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT DISTINCT ON (a.id) a.id, a.balance, al.balance_after
                FROM accounts a
                JOIN audit_logs al ON al.account_id = a.id
                ORDER BY a.id, al.created_at DESC, al.id DESC
            ) t
            WHERE t.balance <> t.balance_after
            """
        )
        mismatch_count = cur.fetchone()[0]
    assert mismatch_count == 0
