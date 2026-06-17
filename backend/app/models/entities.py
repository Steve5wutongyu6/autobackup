"""ORM entities for the AutoBackup application."""

from __future__ import annotations

from datetime import UTC, datetime, time
from enum import StrEnum

from sqlalchemy import BIGINT, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, Text, Time
from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utc_now() -> datetime:
    """
    Build a UTC timestamp for ORM defaults.

    Returns:
        Current timezone-aware UTC datetime.
    """

    return datetime.now(UTC)


class ScheduleType(StrEnum):
    """Supported scheduler types for backup tasks."""

    INTERVAL = "interval"
    WEEKLY = "weekly"
    ONCE = "once"


class ReplicaStatus(StrEnum):
    """Upload and storage status for a bucket replica."""

    PENDING = "pending"
    AVAILABLE = "available"
    FAILED = "failed"
    DELETED = "deleted"


class JobStatus(StrEnum):
    """Execution status for backup and restore jobs."""

    PENDING = "pending"
    RUNNING = "running"
    WAITING_CONFIRMATION = "waiting_confirmation"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELED = "canceled"


class AdminAccount(Base):
    """Single administrator account state."""

    __tablename__ = "admin_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    username_ciphertext: Mapped[str] = mapped_column(Text)
    username_nonce: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(512))
    must_rotate_password: Mapped[bool] = mapped_column(Boolean, default=True)
    totp_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    passkey_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    totp_secret: Mapped["TotpSecret | None"] = relationship(back_populates="admin", uselist=False)
    passkeys: Mapped[list["WebAuthnCredential"]] = relationship(back_populates="admin")


class TotpSecret(Base):
    """Encrypted TOTP enrollment record."""

    __tablename__ = "totp_secret"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_account.id"), unique=True)
    secret_ciphertext: Mapped[str] = mapped_column(Text)
    secret_nonce: Mapped[str] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    admin: Mapped["AdminAccount"] = relationship(back_populates="totp_secret")


class WebAuthnCredential(Base):
    """Registered passkey credential for the single administrator."""

    __tablename__ = "webauthn_credential"

    id: Mapped[int] = mapped_column(primary_key=True)
    admin_id: Mapped[int] = mapped_column(ForeignKey("admin_account.id"))
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)
    public_key: Mapped[bytes] = mapped_column(LargeBinary)
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    aaguid: Mapped[str] = mapped_column(String(64), default="")
    friendly_name: Mapped[str] = mapped_column(String(255))
    transports: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    admin: Mapped["AdminAccount"] = relationship(back_populates="passkeys")


class CosCredential(Base):
    """Encrypted Tencent COS access credential."""

    __tablename__ = "cos_credential"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    secret_id_ciphertext: Mapped[str] = mapped_column(Text)
    secret_id_nonce: Mapped[str] = mapped_column(String(128))
    secret_key_ciphertext: Mapped[str] = mapped_column(Text)
    secret_key_nonce: Mapped[str] = mapped_column(String(128))
    session_token_ciphertext: Mapped[str | None] = mapped_column(Text, nullable=True)
    session_token_nonce: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    buckets: Mapped[list["CosBucket"]] = relationship(back_populates="credential")


class CosBucket(Base):
    """Configured Tencent COS bucket metadata and connectivity state."""

    __tablename__ = "cos_bucket"

    id: Mapped[int] = mapped_column(primary_key=True)
    credential_id: Mapped[int] = mapped_column(ForeignKey("cos_credential.id"))
    name: Mapped[str] = mapped_column(String(255))
    app_id: Mapped[str] = mapped_column(String(64))
    region: Mapped[str] = mapped_column(String(64))
    endpoint_mode: Mapped[str] = mapped_column(String(64), default="default")
    custom_endpoint: Mapped[str | None] = mapped_column(String(255), nullable=True)
    use_https: Mapped[bool] = mapped_column(Boolean, default=True)
    user_expected_private_route: Mapped[bool] = mapped_column(Boolean, default=False)
    last_nslookup_ip: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_nslookup_private: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_connectivity_check_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default="unknown")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    credential: Mapped["CosCredential"] = relationship(back_populates="buckets")
    task_links: Mapped[list["BackupTaskBucket"]] = relationship(back_populates="bucket")
    replicas: Mapped[list["ArtifactReplica"]] = relationship(back_populates="bucket")

    __table_args__ = (UniqueConstraint("name", "app_id", "region", name="uq_bucket_identity"),)


class BackupTask(Base):
    """Configured backup task definition."""

    __tablename__ = "backup_task"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    source_path: Mapped[str] = mapped_column(Text)
    zip_password_ciphertext: Mapped[str] = mapped_column(Text)
    zip_password_nonce: Mapped[str] = mapped_column(String(128))
    schedule_type: Mapped[str] = mapped_column(String(32))
    interval_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    weekday_mask: Mapped[str | None] = mapped_column(String(32), nullable=True)
    run_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    buckets: Mapped[list["BackupTaskBucket"]] = relationship(back_populates="task")
    artifacts: Mapped[list["BackupArtifact"]] = relationship(back_populates="task")


