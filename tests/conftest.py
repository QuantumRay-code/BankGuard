import os

import httpx
import psycopg
import pytest
from dotenv import load_dotenv

from database import get_db
from main import app


class _SavepointConnection:
    """
    Wraps a real psycopg connection so .commit()/.rollback() calls made
    by application code operate against a savepoint scoped to the
    current request, rather than the real transaction.
    """

    def __init__(self, conn: psycopg.Connection):
        self._conn = conn
        self._savepoint_name = "request_boundary"

    def begin_checkpoint(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"SAVEPOINT {self._savepoint_name}")

    def commit(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"RELEASE SAVEPOINT {self._savepoint_name}")

    def rollback(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"ROLLBACK TO SAVEPOINT {self._savepoint_name}")
            cur.execute(f"RELEASE SAVEPOINT {self._savepoint_name}")

    def __getattr__(self, name):
        return getattr(self._conn, name)


@pytest.fixture
def db_connection():
    load_dotenv()
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    yield conn
    conn.rollback()
    conn.close()


@pytest.fixture
async def api_client(db_connection):
    wrapped = _SavepointConnection(db_connection)

    def override_get_db():
        wrapped.begin_checkpoint()
        yield wrapped

    app.dependency_overrides[get_db] = override_get_db
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
