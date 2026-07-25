import asyncio
import os
from decimal import Decimal

import httpx
import psycopg
import pytest

from database import pool
from factories import create_account, create_branch, create_customer, create_employee
from helpers import count_rows, get_balance
from main import app


@pytest.fixture(scope="module")
def _real_pool():
    pool.open(wait=True, timeout=10)
    yield pool
    pool.close()


@pytest.fixture
def concurrency_test_data(_real_pool):
    created = {"accounts": [], "customers": [], "employees": [], "branches": []}

    def make_account(balance=Decimal("1000.00")):
        conn = psycopg.connect(os.environ["DATABASE_URL"])
        branch = create_branch(conn)
        employee = create_employee(conn, branch_id=branch["id"])
        customer = create_customer(conn)
        account = create_account(
            conn,
            customer_id=customer["id"],
            branch_id=branch["id"],
            opened_by_employee_id=employee["id"],
            balance=balance,
        )
        conn.commit()
        conn.close()
        created["accounts"].append(account["id"])
        created["customers"].append(customer["id"])
        created["employees"].append(employee["id"])
        created["branches"].append(branch["id"])
        return account

    yield make_account

    cleanup = psycopg.connect(os.environ["DATABASE_URL"])
    with cleanup.cursor() as cur:
        for account_id in created["accounts"]:
            cur.execute(
                "DELETE FROM audit_logs WHERE account_id = %s OR related_account_id = %s",
                (account_id, account_id),
            )
            cur.execute("DELETE FROM transactions WHERE account_id = %s", (account_id,))
            cur.execute(
                "DELETE FROM transfers WHERE from_account_id = %s OR to_account_id = %s",
                (account_id, account_id),
            )
        for account_id in created["accounts"]:
            cur.execute("DELETE FROM accounts WHERE id = %s", (account_id,))
        for customer_id in created["customers"]:
            cur.execute("DELETE FROM customers WHERE id = %s", (customer_id,))
        for employee_id in created["employees"]:
            cur.execute("DELETE FROM employees WHERE id = %s", (employee_id,))
        for branch_id in created["branches"]:
            cur.execute("DELETE FROM branches WHERE id = %s", (branch_id,))
    cleanup.commit()
    cleanup.close()


@pytest.fixture
async def concurrent_client(_real_pool):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", timeout=30.0
    ) as client:
        yield client


async def test_concurrent_withdrawals_never_go_negative(
    concurrency_test_data, concurrent_client
):
    account = concurrency_test_data(balance=Decimal("1000.00"))

    responses = await asyncio.gather(
        *[
            concurrent_client.post(
                "/withdraw",
                json={
                    "account_id": account["id"],
                    "amount": "150.00",
                    "idempotency_key": f"concurrent-wd-{i}",
                },
            )
            for i in range(10)
        ]
    )

    succeeded = [r for r in responses if r.status_code == 201]
    failed = [r for r in responses if r.status_code == 409]
    assert len(succeeded) + len(failed) == 10
    assert (
        len(succeeded) == 6
    )  # floor(1000 / 150) = 6, regardless of which 6 win the race

    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        final_balance = get_balance(conn, account["id"])
        assert final_balance == Decimal("100.00")
        assert final_balance >= 0
        assert count_rows(conn, "transactions", account_id=account["id"]) == len(
            succeeded
        )
    finally:
        conn.close()


async def test_concurrent_deposits_all_succeed_and_conserve_money(
    concurrency_test_data, concurrent_client
):
    account = concurrency_test_data(balance=Decimal("500.00"))

    responses = await asyncio.gather(
        *[
            concurrent_client.post(
                "/deposit",
                json={
                    "account_id": account["id"],
                    "amount": "20.00",
                    "idempotency_key": f"concurrent-dep-{i}",
                },
            )
            for i in range(15)
        ]
    )

    assert all(r.status_code == 201 for r in responses)

    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        assert (
            get_balance(conn, account["id"])
            == Decimal("500.00") + Decimal("20.00") * 15
        )
        assert count_rows(conn, "transactions", account_id=account["id"]) == 15
    finally:
        conn.close()


async def test_concurrent_bidirectional_transfers_conserve_total_and_do_not_deadlock(
    concurrency_test_data, concurrent_client
):
    account_a = concurrency_test_data(balance=Decimal("1000.00"))
    account_b = concurrency_test_data(balance=Decimal("1000.00"))

    a_to_b = [
        concurrent_client.post(
            "/transfer",
            json={
                "from_account_id": account_a["id"],
                "to_account_id": account_b["id"],
                "amount": "50.00",
                "idempotency_key": f"concurrent-a-to-b-{i}",
            },
        )
        for i in range(5)
    ]
    b_to_a = [
        concurrent_client.post(
            "/transfer",
            json={
                "from_account_id": account_b["id"],
                "to_account_id": account_a["id"],
                "amount": "30.00",
                "idempotency_key": f"concurrent-b-to-a-{i}",
            },
        )
        for i in range(5)
    ]

    responses = await asyncio.wait_for(asyncio.gather(*a_to_b, *b_to_a), timeout=15)
    assert all(r.status_code == 201 for r in responses), (
        "a transfer failed unexpectedly"
    )

    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        balance_a = get_balance(conn, account_a["id"])
        balance_b = get_balance(conn, account_b["id"])
        assert balance_a + balance_b == Decimal("2000.00")
        assert balance_a == Decimal("900.00")
        assert balance_b == Decimal("1100.00")
    finally:
        conn.close()


async def test_concurrent_identical_requests_do_not_double_process(
    concurrency_test_data, concurrent_client
):
    account = concurrency_test_data(balance=Decimal("500.00"))
    key = "concurrent-duplicate-key-test"

    responses = await asyncio.gather(
        *[
            concurrent_client.post(
                "/deposit",
                json={
                    "account_id": account["id"],
                    "amount": "100.00",
                    "idempotency_key": key,
                },
            )
            for _ in range(10)
        ]
    )

    assert all(r.status_code in (200, 201) for r in responses)
    assert sum(1 for r in responses if r.status_code == 201) == 1

    conn = psycopg.connect(os.environ["DATABASE_URL"])
    try:
        assert get_balance(conn, account["id"]) == Decimal("600.00")
        assert count_rows(conn, "transactions", idempotency_key=key) == 1
    finally:
        conn.close()
