"""Repositories for administrator account data."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import AdminAccount, TotpSecret, WebAuthnCredential


class AdminRepository:
    """Data access helper for administrator-related tables."""

    def __init__(self, session: Session) -> None:
        """
        Bind the repository to a database session.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session

    def get_admin(self) -> AdminAccount | None:
        """
        Fetch the single administrator account.

        Returns:
            Existing admin account or None when not initialized.
        """

        return self.session.scalar(select(AdminAccount).limit(1))

    def save_admin(self, admin: AdminAccount) -> AdminAccount:
        """
        Persist the administrator account.

        Args:
            admin: Account entity to persist.

        Returns:
            The saved account entity.
        """

        self.session.add(admin)
        self.session.flush()
        self.session.refresh(admin)
        return admin

    def save_totp_secret(self, secret: TotpSecret) -> TotpSecret:
        """
        Persist a TOTP secret record.

        Args:
            secret: TOTP entity to persist.

        Returns:
            The saved TOTP entity.
        """

        self.session.add(secret)
        self.session.flush()
        self.session.refresh(secret)
        return secret

    def list_passkeys(self, admin_id: int) -> list[WebAuthnCredential]:
        """
        List passkeys for the given administrator.

        Args:
            admin_id: Admin primary key.

        Returns:
            Registered passkeys ordered by creation time.
        """

        statement = (
            select(WebAuthnCredential)
            .where(WebAuthnCredential.admin_id == admin_id)
            .order_by(WebAuthnCredential.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def get_passkey(self, credential_id: str) -> WebAuthnCredential | None:
        """
        Fetch a passkey record by credential ID.

        Args:
            credential_id: WebAuthn credential identifier.

        Returns:
            Matching passkey record or None.
        """

        return self.session.scalar(
            select(WebAuthnCredential).where(WebAuthnCredential.credential_id == credential_id)
        )

    def delete_passkey(self, passkey: WebAuthnCredential) -> None:
        """
        Delete a passkey registration.

        Args:
            passkey: Passkey entity to delete.

        Returns:
            None. The row is removed from the current session.
        """

        self.session.delete(passkey)

