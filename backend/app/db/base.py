"""Database engine and session management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""


engine = create_engine(settings.database_url, future=True, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, class_=Session)

BYTE_COUNT_COLUMNS: dict[str, tuple[str, ...]] = {
    "backup_artifact": ("size_bytes",),
    "backup_run_request": ("step_total", "step_completed"),
    "backup_run_bucket_progress": ("total_bytes", "uploaded_bytes"),
    "artifact_replica": ("size_bytes",),
}


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """
    Open a database session with automatic commit and rollback handling.

    Returns:
        Yielded SQLAlchemy session for repository and worker code.

    Raises:
        Exception: Re-raises any database or service error after rollback.
    """

    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_db_session() -> Generator[Session, None, None]:
    """
    FastAPI dependency that provides a request-scoped database session.

    Returns:
        Generator yielding a SQLAlchemy session.
    """

    with session_scope() as session:
        yield session


def ensure_schema_compatibility() -> None:
    """
    Add lightweight compatibility columns required by newer application versions.

    Returns:
        None. Missing columns are created in place when possible.
    """

    inspector = inspect(engine)
    table_names = set(inspector.get_table_names())
    if "backup_task" not in table_names:
        return

    _ensure_backup_task_scheduled_at(inspector, table_names)
    _ensure_backup_task_retention_count(inspector, table_names)
    _ensure_backup_run_request_cancel_requested(inspector, table_names)
    _ensure_large_byte_count_columns(inspector, table_names)


def _ensure_backup_task_scheduled_at(inspector, table_names: set[str]) -> None:
    """
    Add the scheduled_at column for older backup_task tables when missing.

    Args:
        inspector: SQLAlchemy inspector bound to the current engine.
        table_names: Existing table names discovered from the database.

    Returns:
        None. The compatibility column is added in place when missing.
    """

    if "backup_task" not in table_names:
        return

    column_names = {column["name"] for column in inspector.get_columns("backup_task")}
    if "scheduled_at" in column_names:
        return

    column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE backup_task ADD COLUMN scheduled_at {column_type} NULL"))


def _ensure_backup_task_retention_count(inspector, table_names: set[str]) -> None:
    """
    Add the retention_count column for older backup_task tables when missing.

    Args:
        inspector: SQLAlchemy inspector bound to the current engine.
        table_names: Existing table names discovered from the database.

    Returns:
        None. The compatibility column is added in place when missing.
    """

    if "backup_task" not in table_names:
        return

    column_names = {column["name"] for column in inspector.get_columns("backup_task")}
    if "retention_count" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE backup_task ADD COLUMN retention_count INTEGER NULL"))


def _ensure_backup_run_request_cancel_requested(inspector, table_names: set[str]) -> None:
    """
    Add the cancel_requested column for older backup_run_request tables when missing.

    Args:
        inspector: SQLAlchemy inspector bound to the current engine.
        table_names: Existing table names discovered from the database.

    Returns:
        None. The compatibility column is added in place when missing.
    """

    if "backup_run_request" not in table_names:
        return

    column_names = {column["name"] for column in inspector.get_columns("backup_run_request")}
    if "cancel_requested" in column_names:
        return

    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE backup_run_request ADD COLUMN cancel_requested BOOLEAN NOT NULL DEFAULT FALSE"))


def _ensure_large_byte_count_columns(inspector, table_names: set[str]) -> None:
    """
    Upgrade byte-count columns to BIGINT on PostgreSQL databases.

    Args:
        inspector: SQLAlchemy inspector bound to the current engine.
        table_names: Existing table names discovered from the database.

    Returns:
        None. PostgreSQL columns are widened in place when still using INTEGER.
    """

    if engine.dialect.name != "postgresql":
        return

    for table_name, column_names in BYTE_COUNT_COLUMNS.items():
        if table_name not in table_names:
            continue
        _upgrade_postgresql_integer_columns(inspector, table_name, column_names)


def _upgrade_postgresql_integer_columns(inspector, table_name: str, column_names: tuple[str, ...]) -> None:
    """
    Alter PostgreSQL integer columns to BIGINT when old schemas still use INTEGER.

    Args:
        inspector: SQLAlchemy inspector bound to the current engine.
        table_name: Target table name.
        column_names: Column names that must be safe for large byte counts.

    Returns:
        None. Matching columns are altered in place when needed.
    """

    existing_columns = {column["name"] for column in inspector.get_columns(table_name)}
    target_columns = [column_name for column_name in column_names if column_name in existing_columns]
    if not target_columns:
        return

    with engine.begin() as connection:
        for column_name in target_columns:
            data_type = connection.execute(
                text(
                    """
                    SELECT data_type
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = :table_name
                      AND column_name = :column_name
                    """
                ),
                {"table_name": table_name, "column_name": column_name},
            ).scalar_one_or_none()
            if data_type != "integer":
                continue
            connection.execute(text(f"ALTER TABLE {table_name} ALTER COLUMN {column_name} TYPE BIGINT"))
