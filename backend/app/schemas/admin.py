"""Administrator profile and security schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class AdminProfileResponse(BaseModel):
    """
    Administrator profile summary for the frontend.

    Attributes:
        username: Decrypted admin username.
        must_rotate_password: Whether the admin is still in bootstrap state.
        totp_enabled: Whether TOTP is currently enabled.
        passkey_enabled: Whether at least one passkey is registered.
        created_at: Account creation time.
        updated_at: Last account update time.
    """

    username: str
    must_rotate_password: bool
    totp_enabled: bool
    passkey_enabled: bool
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BootstrapCompleteRequest(BaseModel):
    """
    First-run hardening request body.

    Attributes:
        username: New administrator username.
        password: New administrator password.
    """

    username: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=255)


class UpdateAdminProfileRequest(BaseModel):
    """
    Request to update the administrator username.

    Attributes:
        username: New admin username.
    """

    username: str = Field(min_length=3, max_length=255)


class UpdatePasswordRequest(BaseModel):
    """
    Request to change the administrator password.

    Attributes:
        current_password: Existing password for verification.
        new_password: Replacement password.
    """

    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=8, max_length=255)


class TotpSetupResponse(BaseModel):
    """
    TOTP enrollment material for the admin UI.

    Attributes:
        setup_token: Short-lived server token for enrollment confirmation.
        secret: Raw Base32 secret for manual entry.
        otpauth_uri: QR-code compatible enrollment URI.
    """

    setup_token: str
    secret: str
    otpauth_uri: str


class TotpConfirmRequest(BaseModel):
    """
    Request to finalize TOTP enrollment.

    Attributes:
        setup_token: Setup token received from the server.
        code: Current authenticator code proving the secret works.
    """

    setup_token: str
    code: str = Field(min_length=6, max_length=8)


class PasskeyListItem(BaseModel):
    """
    Passkey summary item for the administrator center.

    Attributes:
        credential_id: Stable credential identifier.
        friendly_name: User-visible label.
        created_at: Registration time.
        last_used_at: Last successful authentication time.
    """

    credential_id: str
    friendly_name: str
    created_at: datetime
    last_used_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
