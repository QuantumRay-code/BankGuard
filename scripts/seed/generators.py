"""
Generators for BankGuard's supporting entities: branches, employees,
customers, and accounts.

These tables stay in the thousands even at the Large profile, so plain
executemany() (pipelined automatically by psycopg3) is fast enough here.
The high-volume ledger simulation (transactions/transfers/audit_logs)
lives in ledger.py and uses COPY instead.
"""

import random
from datetime import datetime, timedelta

from faker import Faker

from . import config

fake = Faker()


def generate_branches(customer_count: int) -> list[tuple]:
    """Rows for branches: (branch_code, name, city)."""
    branch_count = max(config.MIN_BRANCHES, customer_count // config.BRANCH_DENSITY)
    rows = []
    for i in range(1, branch_count + 1):
        city = fake.city()
        rows.append((f"BR{i:04d}", f"{city} Branch", city))
    return rows


def generate_employees(branch_ids: list[int]) -> tuple[list[tuple], dict[int, range]]:
    """
    Rows for employees: (branch_id, employee_code, full_name).

    Also returns a branch_id -> range mapping, indexing into the returned
    rows list (not employee IDs, since those don't exist yet before
    insertion). The caller zips this against the post-insert employee IDs
    to build a branch_id -> [employee_id] map.
    """
    rows = []
    counter = 1
    branch_row_ranges: dict[int, range] = {}
    for branch_id in branch_ids:
        employee_count = random.randint(*config.EMPLOYEES_PER_BRANCH_RANGE)
        start = len(rows)
        for _ in range(employee_count):
            rows.append((branch_id, f"EMP{counter:06d}", fake.name()))
            counter += 1
        branch_row_ranges[branch_id] = range(start, len(rows))
    return rows, branch_row_ranges


def generate_customers(customer_count: int) -> list[tuple]:
    """Rows for customers: (full_name, email, phone_number)."""
    rows = []
    for _ in range(customer_count):
        rows.append((fake.name(), fake.unique.email(), fake.phone_number()[:20]))
    return rows


def _pick_account_count() -> int:
    values = list(config.ACCOUNTS_PER_CUSTOMER_WEIGHTS.keys())
    weights = list(config.ACCOUNTS_PER_CUSTOMER_WEIGHTS.values())
    return random.choices(values, weights=weights, k=1)[0]


def generate_accounts(
    customer_ids: list[int],
    branch_ids: list[int],
    employee_ids_by_branch: dict[int, list[int]],
    history_start: datetime,
    history_end: datetime,
) -> list[tuple]:
    """
    Rows for accounts: (customer_id, branch_id, opened_by_employee_id,
    account_number, created_at).

    created_at is assigned explicitly (not left to the DB default) so the
    account's "opening date" can anchor the start of its transaction
    history in ledger.py — an account can't have a transaction before it
    exists. At least 30 days of runway before history_end is reserved so
    there's room for subsequent activity.
    """
    rows = []
    counter = 1
    latest_possible_start = history_end - timedelta(days=30)
    window_seconds = (latest_possible_start - history_start).total_seconds()

    for customer_id in customer_ids:
        for _ in range(_pick_account_count()):
            branch_id = random.choice(branch_ids)
            opened_by_employee_id = random.choice(employee_ids_by_branch[branch_id])
            account_number = f"{counter:012d}"
            created_at = history_start + timedelta(
                seconds=random.uniform(0, window_seconds)
            )
            rows.append(
                (
                    customer_id,
                    branch_id,
                    opened_by_employee_id,
                    account_number,
                    created_at,
                )
            )
            counter += 1
    return rows
