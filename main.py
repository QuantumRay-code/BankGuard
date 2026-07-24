from contextlib import asynccontextmanager

import psycopg
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse

from database import get_db, pool
from exceptions import (
    AccountNotFound,
    IdempotencyKeyConflict,
    InsufficientFunds,
    TransactionNotFound,
)
from ledger import deposit as ledger_deposit
from ledger import transfer as ledger_transfer
from ledger import withdraw as ledger_withdraw
from schemas import (
    AccountResponse,
    DepositRequest,
    TransactionResponse,
    TransferRequest,
    TransferResponse,
    WithdrawRequest,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool.open(wait=True, timeout=10)
    yield
    pool.close()


app = FastAPI(title="BankGuard API", lifespan=lifespan)


@app.exception_handler(AccountNotFound)
def handle_account_not_found(request, exc: AccountNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(TransactionNotFound)
def handle_transaction_not_found(request, exc: TransactionNotFound):
    return JSONResponse(status_code=404, content={"detail": str(exc)})


@app.exception_handler(InsufficientFunds)
def handle_insufficient_funds(request, exc: InsufficientFunds):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.exception_handler(IdempotencyKeyConflict)
def handle_idempotency_conflict(request, exc: IdempotencyKeyConflict):
    return JSONResponse(status_code=409, content={"detail": str(exc)})


@app.post("/deposit", response_model=TransactionResponse, status_code=201)
def post_deposit(payload: DepositRequest, conn: psycopg.Connection = Depends(get_db)):
    return ledger_deposit(
        conn, payload.account_id, payload.amount, payload.idempotency_key
    )


@app.post("/withdraw", response_model=TransactionResponse, status_code=201)
def post_withdraw(payload: WithdrawRequest, conn: psycopg.Connection = Depends(get_db)):
    return ledger_withdraw(
        conn, payload.account_id, payload.amount, payload.idempotency_key
    )


@app.post("/transfer", response_model=TransferResponse, status_code=201)
def post_transfer(payload: TransferRequest, conn: psycopg.Connection = Depends(get_db)):
    return ledger_transfer(
        conn,
        payload.from_account_id,
        payload.to_account_id,
        payload.amount,
        payload.idempotency_key,
    )


@app.get("/accounts/{account_id}", response_model=AccountResponse)
def get_account(account_id: int, conn: psycopg.Connection = Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, customer_id, branch_id, opened_by_employee_id, account_number, balance, created_at
            FROM accounts WHERE id = %s
            """,
            (account_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise AccountNotFound(account_id)
    return {
        "id": row[0],
        "customer_id": row[1],
        "branch_id": row[2],
        "opened_by_employee_id": row[3],
        "account_number": row[4],
        "balance": row[5],
        "created_at": row[6],
    }


@app.get("/transactions/{transaction_id}", response_model=TransactionResponse)
def get_transaction(transaction_id: int, conn: psycopg.Connection = Depends(get_db)):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.account_id, t.transaction_type, t.amount, al.balance_after, t.created_at
            FROM transactions t
            JOIN audit_logs al ON al.transaction_id = t.id
            WHERE t.id = %s
            """,
            (transaction_id,),
        )
        row = cur.fetchone()
    if row is None:
        raise TransactionNotFound(transaction_id)
    return {
        "id": row[0],
        "account_id": row[1],
        "transaction_type": row[2],
        "amount": row[3],
        "balance_after": row[4],
        "created_at": row[5],
    }
