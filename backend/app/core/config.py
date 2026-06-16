"""Application settings and environment helpers."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


def _split_csv(raw_value: str) -> list[str]:
    """
    Parse a comma-separated environment variable into a trimmed string list.

    Args:
        raw_value: Raw CSV string from the environment.

    Returns:
        List of non-empty trimmed values.
    """

    return [item.strip() for item in raw_value.split(",") if item.strip()]


@dataclass(slots=True)
class Settings:
    """
    Hold application configuration loaded from environment variables.

    Attributes:
        app_name: Public application name used in logs and responses.
        environment: Deployment environment label.
        api_host: Bind host for the API container.
        api_port: Bind port for the API container.
        database_url: PostgreSQL DSN used by API and worker.
        app_master_key: Base64-safe secret used for AES-GCM encryption.
        jwt_secret: Secret used for signing access and refresh tokens.
        session_ttl_minutes: Expiry for access tokens in minutes.
        refresh_ttl_minutes: Expiry for refresh tokens in minutes.
        bootstrap_username: Default admin username for first boot.
        bootstrap_password: Default admin password for first boot.
        cors_origins: Allowed browser origins for the frontend.
        temp_dir: Local temporary archive working directory.
        backup_roots: Allowed source and restore root directories.
        rp_id: WebAuthn relying party ID.
        rp_name: WebAuthn relying party display name.
        log_level: Python logging level.
    """

    app_name: str
    environment: str
    api_host: str
    api_port: int
    database_url: str
    app_master_key: str
    jwt_secret: str
    session_ttl_minutes: int
    refresh_ttl_minutes: int
    bootstrap_username: str
    bootstrap_password: str
    cors_origins: list[str]
    temp_dir: Path
    backup_roots: list[Path]
    rp_id: str
    rp_name: str
    webauthn_expected_origins: list[str]
    log_level: str


def load_settings() -> Settings:
    """
    Load validated runtime settings from environment variables.

    Returns:
        Parsed application settings object.

    Raises:
        ValueError: Raised when required variables are missing or invalid.
    """

    database_url = os.getenv("DATABASE_URL", "").strip()
    app_master_key = os.getenv("APP_MASTER_KEY", "").strip()
    jwt_secret = os.getenv("JWT_SECRET", "").strip()
    bootstrap_username = os.getenv("BOOTSTRAP_ADMIN_USERNAME", "").strip()
    bootstrap_password = os.getenv("BOOTSTRAP_ADMIN_PASSWORD", "").strip()

    if not database_url:
        raise ValueError("DATABASE_URL is required")
    if not app_master_key:
        raise ValueError("APP_MASTER_KEY is required")
    if not jwt_secret:
        raise ValueError("JWT_SECRET is required")
    if not bootstrap_username:
        raise ValueError("BOOTSTRAP_ADMIN_USERNAME is required")
    if not bootstrap_password:
        raise ValueError("BOOTSTRAP_ADMIN_PASSWORD is required")

    raw_roots = os.getenv("BACKUP_ALLOWED_ROOTS", "/data")
    temp_dir = Path(os.getenv("BACKUP_TEMP_DIR", "/tmp/autobackup")).resolve()

    return Settings(
        app_name=os.getenv("APP_NAME", "AutoBackup"),
        environment=os.getenv("APP_ENV", "development"),
        api_host=os.getenv("API_HOST", "0.0.0.0"),
        api_port=int(os.getenv("API_PORT", "8000")),
        database_url=database_url,
        app_master_key=app_master_key,
        jwt_secret=jwt_secret,
        session_ttl_minutes=int(os.getenv("ACCESS_TOKEN_TTL_MINUTES", "30")),
        refresh_ttl_minutes=int(os.getenv("REFRESH_TOKEN_TTL_MINUTES", "10080")),
        bootstrap_username=bootstrap_username,
        bootstrap_password=bootstrap_password,
        cors_origins=_split_csv(os.getenv("CORS_ORIGINS", "http://localhost:5173")),
        temp_dir=temp_dir,
        backup_roots=[Path(item).resolve() for item in _split_csv(raw_roots)],
        rp_id=os.getenv("WEBAUTHN_RP_ID", "localhost"),
        rp_name=os.getenv("WEBAUTHN_RP_NAME", "AutoBackup"),
        webauthn_expected_origins=_split_csv(
            os.getenv(
                "WEBAUTHN_EXPECTED_ORIGINS",
                "http://localhost:8080,http://localhost:5173,http://127.0.0.1:8080,http://127.0.0.1:5173",
            )
        ),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )


settings = load_settings()
