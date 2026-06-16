"""FastAPI dependency helpers."""

from __future__ import annotations

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.security import parse_jwt_token
from app.db.base import get_db_session
from app.services.auth_service import AuthService


bearer_scheme = HTTPBearer(auto_error=False)


def get_db(session: Session = Depends(get_db_session)) -> Session:
    """
    Return the request-scoped SQLAlchemy session.

    Args:
        session: Injected database session.

    Returns:
        SQLAlchemy session bound to the current request.
    """

    return session


def require_admin(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: Session = Depends(get_db),
) -> int:
    """
    Validate an access token and return the administrator ID.

    Args:
        credentials: Bearer credentials extracted from the request.
        session: Active SQLAlchemy session used to ensure bootstrap state.

    Returns:
        Administrator primary key from the access token.

    Raises:
        HTTPException: Raised when the request is unauthenticated.
    """

    if not credentials:
        raise HTTPException(status_code=401, detail="Authentication required")

    try:
        payload = parse_jwt_token(credentials.credentials)
    except Exception as error:
        raise HTTPException(status_code=401, detail=f"Invalid token: {error}") from error

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid access token")

    AuthService(session).ensure_bootstrap_admin()
    return int(payload["sub"])

