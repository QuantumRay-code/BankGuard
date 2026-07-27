import uuid
import pytest

pytestmark = pytest.mark.smoke

from decimal import Decimal

from factories import create_account
from helpers import count_rows, get_balance


async def test_repeated_deposit_does_not_double_process(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("100.00"))
    key = str(uuid.uuid4())
    payload = {"account_id": account["id"], "amount": "50.00", "idempotency_key": key}

    first = await api_client.post("/deposit", json=payload)
    second = await api_client.post("/deposit", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert get_balance(db_connection, account["id"]) == Decimal("150.00")
    assert count_rows(db_connection, "transactions", idempotency_key=key) == 1


async def test_repeated_transfer_does_not_double_process(db_connection, api_client):
    from_account = create_account(db_connection, balance=Decimal("1000.00"))
    to_account = create_account(db_connection, balance=Decimal("0.00"))
    key = str(uuid.uuid4())
    payload = {
        "from_account_id": from_account["id"],
        "to_account_id": to_account["id"],
        "amount": "200.00",
        "idempotency_key": key,
    }

    first = await api_client.post("/transfer", json=payload)
    second = await api_client.post("/transfer", json=payload)

    assert first.status_code == 201
    assert second.status_code == 200
    assert get_balance(db_connection, from_account["id"]) == Decimal("800.00")
    assert get_balance(db_connection, to_account["id"]) == Decimal("200.00")


async def test_reusing_key_with_different_amount_is_rejected(db_connection, api_client):
    account = create_account(db_connection, balance=Decimal("100.00"))
    key = str(uuid.uuid4())
    await api_client.post(
        "/deposit",
        json={"account_id": account["id"], "amount": "50.00", "idempotency_key": key},
    )
    response = await api_client.post(
        "/deposit",
        json={"account_id": account["id"], "amount": "75.00", "idempotency_key": key},
    )
    assert response.status_code == 409
