import psycopg
import pytest

pytestmark = pytest.mark.regression

from factories import create_account, create_branch, create_customer, create_employee
from helpers import expect_db_error


def test_account_cannot_reference_nonexistent_customer(db_connection):
    branch = create_branch(db_connection)
    employee = create_employee(db_connection, branch_id=branch["id"])
    with expect_db_error(db_connection, psycopg.errors.ForeignKeyViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO accounts (customer_id, branch_id, opened_by_employee_id, account_number, balance)
                VALUES (999999999, %s, %s, 'FKTEST0001', 100.00)
                """,
                (branch["id"], employee["id"]),
            )


def test_account_cannot_reference_nonexistent_branch(db_connection):
    customer = create_customer(db_connection)
    branch = create_branch(db_connection)
    employee = create_employee(db_connection, branch_id=branch["id"])
    with expect_db_error(db_connection, psycopg.errors.ForeignKeyViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO accounts (customer_id, branch_id, opened_by_employee_id, account_number, balance)
                VALUES (%s, 999999999, %s, 'FKTEST0002', 100.00)
                """,
                (customer["id"], employee["id"]),
            )


def test_transaction_cannot_reference_nonexistent_account(db_connection):
    with expect_db_error(db_connection, psycopg.errors.ForeignKeyViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transactions (account_id, transaction_type, amount, idempotency_key)
                VALUES (999999999, 'deposit', 100.00, 'FKTEST0003')
                """
            )


def test_transfer_cannot_reference_nonexistent_from_account(db_connection):
    to_account = create_account(db_connection)
    with expect_db_error(db_connection, psycopg.errors.ForeignKeyViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO transfers (from_account_id, to_account_id, amount, idempotency_key)
                VALUES (999999999, %s, 100.00, 'FKTEST0004')
                """,
                (to_account["id"],),
            )


def test_employee_cannot_reference_nonexistent_branch(db_connection):
    with expect_db_error(db_connection, psycopg.errors.ForeignKeyViolation):
        with db_connection.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (branch_id, employee_code, full_name)
                VALUES (999999999, 'FKTESTEMP01', 'Test Employee')
                """
            )
