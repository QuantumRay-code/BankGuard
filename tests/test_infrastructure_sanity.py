from decimal import Decimal

from factories import create_account
from helpers import get_balance


def test_db_connection_rolls_back(db_connection):
    account = create_account(db_connection, balance=Decimal("500.00"))
    assert get_balance(db_connection, account["id"]) == Decimal("500.00")


def test_previous_test_data_did_not_leak(db_connection):
    with db_connection.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM accounts WHERE account_number LIKE 'TEST%'")
        count = cur.fetchone()[0]
    assert count == 0, "Rollback isolation is broken — test data leaked between tests"


async def test_api_client_deposit_and_direct_db_query_agree(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("1000.00"))

    response = await api_client.post(
        "/deposit",
        json={
            "account_id": account["id"],
            "amount": "250.00",
            "idempotency_key": "sanity-check-deposit-001",
        },
    )
    assert response.status_code == 201
    assert response.json()["balance_after"] == "1250.00"
    assert get_balance(db_connection, account["id"]) == Decimal("1250.00")


async def test_api_client_changes_do_not_leak(db_connection, api_client):
    with db_connection.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM transactions WHERE idempotency_key = 'sanity-check-deposit-001'"
        )
        count = cur.fetchone()[0]
    assert count == 0, (
        "The previous test's API-created transaction leaked into this test"
    )
