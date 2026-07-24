class AccountNotFound(Exception):
    def __init__(self, account_id: int):
        self.account_id = account_id
        super().__init__(f"Account {account_id} not found.")


class TransactionNotFound(Exception):
    def __init__(self, transaction_id: int):
        self.transaction_id = transaction_id
        super().__init__(f"Transaction {transaction_id} not found.")


class InsufficientFunds(Exception):
    def __init__(self, account_id: int):
        self.account_id = account_id
        super().__init__(f"Account {account_id} has insufficient funds.")


class IdempotencyKeyConflict(Exception):
    def __init__(self, idempotency_key: str):
        self.idempotency_key = idempotency_key
        super().__init__(
            f"Idempotency key '{idempotency_key}' was already used with different parameters."
        )
