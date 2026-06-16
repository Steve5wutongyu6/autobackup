"""Repositories for audit and application log tables."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AppLog, AuditLog


class LogRepository:
    """Data access helper for audit and app logs."""

    def __init__(self, session: Session) -> None:
        """
        Bind the repository to a database session.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session

    def write_audit(self, log: AuditLog) -> AuditLog:
        """
        Persist an audit log entry.

        Args:
            log: Audit log entity.

        Returns:
            Saved audit log entity.
        """

        self.session.add(log)
        self.session.flush()
        self.session.refresh(log)
        return log

    def write_app_log(self, log: AppLog) -> AppLog:
        """
        Persist an application log entry.

        Args:
            log: Application log entity.

        Returns:
            Saved app log entity.
        """

        self.session.add(log)
        self.session.flush()
        self.session.refresh(log)
        return log

    def list_audit_logs(self) -> list[AuditLog]:
        """
        List audit log rows ordered by newest first.

        Returns:
            Audit log entities.
        """

        return list(self.session.scalars(select(AuditLog).order_by(AuditLog.created_at.desc())))

    def list_app_logs(self) -> list[AppLog]:
        """
        List application log rows ordered by newest first.

        Returns:
            Application log entities.
        """

        return list(self.session.scalars(select(AppLog).order_by(AppLog.created_at.desc())))

