import uuid
from decimal import Decimal

from factories import create_account
from helpers import count_rows


async def test_deposit_creates_exactly_one_audit_log(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("100.00"))
    response = await api_client.post(
        "/deposit",
        json={
            "account_id": account["id"],
            "amount": "50.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    transaction_id = response.json()["id"]
    assert count_rows(db_connection, "audit_logs", transaction_id=transaction_id) == 1


async def test_transfer_creates_exactly_two_audit_logs(db_connection, api_client):
    from_account = create_account(db_connection, balance=Decimal("500.00"))
    to_account = create_account(db_connection, balance=Decimal("0.00"))
    response = await api_client.post(
        "/transfer",
        json={
            "from_account_id": from_account["id"],
            "to_account_id": to_account["id"],
            "amount": "100.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    transfer_id = response.json()["id"]
    assert count_rows(db_connection, "audit_logs", transfer_id=transfer_id) == 2


def test_every_seeded_transaction_has_exactly_one_audit_log(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM transactions t
            WHERE (SELECT COUNT(*) FROM audit_logs al WHERE al.transaction_id = t.id) <> 1
            """
        )
        violations = cur.fetchone()[0]
    assert violations == 0


def test_every_seeded_transfer_has_exactly_two_audit_logs(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT COUNT(*) FROM transfers t
            WHERE (SELECT COUNT(*) FROM audit_logs al WHERE al.transfer_id = t.id) <> 2
            """
        )
        violations = cur.fetchone()[0]
    assert violations == 0
