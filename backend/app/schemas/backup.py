"""Backup and restore request/response schemas."""

from __future__ import annotations

from datetime import datetime, time

from pydantic import BaseModel, ConfigDict, Field, model_validator


class BackupTaskCreateRequest(BaseModel):
    """
    Request payload for creating or updating a backup task.

    Attributes:
        name: Task display name.
        source_path: Allowed filesystem path to archive.
        zip_password: AES ZIP password.
        schedule_type: interval, weekly, or once.
        interval_minutes: Interval length for interval schedules.
        weekday_mask: Comma-separated weekday names for weekly schedules.
        run_time: Daily trigger time for weekly schedules.
        scheduled_at: Exact execution time for one-time schedules.
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
    scheduled_at: datetime | None = None
    enabled: bool = True
    bucket_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_schedule_fields(self) -> "BackupTaskCreateRequest":
        """
        Validate schedule-specific fields according to the selected schedule type.

        Returns:
            The validated request model itself.

        Raises:
            ValueError: Raised when required fields for the selected schedule are missing.
        """

        if self.schedule_type == "interval":
            if self.interval_minutes is None:
                raise ValueError("固定间隔模式必须填写间隔分钟")
            self.weekday_mask = None
            self.run_time = None
            self.scheduled_at = None
        elif self.schedule_type == "weekly":
            if not self.weekday_mask:
                raise ValueError("固定星期模式必须选择星期几")
            if self.run_time is None:
                raise ValueError("固定星期模式必须填写执行时间")
            self.interval_minutes = None
            self.scheduled_at = None
        elif self.schedule_type == "once":
            if self.scheduled_at is None:
                raise ValueError("单次任务模式必须填写执行日期时间")
            self.interval_minutes = None
            self.weekday_mask = None
            self.run_time = None
        else:
            raise ValueError("不支持的调度类型")
        return self


class BackupTaskResponse(BaseModel):
    """
    Backup task summary for listing and detail views.

    Attributes:
        id: Task primary key.
        name: Task display name.
        source_path: Protected source path.
        schedule_type: interval, weekly, or once.
        interval_minutes: Interval length when relevant.
        weekday_mask: Weekly days when relevant.
        run_time: Weekly trigger time when relevant.
        scheduled_at: One-time execution datetime when relevant.
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
    scheduled_at: datetime | None
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


class BackupRunBucketProgressResponse(BaseModel):
    """
    Upload progress detail for one bucket inside a backup run.

    Attributes:
        id: Bucket progress primary key.
        bucket_id: Target bucket ID.
        bucket_name: Target bucket display name.
        bucket_region: Target bucket region.
        object_key: COS object key when assigned.
        status: Upload lifecycle state.
        total_bytes: Expected upload bytes for this bucket.
        uploaded_bytes: Uploaded bytes already reported by COS SDK.
        progress_percent: Upload percentage for this bucket.
        error_message: Failure detail when present.
        updated_at: Last progress update time.
    """

    id: int
    bucket_id: int
    bucket_name: str
    bucket_region: str
    object_key: str | None
    status: str
    total_bytes: int
    uploaded_bytes: int
    progress_percent: int
    error_message: str | None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BackupRunRequestResponse(BaseModel):
    """
    Real-time execution progress for one backup run request.

    Attributes:
        id: Run request primary key.
        task_id: Source backup task ID.
        trigger_source: manual or scheduler.
        status: Run request lifecycle state.
        current_step: Current execution step code.
        step_message: Human-readable step detail string.
        step_unit: Unit name for step_total and step_completed.
        step_total: Total work units in the current step.
        step_completed: Completed work units in the current step.
        progress_percent: Current step percentage from 0 to 100.
        artifact_id: Created logical artifact ID when available.
        error_message: Failure detail when present.
        started_at: Actual execution start time.
        finished_at: Execution finish time when completed.
        created_at: Queue creation time.
        updated_at: Last progress update time.
        bucket_progresses: Per-bucket upload progress rows.
    """

    id: int
    task_id: int
    trigger_source: str
    status: str
    current_step: str
    step_message: str | None
    step_unit: str | None
    step_total: int
    step_completed: int
    progress_percent: int
    artifact_id: int | None
    error_message: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    bucket_progresses: list[BackupRunBucketProgressResponse]

    model_config = ConfigDict(from_attributes=True)
