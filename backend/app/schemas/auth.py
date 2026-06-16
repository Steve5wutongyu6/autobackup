"""Authentication-related request and response schemas."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """
    Username/password login request body.

    Attributes:
        username: Admin username.
        password: Admin password.
    """

    username: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class LoginChallengeResponse(BaseModel):
    """
    Response after password validation but before 2FA completion.

    Attributes:
        challenge_token: Short-lived token binding the second-factor flow.
        methods: Enabled second-factor methods for the admin account.
        must_bootstrap: Whether the admin must complete first-run hardening.
        bootstrap_access_token: Temporary token only used during first-run bootstrap.
    """

    challenge_token: str
    methods: list[str]
    must_bootstrap: bool
    bootstrap_access_token: str | None = None


class TotpVerifyRequest(BaseModel):
    """
    Request payload for TOTP challenge verification.

    Attributes:
        challenge_token: Short-lived login challenge token.
        code: Six-digit TOTP code.
    """

    challenge_token: str
    code: str = Field(min_length=6, max_length=8)


class TokenPairResponse(BaseModel):
    """
    Final session token response returned after successful login.

    Attributes:
        access_token: Short-lived bearer token for API requests.
        refresh_token: Longer-lived token used to renew the session.
        token_type: OAuth-style token type string.
    """

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """
    Request to refresh a session using a refresh token.

    Attributes:
        refresh_token: Existing refresh token.
    """

    refresh_token: str


class PasskeyChallengeResponse(BaseModel):
    """
    WebAuthn login or registration challenge bundle.

    Attributes:
        challenge_token: Server-side ticket for the flow.
        public_key: Browser-consumable WebAuthn options JSON.
    """

    challenge_token: str
    public_key: dict


class PasskeyVerifyRequest(BaseModel):
    """
    Request payload for verifying a WebAuthn assertion or registration.

    Attributes:
        challenge_token: Short-lived token or internal flow key.
        credential: Raw browser WebAuthn response object.
    """

    challenge_token: str
    credential: dict


class BootstrapStatusResponse(BaseModel):
    """
    Current first-run bootstrap state for the app.

    Attributes:
        initialized: Whether an admin account already exists in the database.
        must_bootstrap: Whether the administrator must rotate credentials and add 2FA.
        enabled_methods: Enabled second-factor methods for the account.
    """

    initialized: bool
    must_bootstrap: bool
    enabled_methods: list[str]

    model_config = ConfigDict(from_attributes=True)
