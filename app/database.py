import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_DB_PATH = "automation.db"


def get_database_path() -> str:
    return os.getenv("AUTOMATION_DB_PATH", DEFAULT_DB_PATH)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(get_database_path(), timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def transaction(*, immediate: bool = False) -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
        if immediate:
            connection.execute("BEGIN IMMEDIATE")
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    with transaction() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS automation_requests (
                request_id TEXT PRIMARY KEY,
                idempotency_key TEXT UNIQUE,
                process TEXT NOT NULL,
                target TEXT NOT NULL,
                execution_channel TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL,
                attempt_count INTEGER NOT NULL DEFAULT 0,
                max_attempts INTEGER NOT NULL DEFAULT 3,
                next_attempt_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS automation_events (
                event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (request_id)
                    REFERENCES automation_requests(request_id)
                    ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_automation_events_request_id
                ON automation_events(request_id);
            """
        )

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(automation_requests)").fetchall()
        }
        migrations = {
            "idempotency_key": "ALTER TABLE automation_requests ADD COLUMN idempotency_key TEXT",
            "attempt_count": "ALTER TABLE automation_requests ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0",
            "max_attempts": "ALTER TABLE automation_requests ADD COLUMN max_attempts INTEGER NOT NULL DEFAULT 3",
            "next_attempt_at": "ALTER TABLE automation_requests ADD COLUMN next_attempt_at TEXT",
        }
        for column, statement in migrations.items():
            if column not in columns:
                connection.execute(statement)

        connection.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_automation_requests_idempotency_key "
            "ON automation_requests(idempotency_key) WHERE idempotency_key IS NOT NULL"
        )
        connection.execute(
            "CREATE INDEX IF NOT EXISTS idx_automation_requests_status_next_attempt "
            "ON automation_requests(status, next_attempt_at)"
        )
