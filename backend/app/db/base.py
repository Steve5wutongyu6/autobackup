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

    column_names = {column["name"] for column in inspector.get_columns("backup_task")}
    if "scheduled_at" in column_names:
        return

    column_type = "TIMESTAMP WITH TIME ZONE" if engine.dialect.name == "postgresql" else "DATETIME"
    with engine.begin() as connection:
        connection.execute(text(f"ALTER TABLE backup_task ADD COLUMN scheduled_at {column_type} NULL"))
