"""Administrator security and profile routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin, require_bootstrap_or_admin
from app.schemas.admin import AdminProfileResponse, BootstrapCompleteRequest, PasskeyListItem
from app.schemas.admin import TotpConfirmRequest, TotpSetupResponse, UpdateAdminProfileRequest
from app.schemas.admin import UpdatePasswordRequest
from app.schemas.common import ApiMessage
from app.services.auth_service import AuthService


router = APIRouter(prefix="/api/admin", tags=["admin"])


@router.post("/bootstrap/complete", response_model=ApiMessage)
def complete_bootstrap(
    payload: BootstrapCompleteRequest,
    _: int = Depends(require_bootstrap_or_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Complete initial admin credential rotation.

    Args:
        payload: New admin credential payload.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    AuthService(session).complete_bootstrap(payload.username, payload.password)
    return ApiMessage(message="Bootstrap completed")


@router.get("/profile", response_model=AdminProfileResponse)
def profile(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> AdminProfileResponse:
    """
    Retrieve the administrator profile.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Administrator profile response.
    """

    return AdminProfileResponse(**AuthService(session).get_admin_profile())


@router.put("/profile", response_model=ApiMessage)
def update_profile(
    payload: UpdateAdminProfileRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Update the administrator username.

    Args:
        payload: Username update payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    AuthService(session).update_username(payload.username)
    return ApiMessage(message="Username updated")


@router.post("/password", response_model=ApiMessage)
def update_password(
    payload: UpdatePasswordRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Update the administrator password.

    Args:
        payload: Password update payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    try:
        AuthService(session).update_password(payload.current_password, payload.new_password)
        return ApiMessage(message="Password updated")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/totp/setup", response_model=TotpSetupResponse)
def totp_setup(
    _: int = Depends(require_bootstrap_or_admin),
    session: Session = Depends(get_db),
) -> TotpSetupResponse:
    """
    Start TOTP enrollment.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Enrollment secret and otpauth URI.
    """

    return TotpSetupResponse(**AuthService(session).begin_totp_setup())


@router.post("/totp/confirm", response_model=ApiMessage)
def totp_confirm(
    payload: TotpConfirmRequest,
    _: int = Depends(require_bootstrap_or_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Finalize TOTP enrollment.

    Args:
        payload: TOTP confirmation payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    try:
        AuthService(session).confirm_totp_setup(payload.setup_token, payload.code)
        return ApiMessage(message="TOTP enabled")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/totp", response_model=ApiMessage)
def totp_delete(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> ApiMessage:
    """
    Disable TOTP for the administrator.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    AuthService(session).disable_totp()
    return ApiMessage(message="TOTP disabled")


@router.post("/passkeys/register/options", response_model=dict)
def passkey_register_options(
    payload: dict,
    _: int = Depends(require_bootstrap_or_admin),
    session: Session = Depends(get_db),
) -> dict:
    """
    Start WebAuthn registration for a new passkey.

    Args:
        payload: Dictionary containing a friendly_name field.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        WebAuthn registration options payload.
    """

    return AuthService(session).begin_passkey_registration(str(payload.get("friendly_name", "Passkey")))


@router.post("/passkeys/register/verify", response_model=ApiMessage)
def passkey_register_verify(
    payload: dict,
    _: int = Depends(require_bootstrap_or_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Persist a registered passkey returned by the browser.

    Args:
        payload: Dictionary containing challenge_token and credential.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    try:
        AuthService(session).finish_passkey_registration(
            str(payload.get("challenge_token", "")),
            dict(payload.get("credential", {})),
        )
        return ApiMessage(message="Passkey registered")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/passkeys", response_model=list[PasskeyListItem])
def passkeys(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[PasskeyListItem]:
    """
    List registered passkeys for the administrator.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Passkey summary list.
    """

    passkeys = AuthService(session).list_passkeys()
    return [
        PasskeyListItem(
            credential_id=item.credential_id,
            friendly_name=item.friendly_name,
            created_at=item.created_at,
            last_used_at=item.last_used_at,
        )
        for item in passkeys
    ]


@router.delete("/passkeys/{credential_id}", response_model=ApiMessage)
def delete_passkey(
    credential_id: str,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Delete a registered passkey.

    Args:
        credential_id: WebAuthn credential ID to delete.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    try:
        AuthService(session).delete_passkey(credential_id)
        return ApiMessage(message="Passkey deleted")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
