from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator


class DepositRequest(BaseModel):
    account_id: int
    amount: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=100)


class WithdrawRequest(BaseModel):
    account_id: int
    amount: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=100)


class TransferRequest(BaseModel):
    from_account_id: int
    to_account_id: int
    amount: Decimal = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def check_not_self_transfer(self) -> "TransferRequest":
        if self.from_account_id == self.to_account_id:
            raise ValueError("from_account_id and to_account_id must be different.")
        return self


class TransactionResponse(BaseModel):
    id: int
    account_id: int
    transaction_type: str
    amount: Decimal
    balance_after: Decimal
    created_at: datetime


class TransferResponse(BaseModel):
    id: int
    from_account_id: int
    to_account_id: int
    amount: Decimal
    from_balance_after: Decimal
    to_balance_after: Decimal
    flagged_for_review: bool
    created_at: datetime


class AccountResponse(BaseModel):
    id: int
    customer_id: int
    branch_id: int
    opened_by_employee_id: int
    account_number: str
    balance: Decimal
    created_at: datetime
