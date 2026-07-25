import uuid
from decimal import Decimal

from factories import create_account
from helpers import count_rows, get_balance


async def test_failed_withdrawal_leaves_no_partial_changes(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("100.00"))
    response = await api_client.post(
        "/withdraw",
        json={
            "account_id": account["id"],
            "amount": "999999.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 409
    assert get_balance(db_connection, account["id"]) == Decimal("100.00")
    assert count_rows(db_connection, "transactions", account_id=account["id"]) == 0
    assert count_rows(db_connection, "audit_logs", account_id=account["id"]) == 0


async def test_failed_transfer_insufficient_funds_leaves_both_accounts_unchanged(
    db_connection, api_client
):
    from_account = create_account(db_connection, balance=Decimal("50.00"))
    to_account = create_account(db_connection, balance=Decimal("200.00"))
    response = await api_client.post(
        "/transfer",
        json={
            "from_account_id": from_account["id"],
            "to_account_id": to_account["id"],
            "amount": "999999.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 409
    assert get_balance(db_connection, from_account["id"]) == Decimal("50.00")
    assert get_balance(db_connection, to_account["id"]) == Decimal("200.00")
    assert (
        count_rows(db_connection, "transfers", from_account_id=from_account["id"]) == 0
    )


async def test_failed_transfer_to_nonexistent_account_rolls_back_sender(
    db_connection, api_client
):
    from_account = create_account(db_connection, balance=Decimal("500.00"))
    response = await api_client.post(
        "/transfer",
        json={
            "from_account_id": from_account["id"],
            "to_account_id": 999999999,
            "amount": "100.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 404
    assert get_balance(db_connection, from_account["id"]) == Decimal("500.00")
    assert (
        count_rows(db_connection, "transfers", from_account_id=from_account["id"]) == 0
    )
