import sys
from pathlib import Path
import psycopg
from db import get_connection

MIGRATIONS_DIR = Path(__file__).parent.parent / "migrations"


def ensure_migrations_table(conn: psycopg.Connection) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     VARCHAR(255) PRIMARY KEY,
                applied_at  TIMESTAMPTZ NOT NULL DEFAULT now()
            );
            """
        )
    conn.commit()


def get_applied_versions(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations;")
        return {row[0] for row in cur.fetchall()}


def apply_migration(conn: psycopg.Connection, filepath: Path) -> None:
    sql = filepath.read_text(encoding="utf-8")
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    with conn.cursor() as cur:
        for statement in statements:
            cur.execute(statement)
        cur.execute(
            "INSERT INTO schema_migrations (version) VALUES (%s);",
            (filepath.name,),
        )
    conn.commit()


def run_migrations() -> None:
    conn = get_connection()
    try:
        ensure_migrations_table(conn)
        applied = get_applied_versions(conn)
        migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not migration_files:
            print(f"No migration files found in {MIGRATIONS_DIR}")
            return
        pending = [f for f in migration_files if f.name not in applied]
        if not pending:
            print("Database is already up to date. No migrations to apply.")
            return
        for filepath in pending:
            print(f"Applying {filepath.name} ...")
            try:
                apply_migration(conn, filepath)
                print("  -> success")
            except Exception as exc:
                conn.rollback()
                print(f"  -> FAILED: {exc}")
                sys.exit(1)
        print(f"\nApplied {len(pending)} migration(s) successfully.")
    finally:
        conn.close()


if __name__ == "__main__":
    run_migrations()
