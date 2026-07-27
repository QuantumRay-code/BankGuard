import psycopg
import pytest

pytestmark = pytest.mark.smoke

from factories import create_account, create_customer
from helpers import expect_db_error


def test_negative_balance_is_rejected(db_connection):
    account = create_account(db_connection)
    with expect_db_error(db_connection, psycopg.errors.CheckViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                "UPDATE accounts SET balance = -50.00 WHERE id = %s", (account["id"],)
            )


def test_zero_amount_transaction_is_rejected(db_connection):
    account = create_account(db_connection)
    with expect_db_error(db_connection, psycopg.errors.CheckViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (account_id, transaction_type, amount, idempotency_key)
                VALUES (%s, 'deposit', 0, 'ZEROTEST001')
                """,
                (account["id"],),
            )


def test_invalid_transaction_type_is_rejected(db_connection):
    account = create_account(db_connection)
    with expect_db_error(db_connection, psycopg.errors.CheckViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (account_id, transaction_type, amount, idempotency_key)
                VALUES (%s, 'not_a_real_type', 100.00, 'BADTYPE001')
                """,
                (account["id"],),
            )


def test_self_transfer_is_rejected_at_db_level(db_connection):
    account = create_account(db_connection)
    with expect_db_error(db_connection, psycopg.errors.CheckViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transfers (from_account_id, to_account_id, amount, idempotency_key)
                VALUES (%s, %s, 100.00, 'SELFTEST001')
                """,
                (account["id"], account["id"]),
            )


def test_duplicate_email_is_rejected(db_connection):
    create_customer(db_connection, email="duplicate.test@example.com")
    with expect_db_error(db_connection, psycopg.errors.UniqueViolation):
        create_customer(db_connection, email="duplicate.test@example.com")


def test_duplicate_account_number_is_rejected(db_connection):
    existing = create_account(db_connection)
    with expect_db_error(db_connection, psycopg.errors.UniqueViolation):
        create_account(db_connection, account_number=existing["account_number"])


def test_null_customer_name_is_rejected(db_connection):
    with expect_db_error(db_connection, psycopg.errors.NotNullViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                "INSERT INTO customers (full_name, email, phone_number) VALUES (NULL, 'nulltest@example.com', '555-0000')"
            )
