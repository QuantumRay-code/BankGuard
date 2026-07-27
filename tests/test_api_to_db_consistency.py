import uuid
import pytest

pytestmark = pytest.mark.smoke

from decimal import Decimal

from factories import create_account
from helpers import count_rows, get_balance


async def test_successful_deposit_response_matches_db_state(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("200.00"))
    response = await api_client.post(
        "/deposit",
        json={
            "account_id": account["id"],
            "amount": "75.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    body = response.json()
    assert Decimal(body["balance_after"]) == get_balance(db_connection, account["id"])

    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT amount, transaction_type FROM transactions WHERE id = %s",
            (body["id"],),
        )
        db_amount, db_type = cur.fetchone()
    assert db_amount == Decimal("75.00")
    assert db_type == "deposit"


async def test_failed_withdrawal_response_matches_unchanged_db_state(
    db_connection, api_client
):
    account = create_account(db_connection, balance=Decimal("50.00"))
    response = await api_client.post(
        "/withdraw",
        json={
            "account_id": account["id"],
            "amount": "1000.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 409
    assert get_balance(db_connection, account["id"]) == Decimal("50.00")
    assert count_rows(db_connection, "transactions", account_id=account["id"]) == 0


async def test_get_account_response_matches_db_row(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("999.99"))
    response = await api_client.get(f"/accounts/{account['id']}")
    body = response.json()
    assert Decimal(body["balance"]) == Decimal("999.99")
    assert body["id"] == account["id"]


async def test_get_nonexistent_account_returns_404(api_client):
    response = await api_client.get("/accounts/999999999")
    assert response.status_code == 404


async def test_get_nonexistent_transaction_returns_404(api_client):
    response = await api_client.get("/transactions/999999999")
    assert response.status_code == 404
