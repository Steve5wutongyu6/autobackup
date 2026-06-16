"""Backup creation, upload orchestration, and restore execution service."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from zipfile import ZIP_DEFLATED

import pyzipper
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_text, encrypt_text, ensure_allowed_path, generate_random_id
from app.models.entities import ArtifactReplica, BackupArtifact, BackupTask, JobStatus, ReplicaStatus, RestoreJob
from app.repositories.backup import BackupRepository
from app.repositories.cos import CosRepository
from app.services.cos_service import CosService
from app.services.log_service import LogService


class BackupService:
    """Manage backup task definitions, archive generation, uploads, and restore jobs."""

    def __init__(self, session: Session) -> None:
        """
        Initialize the backup service.

        Args:
            session: Active SQLAlchemy session.
        """

        self.session = session
        self.repository = BackupRepository(session)
        self.cos_repository = CosRepository(session)
        self.cos_service = CosService(session)
        self.log_service = LogService(session)
        settings.temp_dir.mkdir(parents=True, exist_ok=True)

    def create_or_update_task(self, task_id: int | None, payload: dict[str, object]) -> BackupTask:
        """
        Create or update a backup task definition.

        Args:
            task_id: Existing task primary key or None for new tasks.
            payload: Task field dictionary from the API layer.

        Returns:
            Saved backup task entity.

        Raises:
            ValueError: Raised when the source path is outside allowed roots.
        """

        normalized_source_path = str(ensure_allowed_path(str(payload["source_path"])))
        encrypted_password = encrypt_text(str(payload["zip_password"]), f"zip_password:{payload['name']}")
        task = self.repository.get_task(task_id) if task_id else None
        if not task:
            task = BackupTask(
                name=str(payload["name"]),
                source_path=normalized_source_path,
                zip_password_ciphertext=encrypted_password["ciphertext"],
                zip_password_nonce=encrypted_password["nonce"],
                schedule_type=str(payload["schedule_type"]),
            )

        task.name = str(payload["name"])
        task.source_path = normalized_source_path
        task.zip_password_ciphertext = encrypted_password["ciphertext"]
        task.zip_password_nonce = encrypted_password["nonce"]
        task.schedule_type = str(payload["schedule_type"])
        task.interval_minutes = payload.get("interval_minutes")
        task.weekday_mask = payload.get("weekday_mask")
        task.run_time = payload.get("run_time")
        task.enabled = bool(payload["enabled"])

        saved_task = self.repository.save_task(task)
        self.repository.replace_task_buckets(saved_task.id, [int(item) for item in payload["bucket_ids"]])
        self.log_service.audit(
            action="backup.task_save",
            actor="admin",
            target_type="backup_task",
            target_id=str(saved_task.id),
            outcome="success",
            detail=f"Backup task {saved_task.name} saved.",
        )
        return self.repository.get_task(saved_task.id) or saved_task

    def list_tasks(self) -> list[BackupTask]:
        """
        Retrieve all backup tasks.

        Returns:
            Task entities.
        """

        return self.repository.list_tasks()

    def get_task(self, task_id: int) -> BackupTask | None:
        """
        Fetch one backup task by primary key.

        Args:
            task_id: Task primary key.

        Returns:
            Matching task or None.
        """

        return self.repository.get_task(task_id)

    def _build_archive(self, task: BackupTask) -> tuple[Path, str, str]:
        """
        Build an AES ZIP archive and checksum for the task source directory.

        Args:
            task: Backup task entity.

        Returns:
            Tuple of archive path, archive filename, and SHA256 checksum.
        """

        source_path = ensure_allowed_path(task.source_path)
        zip_password = decrypt_text(task.zip_password_ciphertext, task.zip_password_nonce, f"zip_password:{task.name}")
        archive_name = f"{task.name}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.zip"
        archive_path = settings.temp_dir / archive_name
        manifest = {
            "task_id": task.id,
            "task_name": task.name,
            "source_path": str(source_path),
            "created_at": datetime.now(UTC).isoformat(),
        }

        with pyzipper.AESZipFile(archive_path, "w", compression=ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as archive:
            archive.setpassword(zip_password.encode("utf-8"))
            for root, _, files in os.walk(source_path):
                for file_name in files:
                    absolute_path = Path(root) / file_name
                    relative_path = absolute_path.relative_to(source_path.parent)
                    archive.write(absolute_path, arcname=str(relative_path))
            archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

        sha256 = hashlib.sha256(archive_path.read_bytes()).hexdigest()
        return archive_path, archive_name, sha256

    def run_task(self, task_id: int) -> BackupArtifact:
        """
        Execute one backup task immediately, upload results, and clean up the archive.

        Args:
            task_id: Task primary key.

        Returns:
            Persisted logical backup artifact.

        Raises:
            ValueError: Raised when the task does not exist or has no target buckets.
        """

        task = self.repository.get_task(task_id)
        if not task:
            raise ValueError("Backup task not found")
        if not task.buckets:
            raise ValueError("Backup task has no target buckets")

        archive_path, archive_name, sha256 = self._build_archive(task)
        size_bytes = archive_path.stat().st_size
        artifact = self.repository.save_artifact(
            BackupArtifact(
                task_id=task.id,
                artifact_key=generate_random_id(),
                source_path=task.source_path,
                archive_name=archive_name,
                size_bytes=size_bytes,
                sha256=sha256,
                zip_encrypted=True,
                status=JobStatus.RUNNING.value,
            )
        )

        success_count = 0
        for task_bucket in task.buckets:
            bucket = self.cos_repository.get_bucket(task_bucket.bucket_id)
            if not bucket:
                continue
            object_key = f"autobackup/{task.name}/{archive_name}"
            replica = self.repository.save_replica(
                ArtifactReplica(
                    artifact_id=artifact.id,
                    bucket_id=bucket.id,
                    object_key=object_key,
                    upload_status=ReplicaStatus.PENDING.value,
                )
            )
            try:
                upload_result = self.cos_service.upload_file(bucket, object_key, str(archive_path))
                replica.upload_status = ReplicaStatus.AVAILABLE.value
                replica.etag = str(upload_result.get("ETag", ""))
                replica.size_bytes = size_bytes
                success_count += 1
            except Exception as error:
                replica.upload_status = ReplicaStatus.FAILED.value
                replica.error_message = str(error)
            self.session.add(replica)
            self.session.flush()

        artifact.status = JobStatus.SUCCESS.value if success_count > 0 else JobStatus.FAILED.value
        self.session.add(artifact)
        self.session.flush()
        archive_path.unlink(missing_ok=True)
        self.log_service.audit(
            action="backup.task_run",
            actor="worker",
            target_type="backup_task",
            target_id=str(task.id),
            outcome="success" if success_count > 0 else "failure",
            detail=f"Backup archive {archive_name} uploaded to {success_count} buckets.",
        )
        return self.repository.get_artifact(artifact.id) or artifact

    def list_artifacts(self) -> list[BackupArtifact]:
        """
        Return all logical backup artifacts.

        Returns:
            Artifact entities.
        """

        return self.repository.list_artifacts()

    def delete_artifact(self, artifact_id: int) -> None:
        """
        Delete a logical artifact from all buckets and remove its database rows.

        Args:
            artifact_id: Artifact primary key.

        Returns:
            None. Related COS objects and rows are deleted.

        Raises:
            ValueError: Raised when the artifact does not exist.
        """

        artifact = self.repository.get_artifact(artifact_id)
        if not artifact:
            raise ValueError("Artifact not found")

        for replica in artifact.replicas:
            bucket = self.cos_repository.get_bucket(replica.bucket_id)
            if bucket and replica.upload_status == ReplicaStatus.AVAILABLE.value:
                try:
                    self.cos_service.delete_object(bucket, replica.object_key)
                    replica.upload_status = ReplicaStatus.DELETED.value
                except Exception as error:
                    replica.error_message = str(error)
            self.session.add(replica)

        self.repository.delete_artifact(artifact)
        self.log_service.audit(
            action="artifact.delete",
            actor="admin",
            target_type="backup_artifact",
            target_id=str(artifact_id),
            outcome="success",
            detail=f"Artifact {artifact_id} deleted across configured replicas.",
        )

    def start_restore(self, artifact_id: int, restore_path: str) -> RestoreJob:
        """
        Create a restore job and decide whether public-download confirmation is needed.

        Args:
            artifact_id: Logical artifact primary key.
            restore_path: Target restore directory.

        Returns:
            Newly created restore job entity.

        Raises:
            ValueError: Raised when the artifact does not exist or no usable replica is found.
        """

        normalized_restore_path = str(ensure_allowed_path(restore_path))
        artifact = self.repository.get_artifact(artifact_id)
        if not artifact:
            raise ValueError("Artifact not found")

        available_replicas = [replica for replica in artifact.replicas if replica.upload_status == ReplicaStatus.AVAILABLE.value]
        if not available_replicas:
            raise ValueError("Artifact has no available replicas")

        private_replica = None
        public_replica = None
        for replica in available_replicas:
            is_private, _ = self.cos_service.verify_download_route(replica)
            if is_private and not private_replica:
                private_replica = replica
            if not is_private and not public_replica:
                public_replica = replica

        selected_replica = private_replica or public_replica
        restore_job = RestoreJob(
            artifact_id=artifact.id,
            replica_id=selected_replica.id if selected_replica else None,
            restore_path=normalized_restore_path,
            status=JobStatus.PENDING.value if private_replica else JobStatus.WAITING_CONFIRMATION.value,
            requires_public_confirm=private_replica is None,
            public_confirmed=False,
            checksum_verified=False,
        )
        saved_job = self.repository.save_restore_job(restore_job)
        self.log_service.audit(
            action="restore.create",
            actor="admin",
            target_type="restore_job",
            target_id=str(saved_job.id),
            outcome="success",
            detail="Restore job created." if private_replica else "Restore job requires public download confirmation.",
        )
        return saved_job

    def confirm_public_restore(self, restore_job_id: int) -> RestoreJob:
        """
        Approve a restore job that would use public COS egress.

        Args:
            restore_job_id: Restore job primary key.

        Returns:
            Updated restore job entity.

        Raises:
            ValueError: Raised when the restore job does not exist.
        """

        restore_job = self.repository.get_restore_job(restore_job_id)
        if not restore_job:
            raise ValueError("Restore job not found")
        restore_job.public_confirmed = True
        restore_job.requires_public_confirm = False
        restore_job.status = JobStatus.PENDING.value
        self.session.add(restore_job)
        self.session.flush()
        self.log_service.audit(
            action="restore.public_confirm",
            actor="admin",
            target_type="restore_job",
            target_id=str(restore_job.id),
            outcome="success",
            detail="Public COS download approved by administrator.",
        )
        return restore_job

    def run_restore_job(self, restore_job_id: int) -> RestoreJob:
        """
        Execute a restore job by downloading, validating, and extracting the archive.

        Args:
            restore_job_id: Restore job primary key.

        Returns:
            Updated restore job entity after execution.

        Raises:
            ValueError: Raised when the restore job is missing or not ready.
        """

        restore_job = self.repository.get_restore_job(restore_job_id)
        if not restore_job:
            raise ValueError("Restore job not found")
        if restore_job.requires_public_confirm and not restore_job.public_confirmed:
            raise ValueError("Restore job requires public download confirmation")
        if not restore_job.replica_id:
            raise ValueError("Restore job does not have a selected replica")

        artifact = self.repository.get_artifact(restore_job.artifact_id)
        if not artifact:
            raise ValueError("Artifact not found")

        replica = next((item for item in artifact.replicas if item.id == restore_job.replica_id), None)
        if not replica:
            raise ValueError("Selected replica not found")

        restore_job.status = JobStatus.RUNNING.value
        self.session.add(restore_job)
        self.session.flush()

        with NamedTemporaryFile(dir=settings.temp_dir, suffix=".zip", delete=False) as temp_archive:
            temp_archive_path = Path(temp_archive.name)

        try:
            self.cos_service.download_file(replica, str(temp_archive_path))
            archive_sha256 = hashlib.sha256(temp_archive_path.read_bytes()).hexdigest()
            if archive_sha256 != artifact.sha256:
                raise ValueError("Downloaded archive checksum verification failed")
            restore_job.checksum_verified = True

            target_path = ensure_allowed_path(restore_job.restore_path)
            if target_path.exists():
                shutil.rmtree(target_path)
            target_path.mkdir(parents=True, exist_ok=True)

            task = self.repository.get_task(artifact.task_id)
            if not task:
                raise ValueError("Backup task not found")
            zip_password = decrypt_text(task.zip_password_ciphertext, task.zip_password_nonce, f"zip_password:{task.name}")
            with pyzipper.AESZipFile(temp_archive_path) as archive:
                archive.setpassword(zip_password.encode("utf-8"))
                archive.extractall(path=target_path.parent)

            restore_job.status = JobStatus.SUCCESS.value
        except Exception as error:
            restore_job.status = JobStatus.FAILED.value
            restore_job.error_message = str(error)
            raise
        finally:
            temp_archive_path.unlink(missing_ok=True)
            self.session.add(restore_job)
            self.session.flush()
            self.log_service.audit(
                action="restore.run",
                actor="worker",
                target_type="restore_job",
                target_id=str(restore_job.id),
                outcome="success" if restore_job.status == JobStatus.SUCCESS.value else "failure",
                detail=restore_job.error_message or "Restore job executed.",
            )
        return restore_job

    def list_restore_jobs(self) -> list[RestoreJob]:
        """
        Return all restore jobs for the admin UI.

        Returns:
            Restore job entities.
        """

        return self.repository.list_restore_jobs()

    def list_pending_restore_jobs(self) -> list[RestoreJob]:
        """
        Retrieve restore jobs that are ready to execute.

        Returns:
            Pending restore job entities approved for worker execution.
        """

        return self.repository.list_pending_restore_jobs()
