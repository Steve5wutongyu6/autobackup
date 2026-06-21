"""Backup task, artifact, and restore routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, require_admin
from app.schemas.backup import BackupArtifactResponse, BackupRunRequestResponse, BackupTaskCreateRequest, BackupTaskResponse
from app.schemas.backup import RestoreJobResponse, RestoreRequest
from app.schemas.common import ApiMessage
from app.services.backup_service import BackupService


router = APIRouter(tags=["backup"])


def _map_task(task) -> BackupTaskResponse:
    """
    Convert a backup task entity into an API response model.

    Args:
        task: ORM backup task entity.

    Returns:
        Serialized backup task response.
    """

    return BackupTaskResponse(
        id=task.id,
        name=task.name,
        source_path=task.source_path,
        schedule_type=task.schedule_type,
        interval_minutes=task.interval_minutes,
        weekday_mask=task.weekday_mask,
        run_time=task.run_time,
        scheduled_at=task.scheduled_at,
        retention_count=task.retention_count,
        enabled=task.enabled,
        bucket_ids=[link.bucket_id for link in task.buckets],
        created_at=task.created_at,
        updated_at=task.updated_at,
    )


def _map_artifact(artifact) -> BackupArtifactResponse:
    """
    Convert a logical artifact entity into an API response model.

    Args:
        artifact: ORM artifact entity.

    Returns:
        Serialized artifact response.
    """

    return BackupArtifactResponse(
        id=artifact.id,
        task_id=artifact.task_id,
        artifact_key=artifact.artifact_key,
        source_path=artifact.source_path,
        archive_name=artifact.archive_name,
        size_bytes=artifact.size_bytes,
        sha256=artifact.sha256,
        status=artifact.status,
        created_at=artifact.created_at,
        replicas=[
            {
                "id": replica.id,
                "bucket_id": replica.bucket_id,
                "object_key": replica.object_key,
                "upload_status": replica.upload_status,
                "is_private_route_verified": replica.is_private_route_verified,
                "last_verified_at": replica.last_verified_at,
                "error_message": replica.error_message,
            }
            for replica in artifact.replicas
        ],
    )


def _map_restore_job(job) -> RestoreJobResponse:
    """
    Convert a restore job entity into an API response model.

    Args:
        job: ORM restore job entity.

    Returns:
        Serialized restore job response.
    """

    return RestoreJobResponse.model_validate(job)


def _map_run_request(run_request) -> BackupRunRequestResponse:
    """
    Convert a backup run request entity into an API response model.

    Args:
        run_request: ORM backup run request entity.

    Returns:
        Serialized backup run request response.
    """

    return BackupRunRequestResponse.model_validate(run_request)


@router.post("/api/backup-tasks", response_model=BackupTaskResponse)
def create_task(
    payload: BackupTaskCreateRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> BackupTaskResponse:
    """
    Create a backup task.

    Args:
        payload: Backup task creation payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Saved backup task response.
    """

    try:
        task = BackupService(session).create_or_update_task(None, payload.model_dump())
        return _map_task(task)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/backup-tasks", response_model=list[BackupTaskResponse])
def list_tasks(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[BackupTaskResponse]:
    """
    List configured backup tasks.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Backup task response list.
    """

    return [_map_task(task) for task in BackupService(session).list_tasks()]


@router.get("/api/backup-tasks/{task_id}", response_model=BackupTaskResponse)
def get_task(task_id: int, _: int = Depends(require_admin), session: Session = Depends(get_db)) -> BackupTaskResponse:
    """
    Get one backup task by ID.

    Args:
        task_id: Backup task primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Backup task response.
    """

    task = BackupService(session).get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Backup task not found")
    return _map_task(task)


@router.put("/api/backup-tasks/{task_id}", response_model=BackupTaskResponse)
def update_task(
    task_id: int,
    payload: BackupTaskCreateRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> BackupTaskResponse:
    """
    Update an existing backup task.

    Args:
        task_id: Backup task primary key.
        payload: Task update payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Updated task response.
    """

    try:
        task = BackupService(session).create_or_update_task(task_id, payload.model_dump())
        return _map_task(task)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/backup-tasks/{task_id}/run", response_model=ApiMessage)
def run_task(task_id: int, _: int = Depends(require_admin), session: Session = Depends(get_db)) -> ApiMessage:
    """
    Queue a backup task for immediate worker-side execution.

    Args:
        task_id: Backup task primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message after the request is queued.
    """

    try:
        BackupService(session).enqueue_task_run(task_id)
        return ApiMessage(message="Backup task queued")
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/artifacts", response_model=list[BackupArtifactResponse])
def list_artifacts(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[BackupArtifactResponse]:
    """
    List logical backup artifacts with replica details.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Artifact response list.
    """

    return [_map_artifact(item) for item in BackupService(session).list_artifacts()]


@router.get("/api/backup-run-requests", response_model=list[BackupRunRequestResponse])
def list_run_requests(_: int = Depends(require_admin), session: Session = Depends(get_db)) -> list[BackupRunRequestResponse]:
    """
    List recent backup run requests with real-time execution progress.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Backup run request response list.
    """

    return [_map_run_request(item) for item in BackupService(session).list_run_requests()]


@router.post("/api/backup-run-requests/{run_request_id}/cancel", response_model=BackupRunRequestResponse)
def cancel_run_request(
    run_request_id: int,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> BackupRunRequestResponse:
    """
    Request safe termination for one queued or running backup job.

    Args:
        run_request_id: Backup run request primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Updated backup run request response.
    """

    try:
        run_request = BackupService(session).cancel_run_request(run_request_id)
        return _map_run_request(run_request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.delete("/api/artifacts/{artifact_id}", response_model=ApiMessage)
def delete_artifact(
    artifact_id: int,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> ApiMessage:
    """
    Delete a logical artifact across all replicas.

    Args:
        artifact_id: Artifact primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Success message.
    """

    try:
        BackupService(session).delete_artifact(artifact_id)
        return ApiMessage(message="Artifact deleted")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/api/artifacts/{artifact_id}/restore", response_model=RestoreJobResponse)
def create_restore(
    artifact_id: int,
    payload: RestoreRequest,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> RestoreJobResponse:
    """
    Create a restore job for a logical artifact.

    Args:
        artifact_id: Artifact primary key.
        payload: Restore target payload.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Restore job response.
    """

    try:
        job = BackupService(session).start_restore(artifact_id, payload.restore_path)
        return _map_restore_job(job)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.post("/api/restore-jobs/{restore_job_id}/confirm-public-download", response_model=RestoreJobResponse)
def confirm_public_restore(
    restore_job_id: int,
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> RestoreJobResponse:
    """
    Approve a restore job that requires public COS egress.

    Args:
        restore_job_id: Restore job primary key.
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Updated restore job response.
    """

    try:
        job = BackupService(session).confirm_public_restore(restore_job_id)
        return _map_restore_job(job)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error


@router.get("/api/restore-jobs", response_model=list[RestoreJobResponse])
def list_restore_jobs(
    _: int = Depends(require_admin),
    session: Session = Depends(get_db),
) -> list[RestoreJobResponse]:
    """
    List restore jobs.

    Args:
        _: Authenticated administrator ID.
        session: Active SQLAlchemy session.

    Returns:
        Restore job response list.
    """

    return [_map_restore_job(item) for item in BackupService(session).list_restore_jobs()]
