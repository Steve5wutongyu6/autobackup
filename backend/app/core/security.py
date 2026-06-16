"""Security helpers for hashing, encryption, JWT, TOTP, and path checks."""

from __future__ import annotations

import base64
from datetime import UTC, datetime, timedelta
import hashlib
import ipaddress
import os
from pathlib import Path
import secrets
from typing import Any

from argon2 import PasswordHasher
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
import jwt
import pyotp

from app.core.config import settings


password_hasher = PasswordHasher()


def _normalized_master_key() -> bytes:
    """
    Normalize the configured master key to 32 bytes for AES-256-GCM.

    Returns:
        32-byte binary key derived from the environment secret.
    """

    digest = hashlib.sha256(settings.app_master_key.encode("utf-8")).digest()
    return digest


def encrypt_text(plain_text: str, aad: str) -> dict[str, str]:
    """
    Encrypt a UTF-8 string with AES-256-GCM.

    Args:
        plain_text: Sensitive string to encrypt.
        aad: Associated data binding the ciphertext to a logical context.

    Returns:
        Mapping containing base64 ciphertext and nonce.
    """

    nonce = os.urandom(12)
    aesgcm = AESGCM(_normalized_master_key())
    cipher_bytes = aesgcm.encrypt(nonce, plain_text.encode("utf-8"), aad.encode("utf-8"))
    return {
        "ciphertext": base64.b64encode(cipher_bytes).decode("utf-8"),
        "nonce": base64.b64encode(nonce).decode("utf-8"),
    }


def decrypt_text(ciphertext: str, nonce: str, aad: str) -> str:
    """
    Decrypt an AES-256-GCM encrypted UTF-8 string.

    Args:
        ciphertext: Base64 encoded ciphertext.
        nonce: Base64 encoded nonce.
        aad: Associated data used during encryption.

    Returns:
        Decrypted plain text.
    """

    aesgcm = AESGCM(_normalized_master_key())
    plain = aesgcm.decrypt(
        base64.b64decode(nonce),
        base64.b64decode(ciphertext),
        aad.encode("utf-8"),
    )
    return plain.decode("utf-8")


def hash_password(raw_password: str) -> str:
    """
    Hash a password with Argon2id.

    Args:
        raw_password: Cleartext password.

    Returns:
        Argon2id hash string.
    """

    return password_hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    """
    Verify a cleartext password against the stored Argon2 hash.

    Args:
        raw_password: User supplied password.
        password_hash: Stored Argon2 hash.

    Returns:
        True when the password is valid, otherwise False.
    """

    try:
        return password_hasher.verify(password_hash, raw_password)
    except Exception:
        return False


def build_jwt_token(subject: str, token_type: str, ttl_minutes: int, extra: dict[str, Any] | None = None) -> str:
    """
    Create a signed JWT token for the current application.

    Args:
        subject: Principal identifier for the token.
        token_type: Logical token purpose such as access, refresh, or challenge.
        ttl_minutes: Token lifetime in minutes.
        extra: Optional extra claims to embed.

    Returns:
        Signed JWT string.
    """

    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=ttl_minutes)).timestamp()),
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def parse_jwt_token(token: str) -> dict[str, Any]:
    """
    Decode and validate an application JWT token.

    Args:
        token: Raw JWT string from the client.

    Returns:
        Decoded JWT payload dictionary.

    Raises:
        jwt.PyJWTError: Raised when the token is invalid or expired.
    """

    return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])


def new_totp_secret() -> str:
    """
    Generate a new TOTP secret for administrator enrollment.

    Returns:
        Base32 secret string compatible with authenticator apps.
    """

    return pyotp.random_base32()


def verify_totp(secret: str, code: str) -> bool:
    """
    Validate a TOTP code against a shared secret.

    Args:
        secret: Base32 TOTP secret.
        code: User supplied 6-digit code.

    Returns:
        True when the code is valid in the current time window.
    """

    return pyotp.TOTP(secret).verify(code, valid_window=1)


def build_totp_uri(secret: str, username: str) -> str:
    """
    Build the otpauth URI for QR-code enrollment.

    Args:
        secret: Base32 TOTP secret.
        username: Display label for the account.

    Returns:
        otpauth URI string.
    """

    return pyotp.TOTP(secret).provisioning_uri(name=username, issuer_name=settings.app_name)


def generate_random_id() -> str:
    """
    Generate a high-entropy URL-safe identifier.

    Returns:
        URL-safe random identifier string.
    """

    return secrets.token_urlsafe(24)


def ensure_allowed_path(target_path: str) -> Path:
    """
    Normalize and verify that a filesystem path stays within allowed roots.

    Args:
        target_path: User requested source or restore path.

    Returns:
        Resolved path when it is allowed.

    Raises:
        ValueError: Raised when the path escapes the configured root list.
    """

    resolved_path = Path(target_path).resolve()
    for allowed_root in settings.backup_roots:
        try:
            resolved_path.relative_to(allowed_root)
            return resolved_path
        except ValueError:
            continue
    raise ValueError(f"Path is outside allowed roots: {target_path}")


def is_private_ip(ip_address: str) -> bool:
    """
    Check whether an IP address belongs to an approved private range.

    Args:
        ip_address: IPv4 or IPv6 textual address.

    Returns:
        True when the address is considered private for COS routing checks.
    """

    parsed_ip = ipaddress.ip_address(ip_address)
    if parsed_ip.version == 4:
        return (
            parsed_ip in ipaddress.ip_network("10.0.0.0/8")
            or parsed_ip in ipaddress.ip_network("172.16.0.0/12")
            or parsed_ip in ipaddress.ip_network("192.168.0.0/16")
            or parsed_ip in ipaddress.ip_network("100.64.0.0/10")
        )
    return parsed_ip.is_private

