import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import (
    Column,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
)
from sqlalchemy.engine import Connection, Engine

DEFAULT_DB_PATH = "automation.db"
metadata = MetaData()


automation_requests = Table(
    "automation_requests",
    metadata,
    Column("request_id", String, primary_key=True),
    Column("idempotency_key", String, unique=True, nullable=True),
    Column("process", String, nullable=False),
    Column("target", String, nullable=False),
    Column("execution_channel", String, nullable=False),
    Column("payload_json", Text, nullable=False),
    Column("status", String, nullable=False),
    Column("detail", Text, nullable=False),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("max_attempts", Integer, nullable=False, default=3),
    Column("next_attempt_at", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)


automation_events = Table(
    "automation_events",
    metadata,
    Column("event_id", Integer, primary_key=True, autoincrement=True),
    Column(
        "request_id",
        String,
        ForeignKey("automation_requests.request_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("status", String, nullable=False),
    Column("detail", Text, nullable=False),
    Column("created_at", String, nullable=False),
)

Index("idx_automation_events_request_id", automation_events.c.request_id)
Index(
    "idx_automation_requests_status_next_attempt",
    automation_requests.c.status,
    automation_requests.c.next_attempt_at,
)

_engines: dict[str, Engine] = {}


def get_database_url() -> str:
    explicit = os.getenv("AUTOMATION_DATABASE_URL")
    if explicit:
        return explicit
    path = Path(os.getenv("AUTOMATION_DB_PATH", DEFAULT_DB_PATH)).resolve()
    return f"sqlite+pysqlite:///{path}"


def get_engine() -> Engine:
    url = get_database_url()
    engine = _engines.get(url)
    if engine is None:
        kwargs: dict[str, object] = {"pool_pre_ping": True}
        if url.startswith("sqlite"):
            kwargs["connect_args"] = {"timeout": 10, "check_same_thread": False}
        engine = create_engine(url, **kwargs)
        _engines[url] = engine
    return engine


@contextmanager
def transaction(*, immediate: bool = False) -> Iterator[Connection]:
    engine = get_engine()
    connection = engine.connect()
    transaction_handle = None
    try:
        if immediate and engine.dialect.name == "sqlite":
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        else:
            transaction_handle = connection.begin()
        yield connection
        if transaction_handle is not None:
            transaction_handle.commit()
        else:
            connection.commit()
    except Exception:
        if transaction_handle is not None and transaction_handle.is_active:
            transaction_handle.rollback()
        else:
            connection.rollback()
        raise
    finally:
        connection.close()


def init_database() -> None:
    engine = get_engine()
    if engine.dialect.name == "sqlite":
        with engine.connect() as connection:
            connection.exec_driver_sql("PRAGMA foreign_keys = ON")
            connection.exec_driver_sql("PRAGMA journal_mode = WAL")
    metadata.create_all(engine)
