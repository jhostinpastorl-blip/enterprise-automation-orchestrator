import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

DEFAULT_DB_PATH = "automation.db"


def get_database_path() -> str:
    return os.getenv("AUTOMATION_DB_PATH", DEFAULT_DB_PATH)


def connect() -> sqlite3.Connection:
    connection = sqlite3.connect(get_database_path())
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


@contextmanager
def transaction() -> Iterator[sqlite3.Connection]:
    connection = connect()
    try:
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
                process TEXT NOT NULL,
                target TEXT NOT NULL,
                execution_channel TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL,
                detail TEXT NOT NULL,
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
