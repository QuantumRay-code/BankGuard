import os

import httpx
import psycopg
import pytest
from dotenv import load_dotenv

from database import get_db
from main import app


class _SavepointConnection:
    """
    Wraps a real psycopg connection so .commit()/.rollback() operate on a
    SAVEPOINT instead of the real transaction. Necessary because ledger.py
    calls conn.commit() as part of normal successful operation — without
    this, that commit would be permanent and no test rollback could undo it.
    """

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn
        with conn.cursor() as cur:
            cur.execute("SAVEPOINT api_boundary")

    def commit(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("RELEASE SAVEPOINT api_boundary")
            cur.execute("SAVEPOINT api_boundary")

    def rollback(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("ROLLBACK TO SAVEPOINT api_boundary")
            cur.execute("SAVEPOINT api_boundary")

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def db_connection():
    load_dotenv()
    raw_conn = psycopg.connect(os.environ["DATABASE_URL"])
    wrapped = _SavepointConnection(raw_conn)
    yield wrapped
    raw_conn.rollback()
    raw_conn.close()


@pytest.fixture
async def api_client(db_connection):
    def override_get_db():
        yield db_connection

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
