import random
import uuid
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

import psycopg

from . import config

TWOPLACES = Decimal("0.01")


def _round(value: Decimal) -> Decimal:
    return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)


def _deterministic_uuid() -> str:

    return str(uuid.UUID(int=random.getrandbits(128)))


def _maybe_employee(employee_ids: list[int]) -> int | None:
    if random.random() < config.EMPLOYEE_ASSISTED_RATE:
        return random.choice(employee_ids)
    return None


def _next_starting_id(conn: psycopg.Connection, table: str) -> int:
    with conn.cursor() as cur:
        cur.execute(f"SELECT COALESCE(MAX(id), 0) FROM {table}")
        return cur.fetchone()[0] + 1


class _BatchWriter:
    def __init__(self, conn: psycopg.Connection, table: str, columns: list[str]):
        self.conn = conn
        self.table = table
        self.columns = columns
        self.rows: list[tuple] = []

    def add(self, row: tuple) -> None:
        self.rows.append(row)

    def flush(self) -> None:
        if not self.rows:
            return
        column_list = ", ".join(self.columns)
        with self.conn.cursor() as cur:
            with cur.copy(f"COPY {self.table} ({column_list}) FROM STDIN") as copy:
                for row in self.rows:
                    copy.write_row(row)
        self.conn.commit()
        self.rows.clear()


def generate_organic_activity(
    conn: psycopg.Connection,
    accounts: list[dict],
    employee_ids: list[int],
    history_end: datetime,
) -> tuple[dict[int, Decimal], dict[int, datetime]]:
    """
    Returns (balances, last_event_ts) after organic activity — both keyed
    by account_id — so generate_transfers can anchor transfer timestamps
    strictly after each account's most recent event, keeping created_at
    ordering consistent with the order balances were applied.
    """
    next_tx_id = _next_starting_id(conn, "transactions")
    next_audit_id = _next_starting_id(conn, "audit_logs")

    tx_writer = _BatchWriter(
        conn,
        "transactions",
        [
            "id",
            "account_id",
            "transaction_type",
            "amount",
            "idempotency_key",
            "performed_by_employee_id",
            "created_at",
        ],
    )
    audit_writer = _BatchWriter(
        conn,
        "audit_logs",
        [
            "id",
            "operation_type",
            "transaction_id",
            "account_id",
            "amount",
            "balance_before",
            "balance_after",
            "created_at",
        ],
    )

    balances: dict[int, Decimal] = {}
    last_event_ts: dict[int, datetime] = {}
    processed = 0

    for account in accounts:
        account_id = account["id"]
        created_at = account["created_at"]

        opening_amount = _round(
            Decimal(str(random.uniform(*config.OPENING_DEPOSIT_RANGE)))
        )
        events = [(created_at, "deposit", opening_amount)]
        running = opening_amount

        extra_count = random.randint(*config.TRANSACTIONS_PER_ACCOUNT_RANGE)
        span = (history_end - created_at).total_seconds()
        timestamps = sorted(
            created_at + timedelta(seconds=random.uniform(0, span))
            for _ in range(extra_count)
        )

        for ts in timestamps:
            if random.random() < 0.5 and running > 0:
                fraction = Decimal(
                    str(random.uniform(*config.WITHDRAWAL_FRACTION_RANGE))
                )
                amount = _round(running * fraction)
                if amount <= 0:
                    continue
                events.append((ts, "withdrawal", amount))
                running = _round(running - amount)
            else:
                amount = _round(
                    Decimal(str(random.uniform(*config.DEPOSIT_AMOUNT_RANGE)))
                )
                events.append((ts, "deposit", amount))
                running = _round(running + amount)

        running = Decimal("0.00")
        for ts, tx_type, amount in events:
            balance_before = running
            running = (
                _round(running + amount)
                if tx_type == "deposit"
                else _round(running - amount)
            )

            tx_id = next_tx_id
            next_tx_id += 1
            performed_by = _maybe_employee(employee_ids)

            tx_writer.add(
                (
                    tx_id,
                    account_id,
                    tx_type,
                    amount,
                    _deterministic_uuid(),
                    performed_by,
                    ts,
                )
            )
            audit_writer.add(
                (
                    next_audit_id,
                    tx_type,
                    tx_id,
                    account_id,
                    amount,
                    balance_before,
                    running,
                    ts,
                )
            )
            next_audit_id += 1

        balances[account_id] = running
        last_event_ts[account_id] = events[-1][0]
        processed += 1

        if len(tx_writer.rows) >= config.COPY_BATCH_SIZE:
            tx_writer.flush()
            audit_writer.flush()
            print(
                f"  ... organic activity: {processed}/{len(accounts)} accounts processed"
            )

    tx_writer.flush()
    audit_writer.flush()
    return balances, last_event_ts


