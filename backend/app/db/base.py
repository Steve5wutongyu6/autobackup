"""Database engine and session management."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
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

