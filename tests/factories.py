import random
import uuid
from decimal import Decimal

import psycopg
from faker import Faker

fake = Faker()


def create_branch(conn: psycopg.Connection, **overrides) -> dict:
    values = {
        "branch_code": f"TEST{random.randint(100000, 999999)}",
        "name": f"{fake.city()} Test Branch",
        "city": fake.city(),
    }
    values.update(overrides)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO branches (branch_code, name, city)
            VALUES (%(branch_code)s, %(name)s, %(city)s)
            RETURNING id, branch_code, name, city, created_at
            """,
            values,
        )
        row = cur.fetchone()
    return {
        "id": row[0],
        "branch_code": row[1],
        "name": row[2],
        "city": row[3],
        "created_at": row[4],
    }


def create_employee(
    conn: psycopg.Connection, branch_id: int | None = None, **overrides
) -> dict:
    if branch_id is None:
        branch_id = create_branch(conn)["id"]
    values = {
        "branch_id": branch_id,
        "employee_code": f"TESTEMP{random.randint(100000, 999999)}",
        "full_name": fake.name(),
    }
    values.update(overrides)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO employees (branch_id, employee_code, full_name)
            VALUES (%(branch_id)s, %(employee_code)s, %(full_name)s)
            RETURNING id, branch_id, employee_code, full_name, created_at
            """,
            values,
        )
        row = cur.fetchone()
    return {
        "id": row[0],
        "branch_id": row[1],
        "employee_code": row[2],
        "full_name": row[3],
        "created_at": row[4],
    }


def create_customer(conn: psycopg.Connection, **overrides) -> dict:
    values = {
        "full_name": fake.name(),
        "email": f"test.{uuid.uuid4().hex[:12]}@example.com",
        "phone_number": fake.phone_number()[:20],
    }
    values.update(overrides)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO customers (full_name, email, phone_number)
            VALUES (%(full_name)s, %(email)s, %(phone_number)s)
            RETURNING id, full_name, email, phone_number, created_at
            """,
            values,
        )
        row = cur.fetchone()
    return {
        "id": row[0],
        "full_name": row[1],
        "email": row[2],
        "phone_number": row[3],
        "created_at": row[4],
    }


def create_account(
    conn: psycopg.Connection,
    customer_id: int | None = None,
    branch_id: int | None = None,
    opened_by_employee_id: int | None = None,
    balance: Decimal = Decimal("1000.00"),
    **overrides,
) -> dict:
    if customer_id is None:
        customer_id = create_customer(conn)["id"]
    if branch_id is None:
        branch_id = create_branch(conn)["id"]
    if opened_by_employee_id is None:
        opened_by_employee_id = create_employee(conn, branch_id=branch_id)["id"]

    values = {
        "customer_id": customer_id,
        "branch_id": branch_id,
        "opened_by_employee_id": opened_by_employee_id,
        "account_number": f"TEST{random.randint(10**10, 10**11 - 1)}",
        "balance": balance,
    }
    values.update(overrides)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO accounts
                (customer_id, branch_id, opened_by_employee_id, account_number, balance)
            VALUES (%(customer_id)s, %(branch_id)s, %(opened_by_employee_id)s,
                    %(account_number)s, %(balance)s)
            RETURNING id, customer_id, branch_id, opened_by_employee_id,
                      account_number, balance, created_at
            """,
            values,
        )
        row = cur.fetchone()
    return {
        "id": row[0],
        "customer_id": row[1],
        "branch_id": row[2],
        "opened_by_employee_id": row[3],
        "account_number": row[4],
        "balance": row[5],
        "created_at": row[6],
    }


