from decimal import Decimal

import psycopg

from exceptions import AccountNotFound, IdempotencyKeyConflict, InsufficientFunds

LARGE_TRANSFER_THRESHOLD = Decimal(
    "2500.00"
)  # keep in sync with scripts/seed/config.py


def _account_exists(conn: psycopg.Connection, account_id: int) -> bool:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT EXISTS(SELECT 1 FROM accounts WHERE id = %s)", (account_id,)
        )
        return cur.fetchone()[0]


def _find_existing_transaction(
    conn: psycopg.Connection, idempotency_key: str
) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.account_id, t.transaction_type, t.amount, t.created_at, al.balance_after
            FROM transactions t
            JOIN audit_logs al ON al.transaction_id = t.id
            WHERE t.idempotency_key = %s
            """,
            (idempotency_key,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "account_id": row[1],
        "transaction_type": row[2],
        "amount": row[3],
        "created_at": row[4],
        "balance_after": row[5],
    }


def _ensure_replay_matches(
    existing, idempotency_key, *, account_id, transaction_type, amount
):
    if (
        existing["account_id"] != account_id
        or existing["transaction_type"] != transaction_type
        or existing["amount"] != amount
    ):
        raise IdempotencyKeyConflict(idempotency_key)


def _apply_transaction(
    conn: psycopg.Connection,
    account_id: int,
    transaction_type: str,
    amount: Decimal,
    idempotency_key: str,
) -> dict:
    existing = _find_existing_transaction(conn, idempotency_key)
    if existing is not None:
        _ensure_replay_matches(
            existing,
            idempotency_key,
            account_id=account_id,
            transaction_type=transaction_type,
            amount=amount,
        )
        return existing

    with conn.cursor() as cur:
        if transaction_type == "deposit":
            cur.execute(
                "UPDATE accounts SET balance = balance + %s WHERE id = %s RETURNING balance",
                (amount, account_id),
            )
            row = cur.fetchone()
            if row is None:
                conn.rollback()
                raise AccountNotFound(account_id)
            balance_after = row[0]
            balance_before = balance_after - amount
        else:
            cur.execute(
                "UPDATE accounts SET balance = balance - %s WHERE id = %s AND balance >= %s RETURNING balance",
                (amount, account_id, amount),
            )
            row = cur.fetchone()
            if row is None:
                if not _account_exists(conn, account_id):
                    conn.rollback()
                    raise AccountNotFound(account_id)
                conn.rollback()
                raise InsufficientFunds(account_id)
            balance_after = row[0]
            balance_before = balance_after + amount

        try:
            cur.execute(
                """
                INSERT INTO transactions
                    (account_id, transaction_type, amount, idempotency_key, performed_by_employee_id)
                VALUES (%s, %s, %s, %s, NULL)
                RETURNING id, created_at
                """,
                (account_id, transaction_type, amount, idempotency_key),
            )
        except psycopg.errors.UniqueViolation as exc:
            conn.rollback()
            if exc.diag.constraint_name != "uq_transactions_idempotency_key":
                raise
            existing = _find_existing_transaction(conn, idempotency_key)
            _ensure_replay_matches(
                existing,
                idempotency_key,
                account_id=account_id,
                transaction_type=transaction_type,
                amount=amount,
            )
            return existing

        transaction_id, created_at = cur.fetchone()

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

    conn.commit()
    return {
        "id": transaction_id,
        "account_id": account_id,
        "transaction_type": transaction_type,
        "amount": amount,
        "balance_after": balance_after,
        "created_at": created_at,
    }


def deposit(
    conn: psycopg.Connection, account_id: int, amount: Decimal, idempotency_key: str
) -> dict:
    return _apply_transaction(conn, account_id, "deposit", amount, idempotency_key)


def withdraw(
    conn: psycopg.Connection, account_id: int, amount: Decimal, idempotency_key: str
) -> dict:
    return _apply_transaction(conn, account_id, "withdrawal", amount, idempotency_key)


def _find_existing_transfer(
    conn: psycopg.Connection, idempotency_key: str
) -> dict | None:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.from_account_id, t.to_account_id, t.amount, t.flagged_for_review, t.created_at,
                   from_log.balance_after, to_log.balance_after
            FROM transfers t
            JOIN audit_logs from_log ON from_log.transfer_id = t.id AND from_log.operation_type = 'transfer_out'
            JOIN audit_logs to_log ON to_log.transfer_id = t.id AND to_log.operation_type = 'transfer_in'
            WHERE t.idempotency_key = %s
            """,
            (idempotency_key,),
        )
        row = cur.fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "from_account_id": row[1],
        "to_account_id": row[2],
        "amount": row[3],
        "flagged_for_review": row[4],
        "created_at": row[5],
        "from_balance_after": row[6],
        "to_balance_after": row[7],
    }


