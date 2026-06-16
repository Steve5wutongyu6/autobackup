"""Audit and application log routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.schemas.logs import AppLogResponse, AuditLogResponse
from app.services.log_service import LogService


router = APIRouter(prefix="/api/logs", tags=["logs"])


@router.get("/audit", response_model=list[AuditLogResponse])
def audit_logs(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[AuditLogResponse]:
    """
    List audit logs for the admin UI.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Audit log list.
    """

    return [AuditLogResponse.model_validate(item) for item in LogService(session).list_audit_logs()]


@router.get("/system", response_model=list[AppLogResponse])
def app_logs(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[AppLogResponse]:
    """
    List searchable application logs for the admin UI.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Application log list.
    """

    return [AppLogResponse.model_validate(item) for item in LogService(session).list_app_logs()]

