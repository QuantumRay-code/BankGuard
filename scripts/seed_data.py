import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from faker import Faker

from db import get_connection
from seed import config, generators, ledger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Seed BankGuard with a deterministic dataset."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--profile", choices=sorted(config.PROFILES), help="Named dataset profile."
    )
    group.add_argument(
        "--customers", type=int, help="Custom customer count, overriding --profile."
    )
    return parser.parse_args()


def resolve_customer_count(args: argparse.Namespace) -> int:
    if args.customers is not None:
        if args.customers <= 0:
            print("ERROR: --customers must be a positive integer.")
            sys.exit(1)
        return args.customers
    profile = args.profile or config.DEFAULT_PROFILE
    return config.PROFILES[profile]["customers"]


def ensure_database_is_empty(conn) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM customers")
        count = cur.fetchone()[0]
    if count > 0:
        print(
            "ERROR: customers table already has data — refusing to seed on top of it.\n"
            "Reset the database first:\n"
            "  docker compose down -v\n"
            "  docker compose up -d\n"
            "  uv run python scripts/run_migrations.py"
        )
        sys.exit(1)


def insert_and_fetch_ids(
    conn, table: str, columns: list[str], rows: list[tuple]
) -> list[int]:

    if not rows:
        return []
    placeholders = ", ".join(["%s"] * len(columns))
    column_list = ", ".join(columns)
    sql = f"INSERT INTO {table} ({column_list}) VALUES ({placeholders})"
    with conn.cursor() as cur:
        cur.executemany(sql, rows)
        cur.execute(f"SELECT id FROM {table} ORDER BY id")
        ids = [row[0] for row in cur.fetchall()]
    conn.commit()
    return ids


def update_final_balances(conn, balances: dict[int, Decimal]) -> None:
    rows = [(balance, account_id) for account_id, balance in balances.items()]
    with conn.cursor() as cur:
        cur.executemany("UPDATE accounts SET balance = %s WHERE id = %s", rows)
    conn.commit()


def main() -> None:
    args = parse_args()
    customer_count = resolve_customer_count(args)

    random.seed(config.RANDOM_SEED)
    Faker.seed(config.RANDOM_SEED)

    conn = get_connection()
    try:
        ensure_database_is_empty(conn)
        print(f"Seeding {customer_count} customers ...")

        history_end = datetime.now(timezone.utc)
        history_start = history_end - timedelta(days=30 * config.HISTORY_MONTHS)

        print("Generating branches ...")
        branch_rows = generators.generate_branches(customer_count)
        branch_ids = insert_and_fetch_ids(
            conn, "branches", ["branch_code", "name", "city"], branch_rows
        )

        print("Generating employees ...")
        employee_rows, branch_row_ranges = generators.generate_employees(branch_ids)
        employee_ids = insert_and_fetch_ids(
            conn,
            "employees",
            ["branch_id", "employee_code", "full_name"],
            employee_rows,
        )
        employee_ids_by_branch = {
            branch_id: [employee_ids[i] for i in row_range]
            for branch_id, row_range in branch_row_ranges.items()
        }

        print("Generating customers ...")
        customer_rows = generators.generate_customers(customer_count)
        customer_ids = insert_and_fetch_ids(
            conn, "customers", ["full_name", "email", "phone_number"], customer_rows
        )

        print("Generating accounts ...")
        account_rows = generators.generate_accounts(
            customer_ids, branch_ids, employee_ids_by_branch, history_start, history_end
        )
        account_ids = insert_and_fetch_ids(
            conn,
            "accounts",
            [
                "customer_id",
                "branch_id",
                "opened_by_employee_id",
                "account_number",
                "created_at",
            ],
            account_rows,
        )
        account_created_at = {
            aid: row[4] for aid, row in zip(account_ids, account_rows)
        }
        accounts = [
            {"id": aid, "created_at": account_created_at[aid]} for aid in account_ids
        ]

        print("Generating organic transaction history ...")
        balances, last_event_ts = ledger.generate_organic_activity(
            conn, accounts, employee_ids, history_end
        )

        print("Generating transfers ...")
        balances = ledger.generate_transfers(
            conn, account_ids, balances, last_event_ts, employee_ids, history_end
        )

        print("Writing final account balances ...")
        update_final_balances(conn, balances)

        print(
            f"\nDone. Seeded {len(customer_ids)} customers, {len(account_ids)} accounts, "
            f"{len(branch_ids)} branches, {len(employee_ids)} employees."
        )
    finally:
        conn.close()


if __name__ == "__main__":
    main()