class BackupTaskBucket(Base):
    """Join table mapping backup tasks to target buckets."""

    __tablename__ = "backup_task_bucket"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("backup_task.id"))
    bucket_id: Mapped[int] = mapped_column(ForeignKey("cos_bucket.id"))

    task: Mapped["BackupTask"] = relationship(back_populates="buckets")
    bucket: Mapped["CosBucket"] = relationship(back_populates="task_links")

    __table_args__ = (UniqueConstraint("task_id", "bucket_id", name="uq_task_bucket"),)


class BackupArtifact(Base):
    """Logical backup created from one task execution."""

    __tablename__ = "backup_artifact"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("backup_task.id"))
    artifact_key: Mapped[str] = mapped_column(String(255), unique=True)
    source_path: Mapped[str] = mapped_column(Text)
    archive_name: Mapped[str] = mapped_column(String(255))
    size_bytes: Mapped[int] = mapped_column(BIGINT)
    sha256: Mapped[str] = mapped_column(String(128))
    zip_encrypted: Mapped[bool] = mapped_column(Boolean, default=True)
    status: Mapped[str] = mapped_column(String(64), default=JobStatus.PENDING.value)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    task: Mapped["BackupTask"] = relationship(back_populates="artifacts")
    replicas: Mapped[list["ArtifactReplica"]] = relationship(back_populates="artifact")
    restore_jobs: Mapped[list["RestoreJob"]] = relationship(back_populates="artifact")


class BackupRunRequest(Base):
    """Queued manual backup execution request consumed by the worker."""

    __tablename__ = "backup_run_request"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("backup_task.id"))
    trigger_source: Mapped[str] = mapped_column(String(64), default="manual")
    status: Mapped[str] = mapped_column(String(64), default=JobStatus.PENDING.value)
    current_step: Mapped[str] = mapped_column(String(64), default="queued")
    step_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    step_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    step_total: Mapped[int] = mapped_column(BIGINT, default=0)
    step_completed: Mapped[int] = mapped_column(BIGINT, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    artifact_id: Mapped[int | None] = mapped_column(ForeignKey("backup_artifact.id"), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    bucket_progresses: Mapped[list["BackupRunBucketProgress"]] = relationship(back_populates="run_request")


class BackupRunBucketProgress(Base):
    """Upload progress snapshot for one bucket inside a backup run request."""

    __tablename__ = "backup_run_bucket_progress"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_request_id: Mapped[int] = mapped_column(ForeignKey("backup_run_request.id"))
    bucket_id: Mapped[int] = mapped_column(ForeignKey("cos_bucket.id"))
    bucket_name: Mapped[str] = mapped_column(String(255))
    bucket_region: Mapped[str] = mapped_column(String(64))
    object_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(64), default=JobStatus.PENDING.value)
    total_bytes: Mapped[int] = mapped_column(BIGINT, default=0)
    uploaded_bytes: Mapped[int] = mapped_column(BIGINT, default=0)
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    run_request: Mapped["BackupRunRequest"] = relationship(back_populates="bucket_progresses")


class ArtifactReplica(Base):
    """Stored copy of a logical backup in a specific bucket."""

    __tablename__ = "artifact_replica"

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("backup_artifact.id"))
    bucket_id: Mapped[int] = mapped_column(ForeignKey("cos_bucket.id"))
    object_key: Mapped[str] = mapped_column(String(255))
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BIGINT, nullable=True)
    upload_status: Mapped[str] = mapped_column(String(64), default=ReplicaStatus.PENDING.value)
    is_private_route_verified: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    artifact: Mapped["BackupArtifact"] = relationship(back_populates="replicas")
    bucket: Mapped["CosBucket"] = relationship(back_populates="replicas")


class RestoreJob(Base):
    """Restore request lifecycle and public-download confirmation state."""

    __tablename__ = "restore_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    artifact_id: Mapped[int] = mapped_column(ForeignKey("backup_artifact.id"))
    replica_id: Mapped[int | None] = mapped_column(ForeignKey("artifact_replica.id"), nullable=True)
    restore_path: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(64), default=JobStatus.PENDING.value)
    requires_public_confirm: Mapped[bool] = mapped_column(Boolean, default=False)
    public_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    checksum_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    artifact: Mapped["BackupArtifact"] = relationship(back_populates="restore_jobs")


class AuditLog(Base):
    """Structured audit trail for security and operations."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    action: Mapped[str] = mapped_column(String(128))
    actor: Mapped[str] = mapped_column(String(255))
    target_type: Mapped[str] = mapped_column(String(128))
    target_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    outcome: Mapped[str] = mapped_column(String(64))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AppLog(Base):
    """Queryable operational log index for the admin UI."""

    __tablename__ = "app_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    level: Mapped[str] = mapped_column(String(32))
    module: Mapped[str] = mapped_column(String(255))
    message: Mapped[str] = mapped_column(Text)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
