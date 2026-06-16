"""Authentication and administrator security service."""

from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy.orm import Session
from webauthn import generate_authentication_options, generate_registration_options
from webauthn import verify_authentication_response, verify_registration_response
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers import bytes_to_base64url
from webauthn.helpers import options_to_json
from webauthn.helpers.structs import AuthenticatorSelectionCriteria
from webauthn.helpers.structs import PublicKeyCredentialDescriptor
from webauthn.helpers.structs import PublicKeyCredentialType
from webauthn.helpers.structs import ResidentKeyRequirement
from webauthn.helpers.structs import UserVerificationRequirement

from app.core.config import settings
from app.core.security import build_jwt_token, build_totp_uri, decrypt_text, encrypt_text
from app.core.security import hash_password, new_totp_secret, parse_jwt_token
from app.core.security import verify_password, verify_totp
from app.models.entities import AdminAccount, TotpSecret, WebAuthnCredential
from app.repositories.admin import AdminRepository
from app.services.log_service import LogService


class AuthService:
    """Encapsulate administrator bootstrap, login, and second-factor flows."""

    def _must_complete_bootstrap(self, admin: AdminAccount) -> bool:
        """
        Decide whether the administrator must stay in the security bootstrap flow.

        Args:
            admin: Current administrator entity.

        Returns:
            True when password rotation or second-factor enrollment is still incomplete.
        """

        return admin.must_rotate_password or not (admin.totp_enabled or admin.passkey_enabled)

    def __init__(self, session: Session) -> None:
        """
        Initialize the authentication service.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session
        self.repository = AdminRepository(session)
        self.log_service = LogService(session)

    def ensure_bootstrap_admin(self) -> AdminAccount:
        """
        Ensure that a single administrator account exists in the database.

        Returns:
            Existing or newly created administrator account.
        """

        admin = self.repository.get_admin()
        if admin:
            return admin

        encrypted_username = encrypt_text(settings.bootstrap_username, "admin_username")
        admin = AdminAccount(
            username_ciphertext=encrypted_username["ciphertext"],
            username_nonce=encrypted_username["nonce"],
            password_hash=hash_password(settings.bootstrap_password),
            must_rotate_password=True,
            totp_enabled=False,
            passkey_enabled=False,
        )
        self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.bootstrap",
            actor="system",
            target_type="admin_account",
            target_id=str(admin.id),
            outcome="success",
            detail="Default administrator initialized from environment variables.",
        )
        return admin

    def get_bootstrap_status(self) -> tuple[bool, bool, list[str]]:
        """
        Read the current bootstrap status for the single admin account.

        Returns:
            Tuple of initialized flag, must-bootstrap flag, and enabled methods.
        """

        admin = self.ensure_bootstrap_admin()
        methods: list[str] = []
        if admin.totp_enabled:
            methods.append("totp")
        if admin.passkey_enabled:
            methods.append("passkey")
        return True, self._must_complete_bootstrap(admin), methods

    def get_admin_profile(self) -> dict[str, object]:
        """
        Return the decrypted administrator profile summary.

        Returns:
            Dictionary containing account profile fields.
        """

        admin = self.ensure_bootstrap_admin()
        username = decrypt_text(admin.username_ciphertext, admin.username_nonce, "admin_username")
        return {
            "username": username,
            "must_rotate_password": self._must_complete_bootstrap(admin),
            "totp_enabled": admin.totp_enabled,
            "passkey_enabled": admin.passkey_enabled,
            "created_at": admin.created_at,
            "updated_at": admin.updated_at,
        }

    def _build_access_pair(self, admin_id: int) -> dict[str, str]:
        """
        Build a fresh access and refresh token pair.

        Args:
            admin_id: Administrator primary key.

        Returns:
            Dictionary containing both JWT tokens.
        """

        return {
            "access_token": build_jwt_token(str(admin_id), "access", settings.session_ttl_minutes),
            "refresh_token": build_jwt_token(str(admin_id), "refresh", settings.refresh_ttl_minutes),
        }

    def _build_bootstrap_access_token(self, admin_id: int) -> str:
        """
        Build a temporary bootstrap-only token for first-run setup flows.

        Args:
            admin_id: Administrator primary key.

        Returns:
            Signed JWT token that only authorizes bootstrap actions.
        """

        return build_jwt_token(str(admin_id), "bootstrap_access", 30)

    def login(self, username: str, password: str) -> dict[str, object]:
        """
        Validate username and password and start the second-factor flow.

        Args:
            username: User supplied administrator username.
            password: User supplied password.

        Returns:
            Challenge token and enabled methods for second-factor completion.

        Raises:
            ValueError: Raised when username or password is invalid.
        """

        admin = self.ensure_bootstrap_admin()
        stored_username = decrypt_text(admin.username_ciphertext, admin.username_nonce, "admin_username")
        if stored_username != username or not verify_password(password, admin.password_hash):
            self.log_service.audit(
                action="auth.login",
                actor=username,
                target_type="admin_account",
                target_id=str(admin.id),
                outcome="failure",
                detail="Invalid username or password.",
            )
            raise ValueError("Invalid username or password")

        methods: list[str] = []
        if admin.totp_enabled:
            methods.append("totp")
        if admin.passkey_enabled:
            methods.append("passkey")

        if not methods:
            methods.append("bootstrap")

        challenge_token = build_jwt_token(
            str(admin.id),
            "login_challenge",
            10,
            {"methods": methods, "must_bootstrap": self._must_complete_bootstrap(admin)},
        )
        self.log_service.audit(
            action="auth.password_ok",
            actor=username,
            target_type="admin_account",
            target_id=str(admin.id),
            outcome="success",
            detail="Password stage completed.",
        )
        login_result = {
            "challenge_token": challenge_token,
            "methods": methods,
            "must_bootstrap": self._must_complete_bootstrap(admin),
        }
        if self._must_complete_bootstrap(admin) and methods == ["bootstrap"]:
            login_result["bootstrap_access_token"] = self._build_bootstrap_access_token(admin.id)
        return login_result

    def verify_totp_login(self, challenge_token: str, code: str) -> dict[str, str]:
        """
        Verify the TOTP factor and issue session tokens.

        Args:
            challenge_token: Login challenge token created after password validation.
            code: User supplied TOTP code.

        Returns:
            Access and refresh token pair.

        Raises:
            ValueError: Raised when the challenge is invalid or TOTP is not valid.
        """

        payload = parse_jwt_token(challenge_token)
        if payload.get("type") != "login_challenge":
            raise ValueError("Invalid challenge token type")

        admin = self.ensure_bootstrap_admin()
        totp_secret = admin.totp_secret
        if not totp_secret or not totp_secret.enabled:
            raise ValueError("TOTP is not configured")

        secret = decrypt_text(totp_secret.secret_ciphertext, totp_secret.secret_nonce, "totp_secret")
        if not verify_totp(secret, code):
            self.log_service.audit(
                action="auth.totp_verify",
                actor=str(admin.id),
                target_type="admin_account",
                target_id=str(admin.id),
                outcome="failure",
                detail="Invalid TOTP code.",
            )
            raise ValueError("Invalid TOTP code")

        totp_secret.last_verified_at = datetime.now(UTC)
        self.repository.save_totp_secret(totp_secret)
        self.log_service.audit(
            action="auth.totp_verify",
            actor=str(admin.id),
            target_type="admin_account",
            target_id=str(admin.id),
            outcome="success",
            detail="TOTP login completed.",
        )
        return self._build_access_pair(admin.id)

    def refresh(self, refresh_token: str) -> dict[str, str]:
        """
        Refresh an active session from a valid refresh token.

        Args:
            refresh_token: Signed refresh token.

        Returns:
            New access and refresh token pair.

        Raises:
            ValueError: Raised when the token type is invalid.
        """

        payload = parse_jwt_token(refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("Invalid refresh token")
        return self._build_access_pair(int(payload["sub"]))

    def finalize_bootstrap_login(self, bootstrap_access_token: str) -> dict[str, str]:
        """
        Exchange a bootstrap-only token for a full access session after setup completes.

        Args:
            bootstrap_access_token: Temporary bootstrap token issued after password validation.

        Returns:
            Full access and refresh token pair.

        Raises:
            ValueError: Raised when the token is invalid or bootstrap is not complete yet.
        """

        payload = parse_jwt_token(bootstrap_access_token)
        if payload.get("type") != "bootstrap_access":
            raise ValueError("Invalid bootstrap token")

        admin = self.ensure_bootstrap_admin()
        if self._must_complete_bootstrap(admin):
            raise ValueError("Bootstrap is not complete")
        return self._build_access_pair(int(payload["sub"]))

    def complete_bootstrap(self, username: str, password: str) -> AdminAccount:
        """
        Replace environment bootstrap credentials with database-managed ones.

        Args:
            username: New administrator username.
            password: New administrator password.

        Returns:
            Updated administrator entity.
        """

        admin = self.ensure_bootstrap_admin()
        encrypted_username = encrypt_text(username, "admin_username")
        admin.username_ciphertext = encrypted_username["ciphertext"]
        admin.username_nonce = encrypted_username["nonce"]
        admin.password_hash = hash_password(password)
        admin.must_rotate_password = False
        saved_admin = self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.bootstrap_complete",
            actor=str(admin.id),
            target_type="admin_account",
            target_id=str(admin.id),
            outcome="success",
            detail="Administrator finished initial credential rotation.",
        )
        return saved_admin

    def update_username(self, username: str) -> AdminAccount:
        """
        Change the administrator username.

        Args:
            username: Replacement username.

        Returns:
            Updated administrator entity.
        """

        admin = self.ensure_bootstrap_admin()
        encrypted_username = encrypt_text(username, "admin_username")
        admin.username_ciphertext = encrypted_username["ciphertext"]
        admin.username_nonce = encrypted_username["nonce"]
        saved_admin = self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.username_update",
            actor=str(admin.id),
            target_type="admin_account",
            target_id=str(admin.id),
            outcome="success",
            detail="Administrator username changed.",
        )
        return saved_admin

    def update_password(self, current_password: str, new_password: str) -> AdminAccount:
        """
        Change the administrator password after verifying the old password.

        Args:
            current_password: Existing password.
            new_password: Replacement password.

        Returns:
            Updated administrator entity.

        Raises:
            ValueError: Raised when the current password is wrong.
        """

        admin = self.ensure_bootstrap_admin()
        if not verify_password(current_password, admin.password_hash):
            raise ValueError("Current password is incorrect")
        admin.password_hash = hash_password(new_password)
        saved_admin = self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.password_update",
            actor=str(admin.id),
            target_type="admin_account",
            target_id=str(admin.id),
            outcome="success",
            detail="Administrator password changed.",
        )
        return saved_admin

    def begin_totp_setup(self) -> dict[str, str]:
        """
        Start TOTP enrollment and return secret material to the frontend.

        Returns:
            Setup token, secret, and otpauth URI.
        """

        admin = self.ensure_bootstrap_admin()
        username = decrypt_text(admin.username_ciphertext, admin.username_nonce, "admin_username")
        secret = new_totp_secret()
        setup_token = build_jwt_token(
            str(admin.id),
            "totp_setup",
            10,
            {"secret": secret},
        )
        return {
            "setup_token": setup_token,
            "secret": secret,
            "otpauth_uri": build_totp_uri(secret, username),
        }

    def confirm_totp_setup(self, setup_token: str, code: str) -> TotpSecret:
        """
        Finalize TOTP enrollment after verifying the generated code.

        Args:
            setup_token: TOTP setup token created by begin_totp_setup.
            code: Current authenticator code proving the secret works.

        Returns:
            Persisted TOTP secret entity.

        Raises:
            ValueError: Raised when the setup token or TOTP code is invalid.
        """

        payload = parse_jwt_token(setup_token)
        if payload.get("type") != "totp_setup":
            raise ValueError("Invalid setup token")
        secret = str(payload["secret"])
        if not verify_totp(secret, code):
            raise ValueError("Invalid TOTP code")

        admin = self.ensure_bootstrap_admin()
        encrypted_secret = encrypt_text(secret, "totp_secret")
        if admin.totp_secret:
            admin.totp_secret.secret_ciphertext = encrypted_secret["ciphertext"]
            admin.totp_secret.secret_nonce = encrypted_secret["nonce"]
            admin.totp_secret.enabled = True
            admin.totp_secret.last_verified_at = datetime.now(UTC)
            saved_secret = self.repository.save_totp_secret(admin.totp_secret)
        else:
            saved_secret = self.repository.save_totp_secret(
                TotpSecret(
                    admin_id=admin.id,
                    secret_ciphertext=encrypted_secret["ciphertext"],
                    secret_nonce=encrypted_secret["nonce"],
                    enabled=True,
                    last_verified_at=datetime.now(UTC),
                )
            )

        admin.totp_enabled = True
        self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.totp_enable",
            actor=str(admin.id),
            target_type="totp_secret",
            target_id=str(saved_secret.id),
            outcome="success",
            detail="TOTP enabled for administrator.",
        )
        return saved_secret

    def disable_totp(self) -> None:
        """
        Disable TOTP for the single administrator.

        Returns:
            None. The existing secret is marked disabled when present.
        """

        admin = self.ensure_bootstrap_admin()
        if admin.totp_secret:
            admin.totp_secret.enabled = False
            self.repository.save_totp_secret(admin.totp_secret)
        admin.totp_enabled = False
        self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.totp_disable",
            actor=str(admin.id),
            target_type="totp_secret",
            target_id=str(admin.totp_secret.id if admin.totp_secret else ""),
            outcome="success",
            detail="TOTP disabled for administrator.",
        )

    def begin_passkey_registration(self, friendly_name: str) -> dict[str, object]:
        """
        Start WebAuthn passkey registration.

        Args:
            friendly_name: User-visible label for the new passkey.

        Returns:
            Browser-ready registration options and a challenge token.
        """

        admin = self.ensure_bootstrap_admin()
        username = decrypt_text(admin.username_ciphertext, admin.username_nonce, "admin_username")
        exclude_credentials = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(credential.credential_id),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            )
            for credential in self.repository.list_passkeys(admin.id)
        ]
        options = generate_registration_options(
            rp_id=settings.rp_id,
            rp_name=settings.rp_name,
            user_name=username,
            user_id=str(admin.id).encode("utf-8"),
            user_display_name=username,
            authenticator_selection=AuthenticatorSelectionCriteria(
                resident_key=ResidentKeyRequirement.PREFERRED,
                user_verification=UserVerificationRequirement.PREFERRED,
            ),
            exclude_credentials=exclude_credentials,
        )
        challenge_token = build_jwt_token(
            str(admin.id),
            "passkey_register",
            10,
            {
                "friendly_name": friendly_name,
                "challenge": bytes_to_base64url(options.challenge),
            },
        )
        return {
            "challenge_token": challenge_token,
            "public_key": json.loads(options_to_json(options)),
        }

    def finish_passkey_registration(self, challenge_token: str, credential: dict) -> WebAuthnCredential:
        """
        Persist a passkey registration received from the browser.

        Args:
            challenge_token: Registration token created by begin_passkey_registration.
            credential: Browser credential response object.

        Returns:
            Stored passkey entity.

        Raises:
            ValueError: Raised when the token or credential payload is invalid.
        """

        payload = parse_jwt_token(challenge_token)
        if payload.get("type") != "passkey_register":
            raise ValueError("Invalid passkey registration token")

        admin = self.ensure_bootstrap_admin()
        verified_registration = verify_registration_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(payload["challenge"])),
            expected_rp_id=settings.rp_id,
            expected_origin=settings.webauthn_expected_origins,
            require_user_verification=False,
        )

        credential_id = bytes_to_base64url(verified_registration.credential_id)
        existing_passkey = self.repository.get_passkey(credential_id)
        if existing_passkey:
            raise ValueError("Passkey already registered")

        passkey = WebAuthnCredential(
            admin_id=admin.id,
            credential_id=credential_id,
            public_key=verified_registration.credential_public_key,
            sign_count=verified_registration.sign_count,
            aaguid=verified_registration.aaguid,
            friendly_name=str(payload.get("friendly_name", "Passkey")),
            transports=",".join(credential.get("response", {}).get("transports", [])),
        )
        self.session.add(passkey)
        self.session.flush()
        self.session.refresh(passkey)
        admin.passkey_enabled = True
        self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.passkey_add",
            actor=str(admin.id),
            target_type="webauthn_credential",
            target_id=passkey.credential_id,
            outcome="success",
            detail="Passkey registered for administrator.",
        )
        return passkey

    def begin_passkey_login(self, challenge_token: str) -> dict[str, object]:
        """
        Start the WebAuthn login step after password validation.

        Args:
            challenge_token: Password-stage login token.

        Returns:
            Browser-ready authentication options and a second challenge token.
        """

        payload = parse_jwt_token(challenge_token)
        if payload.get("type") != "login_challenge":
            raise ValueError("Invalid login challenge token")

        admin = self.ensure_bootstrap_admin()
        credentials = [
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(passkey.credential_id),
                type=PublicKeyCredentialType.PUBLIC_KEY,
            )
            for passkey in self.repository.list_passkeys(admin.id)
        ]
        options = generate_authentication_options(
            rp_id=settings.rp_id,
            allow_credentials=credentials,
            user_verification=UserVerificationRequirement.PREFERRED,
        )
        webauthn_token = build_jwt_token(
            str(admin.id),
            "passkey_login",
            10,
            {"challenge": bytes_to_base64url(options.challenge)},
        )
        return {
            "challenge_token": webauthn_token,
            "public_key": json.loads(options_to_json(options)),
        }

    def finish_passkey_login(self, challenge_token: str, credential: dict) -> dict[str, str]:
        """
        Complete a WebAuthn login and issue session tokens.

        Args:
            challenge_token: WebAuthn login token.
            credential: Browser assertion response object.

        Returns:
            Access and refresh token pair.

        Raises:
            ValueError: Raised when the credential is missing or unknown.
        """

        payload = parse_jwt_token(challenge_token)
        if payload.get("type") != "passkey_login":
            raise ValueError("Invalid passkey login token")

        raw_credential_id = credential.get("id")
        if not raw_credential_id:
            raise ValueError("Missing credential id")

        passkey = self.repository.get_passkey(str(raw_credential_id))
        if not passkey:
            raise ValueError("Unknown passkey credential")

        verified_authentication = verify_authentication_response(
            credential=credential,
            expected_challenge=base64url_to_bytes(str(payload["challenge"])),
            expected_rp_id=settings.rp_id,
            expected_origin=settings.webauthn_expected_origins,
            credential_public_key=passkey.public_key,
            credential_current_sign_count=passkey.sign_count,
            require_user_verification=False,
        )

        passkey.sign_count = verified_authentication.new_sign_count
        passkey.last_used_at = datetime.now(UTC)
        self.session.add(passkey)
        self.session.flush()
        self.log_service.audit(
            action="auth.passkey_verify",
            actor=str(passkey.admin_id),
            target_type="webauthn_credential",
            target_id=passkey.credential_id,
            outcome="success",
            detail="Passkey login completed.",
        )
        return self._build_access_pair(passkey.admin_id)

    def list_passkeys(self) -> list[WebAuthnCredential]:
        """
        List all registered passkeys for the administrator.

        Returns:
            Passkey entities ordered by creation time.
        """

        admin = self.ensure_bootstrap_admin()
        return self.repository.list_passkeys(admin.id)

    def delete_passkey(self, credential_id: str) -> None:
        """
        Delete a passkey credential from the administrator account.

        Args:
            credential_id: Credential ID to delete.

        Returns:
            None. The passkey is removed if it exists.

        Raises:
            ValueError: Raised when the credential does not exist.
        """

        passkey = self.repository.get_passkey(credential_id)
        if not passkey:
            raise ValueError("Passkey not found")

        admin = self.ensure_bootstrap_admin()
        self.repository.delete_passkey(passkey)
        self.session.flush()
        remaining = self.repository.list_passkeys(admin.id)
        admin.passkey_enabled = bool(remaining)
        self.repository.save_admin(admin)
        self.log_service.audit(
            action="admin.passkey_delete",
            actor=str(admin.id),
            target_type="webauthn_credential",
            target_id=credential_id,
            outcome="success",
            detail="Passkey removed from administrator account.",
        )
