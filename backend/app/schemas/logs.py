"""Audit and application log schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogResponse(BaseModel):
    """
    Audit log line exposed to the frontend.

    Attributes:
        id: Audit record primary key.
        action: Logical action name.
        actor: Operator or system actor label.
        target_type: Target entity category.
        target_id: Target identifier when relevant.
        outcome: Success or failure label.
        detail: Optional detail string.
        created_at: Record creation time.
    """

    id: int
    action: str
    actor: str
    target_type: str
    target_id: str | None
    outcome: str
    detail: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AppLogResponse(BaseModel):
    """
    Application log row exposed to the frontend.

    Attributes:
        id: App log primary key.
        level: Log severity.
        module: Emitting module.
        message: Primary log message.
        detail: Optional extended detail.
        created_at: Record creation time.
    """

    id: int
    level: str
    module: str
    message: str
    detail: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
