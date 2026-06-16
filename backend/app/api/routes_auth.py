"""Authentication API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.schemas.auth import BootstrapStatusResponse, LoginChallengeResponse, LoginRequest
from app.schemas.auth import PasskeyChallengeResponse, PasskeyVerifyRequest, RefreshRequest
from app.schemas.auth import TokenPairResponse, TotpVerifyRequest
from app.services.auth_service import AuthService


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/bootstrap-status", response_model=BootstrapStatusResponse)
def bootstrap_status(session: Session = Depends(get_db)) -> BootstrapStatusResponse:
    """
    Return the current bootstrap state for the administrator account.

    Args:
        session: Active SQLAlchemy session.

    Returns:
        Bootstrap status response.
    """

    initialized, must_bootstrap, enabled_methods = AuthService(session).get_bootstrap_status()
    return BootstrapStatusResponse(
        initialized=initialized,
        must_bootstrap=must_bootstrap,
        enabled_methods=enabled_methods,
    )


@router.post("/login", response_model=LoginChallengeResponse)
def login(payload: LoginRequest, session: Session = Depends(get_db)) -> LoginChallengeResponse:
    """
    Validate password credentials and start the second-factor flow.

    Args:
        payload: Username and password payload.
        session: Active SQLAlchemy session.

    Returns:
        Login challenge response.

    Raises:
        HTTPException: Raised when the login request is invalid.
    """

    try:
        result = AuthService(session).login(payload.username, payload.password)
        return LoginChallengeResponse(**result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/2fa/totp/verify", response_model=TokenPairResponse)
def verify_totp(payload: TotpVerifyRequest, session: Session = Depends(get_db)) -> TokenPairResponse:
    """
    Verify a TOTP code and issue session tokens.

    Args:
        payload: TOTP verification payload.
        session: Active SQLAlchemy session.

    Returns:
        Access and refresh token pair.
    """

    try:
        return TokenPairResponse(**AuthService(session).verify_totp_login(payload.challenge_token, payload.code))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/2fa/passkey/options", response_model=PasskeyChallengeResponse)
def passkey_login_options(payload: dict, session: Session = Depends(get_db)) -> PasskeyChallengeResponse:
    """
    Generate WebAuthn login options after password validation.

    Args:
        payload: Dictionary containing the password-stage challenge token.
        session: Active SQLAlchemy session.

    Returns:
        WebAuthn challenge response.
    """

    challenge_token = str(payload.get("challenge_token", ""))
    try:
        result = AuthService(session).begin_passkey_login(challenge_token)
        return PasskeyChallengeResponse(**result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/2fa/passkey/verify", response_model=TokenPairResponse)
def passkey_verify(payload: PasskeyVerifyRequest, session: Session = Depends(get_db)) -> TokenPairResponse:
    """
    Complete a WebAuthn login and issue session tokens.

    Args:
        payload: Passkey verification payload.
        session: Active SQLAlchemy session.

    Returns:
        Access and refresh token pair.
    """

    try:
        return TokenPairResponse(**AuthService(session).finish_passkey_login(payload.challenge_token, payload.credential))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/refresh", response_model=TokenPairResponse)
def refresh(payload: RefreshRequest, session: Session = Depends(get_db)) -> TokenPairResponse:
    """
    Refresh a session from a valid refresh token.

    Args:
        payload: Refresh token payload.
        session: Active SQLAlchemy session.

    Returns:
        Access and refresh token pair.
    """

    try:
        return TokenPairResponse(**AuthService(session).refresh(payload.refresh_token))
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/bootstrap/finalize", response_model=TokenPairResponse)
def finalize_bootstrap(payload: dict, session: Session = Depends(get_db)) -> TokenPairResponse:
    """
    Exchange a bootstrap-only token for a full access session after first-run setup.

    Args:
        payload: Dictionary containing bootstrap_access_token.
        session: Active SQLAlchemy session.

    Returns:
        Access and refresh token pair.
    """

    try:
        result = AuthService(session).finalize_bootstrap_login(
            str(payload.get("bootstrap_access_token", ""))
        )
        return TokenPairResponse(**result)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
