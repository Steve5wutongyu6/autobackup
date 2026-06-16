"""High-level audit and system log service."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import AppLog, AuditLog
from app.repositories.logs import LogRepository


class LogService:
    """Encapsulate audit and application log writing and listing."""

    def __init__(self, session: Session) -> None:
        """
        Initialize the log service.

        Args:
            session: Active SQLAlchemy session.
        """

        self.repository = LogRepository(session)

    def audit(self, action: str, actor: str, target_type: str, target_id: str | None, outcome: str, detail: str | None = None) -> AuditLog:
        """
        Write an audit record for a security-sensitive or business action.

        Args:
            action: Logical action name.
            actor: Human or system actor.
            target_type: Target entity category.
            target_id: Optional target identifier.
            outcome: Success or failure outcome label.
            detail: Optional detail string.

        Returns:
            Saved audit log record.
        """

        return self.repository.write_audit(
            AuditLog(
                action=action,
                actor=actor,
                target_type=target_type,
                target_id=target_id,
                outcome=outcome,
                detail=detail,
            )
        )

    def app_log(self, level: str, module: str, message: str, detail: str | None = None) -> AppLog:
        """
        Persist a searchable operational log line.

        Args:
            level: Severity level.
            module: Emitting module name.
            message: Primary log message.
            detail: Optional extended detail.

        Returns:
            Saved application log row.
        """

        return self.repository.write_app_log(
            AppLog(level=level, module=module, message=message, detail=detail)
        )

    def list_audit_logs(self) -> list[AuditLog]:
        """
        Retrieve audit log rows for the admin UI.

        Returns:
            Audit log entities ordered by newest first.
        """

        return self.repository.list_audit_logs()

    def list_app_logs(self) -> list[AppLog]:
        """
        Retrieve application log rows for the admin UI.

        Returns:
            Application log entities ordered by newest first.
        """

        return self.repository.list_app_logs()

