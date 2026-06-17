"""Repositories for backup tasks, artifacts, replicas, and restore jobs."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import ArtifactReplica, BackupArtifact, BackupRunBucketProgress, BackupRunRequest, BackupTask
from app.models.entities import BackupTaskBucket, RestoreJob
from app.models.entities import JobStatus


class BackupRepository:
    """Data access helper for backup and restore state."""

    def __init__(self, session: Session) -> None:
        """
        Bind the repository to a database session.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session

    def save_task(self, task: BackupTask) -> BackupTask:
        """
        Persist a backup task.

        Args:
            task: Task entity to persist.

        Returns:
            Saved task entity.
        """

        self.session.add(task)
        self.session.flush()
        self.session.refresh(task)
        return task

    def list_tasks(self) -> list[BackupTask]:
        """
        List tasks with bucket links eagerly loaded.

        Returns:
            Task entities ordered by creation time.
        """

        statement = (
            select(BackupTask)
            .options(selectinload(BackupTask.buckets))
            .order_by(BackupTask.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def get_task(self, task_id: int) -> BackupTask | None:
        """
        Fetch a backup task with bucket links.

        Args:
            task_id: Task primary key.

        Returns:
            Matching task entity or None.
        """

        statement = (
            select(BackupTask)
            .options(selectinload(BackupTask.buckets))
            .where(BackupTask.id == task_id)
        )
        return self.session.scalar(statement)

    def replace_task_buckets(self, task_id: int, bucket_ids: list[int]) -> None:
        """
        Replace bucket links for a task.

        Args:
            task_id: Task primary key.
            bucket_ids: New bucket IDs to link.

        Returns:
            None. Existing links are deleted and replaced.
        """

        self.session.execute(delete(BackupTaskBucket).where(BackupTaskBucket.task_id == task_id))
        for bucket_id in bucket_ids:
            self.session.add(BackupTaskBucket(task_id=task_id, bucket_id=bucket_id))
        self.session.flush()

    def save_artifact(self, artifact: BackupArtifact) -> BackupArtifact:
        """
        Persist a logical backup artifact.

        Args:
            artifact: Artifact entity to persist.

        Returns:
            Saved artifact entity.
        """

        self.session.add(artifact)
        self.session.flush()
        self.session.refresh(artifact)
        return artifact

    def save_run_request(self, run_request: BackupRunRequest) -> BackupRunRequest:
        """
        Persist a manual backup run request.

        Args:
            run_request: Run request entity to persist.

        Returns:
            Saved run request entity.
        """

        self.session.add(run_request)
        self.session.flush()
        self.session.refresh(run_request)
        return run_request

    def save_bucket_progress(self, bucket_progress: BackupRunBucketProgress) -> BackupRunBucketProgress:
        """
        Persist one bucket upload progress row.

        Args:
            bucket_progress: Bucket progress entity to persist.

        Returns:
            Saved bucket progress entity.
        """

        self.session.add(bucket_progress)
        self.session.flush()
        self.session.refresh(bucket_progress)
        return bucket_progress

    def save_replica(self, replica: ArtifactReplica) -> ArtifactReplica:
        """
        Persist an artifact replica.

        Args:
            replica: Replica entity to persist.

        Returns:
            Saved replica entity.
        """

        self.session.add(replica)
        self.session.flush()
        self.session.refresh(replica)
        return replica

    def list_artifacts(self) -> list[BackupArtifact]:
        """
        List logical artifacts with replicas eagerly loaded.

        Returns:
            Artifact entities ordered by creation time.
        """

        statement = (
            select(BackupArtifact)
            .options(selectinload(BackupArtifact.replicas))
            .order_by(BackupArtifact.created_at.desc())
        )
        return list(self.session.scalars(statement))

    def get_artifact(self, artifact_id: int) -> BackupArtifact | None:
        """
        Fetch one logical artifact with replicas.

        Args:
            artifact_id: Artifact primary key.

        Returns:
            Matching artifact or None.
        """

        statement = (
            select(BackupArtifact)
            .options(selectinload(BackupArtifact.replicas))
            .where(BackupArtifact.id == artifact_id)
        )
        return self.session.scalar(statement)

    def delete_artifact(self, artifact: BackupArtifact) -> None:
        """
        Delete a logical artifact row.

        Args:
            artifact: Artifact entity to delete.

        Returns:
            None. The row is removed from the current session.
        """

        self.session.delete(artifact)

    def get_run_request(self, run_request_id: int) -> BackupRunRequest | None:
        """
        Fetch one manual backup run request by primary key.

        Args:
            run_request_id: Run request primary key.

        Returns:
            Matching run request entity or None.
        """

        statement = (
            select(BackupRunRequest)
            .options(selectinload(BackupRunRequest.bucket_progresses))
            .where(BackupRunRequest.id == run_request_id)
        )
        return self.session.scalar(statement)

    def list_pending_run_requests(self) -> list[BackupRunRequest]:
        """
        List manual backup run requests ready for worker execution.

        Returns:
            Pending run request entities ordered by creation time.
        """

        statement = (
            select(BackupRunRequest)
            .where(BackupRunRequest.status == JobStatus.PENDING.value)
            .order_by(BackupRunRequest.created_at.asc())
        )
        return list(self.session.scalars(statement))

    def list_recent_run_requests(self, limit: int = 20) -> list[BackupRunRequest]:
        """
        List recent backup run requests with bucket progress details.

        Args:
            limit: Maximum number of run requests to return.

        Returns:
            Recent run request entities ordered by newest first.
        """

        statement = (
            select(BackupRunRequest)
            .options(selectinload(BackupRunRequest.bucket_progresses))
            .order_by(BackupRunRequest.created_at.desc())
            .limit(limit)
        )
        return list(self.session.scalars(statement))

    def save_restore_job(self, restore_job: RestoreJob) -> RestoreJob:
        """
        Persist a restore job entity.

        Args:
            restore_job: Restore job entity.

        Returns:
            Saved restore job entity.
        """

        self.session.add(restore_job)
        self.session.flush()
        self.session.refresh(restore_job)
        return restore_job

    def get_restore_job(self, restore_job_id: int) -> RestoreJob | None:
        """
        Fetch a restore job by primary key.

        Args:
            restore_job_id: Restore job primary key.

        Returns:
            Matching restore job or None.
        """

        return self.session.get(RestoreJob, restore_job_id)

    def list_restore_jobs(self) -> list[RestoreJob]:
        """
        List restore jobs ordered by most recent first.

        Returns:
            Restore job entities.
        """

        statement = select(RestoreJob).order_by(RestoreJob.created_at.desc())
        return list(self.session.scalars(statement))

    def list_pending_restore_jobs(self) -> list[RestoreJob]:
        """
        List restore jobs ready for worker execution.

        Returns:
            Pending restore job entities that no longer require confirmation.
        """

        statement = (
            select(RestoreJob)
            .where(
                RestoreJob.status == JobStatus.PENDING.value,
                RestoreJob.requires_public_confirm.is_(False),
            )
            .order_by(RestoreJob.created_at.asc())
        )
        return list(self.session.scalars(statement))
