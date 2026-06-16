"""Backup and restore request/response schemas."""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field


class BackupTaskCreateRequest(BaseModel):
    """
    Request payload for creating or updating a backup task.

    Attributes:
        name: Task display name.
        source_path: Allowed filesystem path to archive.
        zip_password: AES ZIP password.
        schedule_type: interval or weekly.
        interval_minutes: Interval length for interval schedules.
        weekday_mask: Comma-separated weekday numbers for weekly schedules.
        run_time: Daily trigger time for weekly schedules.
        enabled: Whether the task is active.
        bucket_ids: Target bucket IDs for upload.
    """

    name: str = Field(min_length=1, max_length=255)
    source_path: str = Field(min_length=1)
    zip_password: str = Field(min_length=1, max_length=255)
    schedule_type: str = Field(min_length=1, max_length=32)
    interval_minutes: int | None = Field(default=None, ge=1)
    weekday_mask: str | None = None
    run_time: time | None = None
    enabled: bool = True
    bucket_ids: list[int] = Field(min_length=1)


class BackupTaskResponse(BaseModel):
    """
    Backup task summary for listing and detail views.

    Attributes:
        id: Task primary key.
        name: Task display name.
        source_path: Protected source path.
        schedule_type: interval or weekly.
        interval_minutes: Interval length when relevant.
        weekday_mask: Weekly days when relevant.
        run_time: Weekly trigger time when relevant.
        enabled: Whether the task is active.
        bucket_ids: Linked target bucket IDs.
        created_at: Creation time.
        updated_at: Last update time.
    """

    id: int
    name: str
    source_path: str
    schedule_type: str
    interval_minutes: int | None
    weekday_mask: str | None
    run_time: time | None
    enabled: bool
    bucket_ids: list[int]
    created_at: datetime
    updated_at: datetime


class ArtifactReplicaResponse(BaseModel):
    """
    Stored replica summary under a logical backup artifact.

    Attributes:
        id: Replica primary key.
        bucket_id: Target bucket ID.
        object_key: COS object key.
        upload_status: Upload state.
        is_private_route_verified: Latest private-route result.
        last_verified_at: Verification time.
        error_message: Failure message when present.
    """

    id: int
    bucket_id: int
    object_key: str
    upload_status: str
    is_private_route_verified: bool | None
    last_verified_at: datetime | None
    error_message: str | None

    model_config = ConfigDict(from_attributes=True)


class BackupArtifactResponse(BaseModel):
    """
    Logical backup artifact shown in the admin UI.

    Attributes:
        id: Artifact primary key.
        task_id: Source task ID.
        artifact_key: Unique logical identifier.
        source_path: Original source path.
        archive_name: Uploaded ZIP filename.
        size_bytes: Archive size.
        sha256: Archive checksum.
        status: Artifact lifecycle state.
        created_at: Artifact creation time.
        replicas: Stored bucket replicas.
    """

    id: int
    task_id: int
    artifact_key: str
    source_path: str
    archive_name: str
    size_bytes: int
    sha256: str
    status: str
    created_at: datetime
    replicas: list[ArtifactReplicaResponse]

    model_config = ConfigDict(from_attributes=True)


class RestoreRequest(BaseModel):
    """
    Request to start a restore for a logical artifact.

    Attributes:
        restore_path: Target restore directory, normally the original path.
    """

    restore_path: str = Field(min_length=1)


class RestoreJobResponse(BaseModel):
    """
    Restore job status shown in the frontend.

    Attributes:
        id: Restore job primary key.
        artifact_id: Logical artifact being restored.
        replica_id: Selected storage replica when decided.
        restore_path: Target restore path.
        status: Restore job state.
        requires_public_confirm: Whether the next step needs operator approval.
        public_confirmed: Whether the operator approved a public download.
        checksum_verified: Whether the downloaded archive checksum passed.
        error_message: Failure detail when present.
        created_at: Creation time.
        updated_at: Last update time.
    """

    id: int
    artifact_id: int
    replica_id: int | None
    restore_path: str
    status: str
    requires_public_confirm: bool
    public_confirmed: bool
    checksum_verified: bool
    error_message: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
