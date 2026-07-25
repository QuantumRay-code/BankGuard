import os

from dotenv import load_dotenv
from psycopg_pool import ConnectionPool

load_dotenv()

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL not set. Check your .env file.")

pool = ConnectionPool(conninfo=DATABASE_URL, open=False, min_size=5, max_size=20)


def get_db():
    with pool.connection() as conn:
        yield conn