def generate_transfers(
    conn: psycopg.Connection,
    account_ids: list[int],
    balances: dict[int, Decimal],
    last_event_ts: dict[int, datetime],
    employee_ids: list[int],
    history_end: datetime,
) -> dict[int, Decimal]:
    """
    Each transfer's timestamp is anchored strictly after both accounts'
    most recent event (last_event_ts), which is updated as we go — this
    keeps created_at ordering consistent with the order balances are
    applied.
    """
    next_transfer_id = _next_starting_id(conn, "transfers")
    next_audit_id = _next_starting_id(conn, "audit_logs")

    transfer_writer = _BatchWriter(
        conn,
        "transfers",
        [
            "id",
            "from_account_id",
            "to_account_id",
            "amount",
            "idempotency_key",
            "performed_by_employee_id",
            "flagged_for_review",
            "created_at",
        ],
    )
    audit_writer = _BatchWriter(
        conn,
        "audit_logs",
        [
            "id",
            "operation_type",
            "transfer_id",
            "account_id",
            "related_account_id",
            "amount",
            "balance_before",
            "balance_after",
            "created_at",
        ],
    )

    senders = [
        acc_id
        for acc_id in account_ids
        if random.random() < config.TRANSFER_PARTICIPATION_RATE
    ]
    processed = 0

    for sender_id in senders:
        transfer_count = random.randint(*config.TRANSFERS_PER_SENDER_RANGE)
        for _ in range(transfer_count):
            if balances[sender_id] <= 0:
                break

            receiver_id = random.choice(account_ids)
            if receiver_id == sender_id:
                continue

            fraction = Decimal(str(random.uniform(*config.TRANSFER_FRACTION_RANGE)))
            amount = _round(balances[sender_id] * fraction)
            if amount <= 0:
                continue

            earliest = max(last_event_ts[sender_id], last_event_ts[receiver_id])
            span = max((history_end - earliest).total_seconds(), 0)
            ts = (
                earliest + timedelta(seconds=random.uniform(0, span))
                if span > 0
                else earliest
            )

            flagged = amount >= config.LARGE_TRANSFER_THRESHOLD
            performed_by = _maybe_employee(employee_ids)
            transfer_id = next_transfer_id
            next_transfer_id += 1

            transfer_writer.add(
                (
                    transfer_id,
                    sender_id,
                    receiver_id,
                    amount,
                    _deterministic_uuid(),
                    performed_by,
                    flagged,
                    ts,
                )
            )

            sender_before = balances[sender_id]
            balances[sender_id] = _round(balances[sender_id] - amount)
            audit_writer.add(
                (
                    next_audit_id,
                    "transfer_out",
                    transfer_id,
                    sender_id,
                    receiver_id,
                    amount,
                    sender_before,
                    balances[sender_id],
                    ts,
                )
            )
            next_audit_id += 1

            receiver_before = balances[receiver_id]
            balances[receiver_id] = _round(balances[receiver_id] + amount)
            audit_writer.add(
                (
                    next_audit_id,
                    "transfer_in",
                    transfer_id,
                    receiver_id,
                    sender_id,
                    amount,
                    receiver_before,
                    balances[receiver_id],
                    ts,
                )
            )
            next_audit_id += 1

            last_event_ts[sender_id] = ts
            last_event_ts[receiver_id] = ts

        processed += 1
        if len(transfer_writer.rows) >= config.COPY_BATCH_SIZE:
            transfer_writer.flush()
            audit_writer.flush()
            print(
                f"  ... transfers: {processed}/{len(senders)} sending accounts processed"
            )

    transfer_writer.flush()
    audit_writer.flush()
    return balances