def create_transaction(
    conn: psycopg.Connection,
    account_id: int | None = None,
    transaction_type: str = "deposit",
    amount: Decimal = Decimal("100.00"),
    **overrides,
) -> dict:
    if account_id is None:
        account_id = create_account(conn)["id"]

    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM accounts WHERE id = %s", (account_id,))
        balance_before = cur.fetchone()[0]
    balance_after = (
        balance_before + amount
        if transaction_type == "deposit"
        else balance_before - amount
    )

    values = {
        "account_id": account_id,
        "transaction_type": transaction_type,
        "amount": amount,
        "idempotency_key": str(uuid.uuid4()),
        "performed_by_employee_id": None,
    }
    values.update(overrides)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transactions
                (account_id, transaction_type, amount, idempotency_key, performed_by_employee_id)
            VALUES (%(account_id)s, %(transaction_type)s, %(amount)s,
                    %(idempotency_key)s, %(performed_by_employee_id)s)
            RETURNING id, account_id, transaction_type, amount, idempotency_key, created_at
            """,
            values,
        )
        row = cur.fetchone()
        transaction_id, created_at = row[0], row[5]

        cur.execute(
            """
            INSERT INTO audit_logs
                (operation_type, transaction_id, account_id, amount, balance_before, balance_after, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                transaction_type,
                transaction_id,
                account_id,
                amount,
                balance_before,
                balance_after,
                created_at,
            ),
        )
        cur.execute(
            "UPDATE accounts SET balance = %s WHERE id = %s",
            (balance_after, account_id),
        )

    return {
        "id": row[0],
        "account_id": row[1],
        "transaction_type": row[2],
        "amount": row[3],
        "idempotency_key": row[4],
        "created_at": row[5],
        "balance_after": balance_after,
    }


def create_transfer(
    conn: psycopg.Connection,
    from_account_id: int | None = None,
    to_account_id: int | None = None,
    amount: Decimal = Decimal("100.00"),
    **overrides,
) -> dict:
    if from_account_id is None:
        from_account_id = create_account(conn)["id"]
    if to_account_id is None:
        to_account_id = create_account(conn)["id"]

    with conn.cursor() as cur:
        cur.execute("SELECT balance FROM accounts WHERE id = %s", (from_account_id,))
        from_balance_before = cur.fetchone()[0]
        cur.execute("SELECT balance FROM accounts WHERE id = %s", (to_account_id,))
        to_balance_before = cur.fetchone()[0]

    from_balance_after = from_balance_before - amount
    to_balance_after = to_balance_before + amount

    values = {
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "amount": amount,
        "idempotency_key": str(uuid.uuid4()),
        "performed_by_employee_id": None,
        "flagged_for_review": False,
    }
    values.update(overrides)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO transfers
                (from_account_id, to_account_id, amount, idempotency_key,
                 performed_by_employee_id, flagged_for_review)
            VALUES (%(from_account_id)s, %(to_account_id)s, %(amount)s, %(idempotency_key)s,
                    %(performed_by_employee_id)s, %(flagged_for_review)s)
            RETURNING id, from_account_id, to_account_id, amount, idempotency_key,
                      flagged_for_review, created_at
            """,
            values,
        )
        row = cur.fetchone()
        transfer_id, created_at = row[0], row[6]

        cur.execute(
            """
            INSERT INTO audit_logs
                (operation_type, transfer_id, account_id, related_account_id,
                 amount, balance_before, balance_after, created_at)
            VALUES ('transfer_out', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                transfer_id,
                from_account_id,
                to_account_id,
                amount,
                from_balance_before,
                from_balance_after,
                created_at,
            ),
        )
        cur.execute(
            """
            INSERT INTO audit_logs
                (operation_type, transfer_id, account_id, related_account_id,
                 amount, balance_before, balance_after, created_at)
            VALUES ('transfer_in', %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                transfer_id,
                to_account_id,
                from_account_id,
                amount,
                to_balance_before,
                to_balance_after,
                created_at,
            ),
        )
        cur.execute(
            "UPDATE accounts SET balance = %s WHERE id = %s",
            (from_balance_after, from_account_id),
        )
        cur.execute(
            "UPDATE accounts SET balance = %s WHERE id = %s",
            (to_balance_after, to_account_id),
        )

    return {
        "id": row[0],
        "from_account_id": row[1],
        "to_account_id": row[2],
        "amount": row[3],
        "idempotency_key": row[4],
        "flagged_for_review": row[5],
        "created_at": row[6],
        "from_balance_after": from_balance_after,
        "to_balance_after": to_balance_after,
    }
