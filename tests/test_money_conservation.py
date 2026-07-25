import uuid
from decimal import Decimal

from factories import create_account
from helpers import get_balance


async def test_transfer_conserves_total_money(db_connection, api_client):
    from_account = create_account(db_connection, balance=Decimal("1000.00"))
    to_account = create_account(db_connection, balance=Decimal("500.00"))
    total_before = get_balance(db_connection, from_account["id"]) + get_balance(
        db_connection, to_account["id"]
    )

    response = await api_client.post(
        "/transfer",
        json={
            "from_account_id": from_account["id"],
            "to_account_id": to_account["id"],
            "amount": "200.00",
            "idempotency_key": str(uuid.uuid4()),
        },
    )
    assert response.status_code == 201

    total_after = get_balance(db_connection, from_account["id"]) + get_balance(
        db_connection, to_account["id"]
    )
    assert total_after == total_before


async def test_chain_of_transfers_conserves_total_money(db_connection, api_client):
    accounts = [
        create_account(db_connection, balance=Decimal("100.00")) for _ in range(4)
    ]
    total_before = sum(
        (get_balance(db_connection, a["id"]) for a in accounts), Decimal("0")
    )

    for i in range(3):
        response = await api_client.post(
            "/transfer",
            json={
                "from_account_id": accounts[i]["id"],
                "to_account_id": accounts[i + 1]["id"],
                "amount": "25.00",
                "idempotency_key": str(uuid.uuid4()),
            },
        )
        assert response.status_code == 201

    total_after = sum(
        (get_balance(db_connection, a["id"]) for a in accounts), Decimal("0")
    )
    assert total_after == total_before


def test_every_seeded_transfer_conserves_money(db_connection):
    with db_connection.cursor() as cur:
        cur.execute(
            """
            SELECT transfer_id
            FROM audit_logs
            WHERE transfer_id IS NOT NULL
            GROUP BY transfer_id
            HAVING SUM(CASE WHEN operation_type = 'transfer_in' THEN amount ELSE -amount END) <> 0
            """
        )
        violations = cur.fetchall()
    assert violations == [], f"{len(violations)} seeded transfers do not conserve money"