def _ensure_transfer_replay_matches(
    existing, idempotency_key, *, from_account_id, to_account_id, amount
):
    if (
        existing["from_account_id"] != from_account_id
        or existing["to_account_id"] != to_account_id
        or existing["amount"] != amount
    ):
        raise IdempotencyKeyConflict(idempotency_key)


def transfer(
    conn: psycopg.Connection,
    from_account_id: int,
    to_account_id: int,
    amount: Decimal,
    idempotency_key: str,
) -> dict:
    existing = _find_existing_transfer(conn, idempotency_key)
    if existing is not None:
        _ensure_transfer_replay_matches(
            existing,
            idempotency_key,
            from_account_id=from_account_id,
            to_account_id=to_account_id,
            amount=amount,
        )
        return existing

    with conn.cursor() as cur:
        first_id, second_id = sorted([from_account_id, to_account_id])
        first_is_sender = first_id == from_account_id

        def _apply(account_id: int, is_sender: bool) -> Decimal:
            if is_sender:
                cur.execute(
                    "UPDATE accounts SET balance = balance - %s WHERE id = %s AND balance >= %s RETURNING balance",
                    (amount, account_id, amount),
                )
                row = cur.fetchone()
                if row is None:
                    if not _account_exists(conn, account_id):
                        raise AccountNotFound(account_id)
                    raise InsufficientFunds(account_id)
                return row[0]
            else:
                cur.execute(
                    "UPDATE accounts SET balance = balance + %s WHERE id = %s RETURNING balance",
                    (amount, account_id),
                )
                row = cur.fetchone()
                if row is None:
                    raise AccountNotFound(account_id)
                return row[0]

        try:
            first_balance_after = _apply(first_id, first_is_sender)
            second_balance_after = _apply(second_id, not first_is_sender)
        except (AccountNotFound, InsufficientFunds):
            conn.rollback()
            raise

        if first_is_sender:
            from_balance_after, to_balance_after = (
                first_balance_after,
                second_balance_after,
            )
        else:
            to_balance_after, from_balance_after = (
                first_balance_after,
                second_balance_after,
            )

        from_balance_before = from_balance_after + amount
        to_balance_before = to_balance_after - amount
        flagged = amount >= LARGE_TRANSFER_THRESHOLD

        try:
            cur.execute(
                """
                INSERT INTO transfers
                    (from_account_id, to_account_id, amount, idempotency_key,
                     performed_by_employee_id, flagged_for_review)
                VALUES (%s, %s, %s, %s, NULL, %s)
                RETURNING id, created_at
                """,
                (from_account_id, to_account_id, amount, idempotency_key, flagged),
            )
        except psycopg.errors.UniqueViolation as exc:
            conn.rollback()
            if exc.diag.constraint_name != "uq_transfers_idempotency_key":
                raise
            existing = _find_existing_transfer(conn, idempotency_key)
            _ensure_transfer_replay_matches(
                existing,
                idempotency_key,
                from_account_id=from_account_id,
                to_account_id=to_account_id,
                amount=amount,
            )
            return existing

        transfer_id, created_at = cur.fetchone()

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

    conn.commit()
    return {
        "id": transfer_id,
        "from_account_id": from_account_id,
        "to_account_id": to_account_id,
        "amount": amount,
        "from_balance_after": from_balance_after,
        "to_balance_after": to_balance_after,
        "flagged_for_review": flagged,
        "created_at": created_at,
    }
