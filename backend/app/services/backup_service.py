"""Backup creation, upload orchestration, and restore execution service."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
from tempfile import NamedTemporaryFile
from time import monotonic
from typing import Callable
from zipfile import ZIP_DEFLATED

import pyzipper
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import decrypt_text, encrypt_text, ensure_allowed_path, generate_random_id
from app.models.entities import ArtifactReplica, BackupArtifact, BackupRunBucketProgress, BackupRunRequest, BackupTask
from app.models.entities import CosBucket
from app.models.entities import JobStatus, ReplicaStatus, RestoreJob
from app.models.entities import ScheduleType
from app.repositories.backup import BackupRepository
from app.repositories.cos import CosRepository
from app.services.cos_service import CosService
from app.services.log_service import LogService


class BackupRunCanceledError(Exception):
    """Raised when a backup run is canceled safely by an operator."""


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

    def _sort_buckets_for_upload(self, buckets: list[CosBucket]) -> list[CosBucket]:
        """
        Order target buckets so verified private-route COS buckets upload first.

        Args:
            buckets: Target bucket entities in task-defined order.

        Returns:
            Buckets sorted by route preference while preserving order within each group.
        """

        def priority(indexed_bucket: tuple[int, CosBucket]) -> tuple[int, int]:
            index, bucket = indexed_bucket
            status = str(getattr(bucket, "status", ""))
            private_route_verified = bool(getattr(bucket, "last_nslookup_private", False))
            private_route_available = status in {"private_route", "available_private"}
            user_expected_private = bool(getattr(bucket, "user_expected_private_route", False))
            if private_route_verified or private_route_available:
                return (0, index)
            if user_expected_private:
                return (1, index)
            return (2, index)

        return [bucket for _, bucket in sorted(enumerate(buckets), key=priority)]

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
        normalized_schedule = self._normalize_schedule_payload(payload)
        task = self.repository.get_task(task_id) if task_id else None
        if not task:
            if not payload.get("zip_password"):
                raise ValueError("ZIP password is required")
            encrypted_password = encrypt_text(str(payload["zip_password"]), f"zip_password:{payload['name']}")
            task = BackupTask(
                name=str(payload["name"]),
                source_path=normalized_source_path,
                zip_password_ciphertext=encrypted_password["ciphertext"],
                zip_password_nonce=encrypted_password["nonce"],
                schedule_type=str(normalized_schedule["schedule_type"]),
            )

        previous_name = task.name
        next_name = str(payload["name"])
        if payload.get("zip_password"):
            encrypted_password = encrypt_text(str(payload["zip_password"]), f"zip_password:{next_name}")
            task.zip_password_ciphertext = encrypted_password["ciphertext"]
            task.zip_password_nonce = encrypted_password["nonce"]
        elif previous_name != next_name:
            zip_password = decrypt_text(task.zip_password_ciphertext, task.zip_password_nonce, f"zip_password:{previous_name}")
            encrypted_password = encrypt_text(zip_password, f"zip_password:{next_name}")
            task.zip_password_ciphertext = encrypted_password["ciphertext"]
            task.zip_password_nonce = encrypted_password["nonce"]
        task.name = next_name
        task.source_path = normalized_source_path
        task.schedule_type = str(normalized_schedule["schedule_type"])
        task.interval_minutes = normalized_schedule["interval_minutes"]
        task.weekday_mask = normalized_schedule["weekday_mask"]
        task.run_time = normalized_schedule["run_time"]
        task.scheduled_at = normalized_schedule["scheduled_at"]
        task.retention_count = payload.get("retention_count")
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

    def _normalize_schedule_payload(self, payload: dict[str, object]) -> dict[str, object]:
        """
        Normalize schedule fields so each schedule mode stores only its own relevant values.

        Args:
            payload: Raw task payload from the API layer.

        Returns:
            Dictionary containing normalized schedule fields.

        Raises:
            ValueError: Raised when the schedule type is not supported.
        """

        schedule_type = str(payload["schedule_type"])
        interval_minutes = payload.get("interval_minutes")
        weekday_mask = payload.get("weekday_mask")
        run_time = payload.get("run_time")
        scheduled_at = payload.get("scheduled_at")

        if schedule_type == ScheduleType.INTERVAL.value:
            return {
                "schedule_type": schedule_type,
                "interval_minutes": interval_minutes,
                "weekday_mask": None,
                "run_time": None,
                "scheduled_at": None,
            }
        if schedule_type == ScheduleType.WEEKLY.value:
            return {
                "schedule_type": schedule_type,
                "interval_minutes": None,
                "weekday_mask": weekday_mask,
                "run_time": run_time,
                "scheduled_at": None,
            }
        if schedule_type == ScheduleType.ONCE.value:
            return {
                "schedule_type": schedule_type,
                "interval_minutes": None,
                "weekday_mask": None,
                "run_time": None,
                "scheduled_at": scheduled_at,
            }
        raise ValueError("Unsupported schedule type")

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

    def delete_task(self, task_id: int) -> None:
        """
        Delete a backup task and all backup state that depends on it.

        Args:
            task_id: Backup task primary key.

        Returns:
            None. Artifacts, replicas, restore jobs, run history, bucket links, and the task are removed.

        Raises:
            ValueError: Raised when the task is missing or has active runs.
        """

        task = self.repository.get_task(task_id)
        if not task:
            raise ValueError("Backup task not found")
        if self.repository.list_active_run_requests_for_task(task_id):
            raise ValueError("Cannot delete a task with queued or running backup jobs")

        artifacts = self.repository.list_artifacts_for_task(task_id)
        for artifact in artifacts:
            self.delete_artifact(
                artifact.id,
                actor="admin",
                detail=f"Artifact {artifact.id} deleted with backup task {task_id}.",
            )
        self.repository.delete_run_requests_for_task(task_id)
        self.repository.delete_task(task)
        self.log_service.audit(
            action="backup.task_delete",
            actor="admin",
            target_type="backup_task",
            target_id=str(task_id),
            outcome="success",
            detail=f"Backup task {task.name} deleted with dependent backup state.",
        )

    def _commit_progress(self) -> None:
        """
        Persist in-flight progress updates so other processes can observe them immediately.

        Returns:
            None. The current SQLAlchemy transaction is committed in place.
        """

        self.session.commit()

    def _refresh_run_request(self, run_request: BackupRunRequest) -> BackupRunRequest:
        """
        Reload one run request from the database so worker code can observe cancel flags.

        Args:
            run_request: In-memory run request entity from the current session.

        Returns:
            The same run request entity refreshed with the latest database state.
        """

        self.session.refresh(run_request)
        return run_request

    def _raise_if_run_canceled(self, run_request: BackupRunRequest | None) -> None:
        """
        Stop execution when the operator has requested safe cancellation.

        Args:
            run_request: Active run request entity or None outside worker-tracked execution.

        Returns:
            None. Execution continues when no cancel request is present.

        Raises:
            BackupRunCanceledError: Raised when the current run request was canceled.
        """

        if not run_request:
            return
        self._refresh_run_request(run_request)
        if run_request.cancel_requested:
            raise BackupRunCanceledError("备份作业已被手动终止")

    def _update_run_request_step(
        self,
        run_request: BackupRunRequest,
        step: str,
        message: str,
        unit: str | None = None,
        total: int = 0,
        completed: int = 0,
        status: str | None = None,
        commit: bool = True,
    ) -> None:
        """
        Update the visible top-level progress state for one backup run request.

        Args:
            run_request: Run request entity to update.
            step: Current execution step code.
            message: Human-readable step detail.
            unit: Unit for total and completed values.
            total: Total work units in the current step.
            completed: Completed work units in the current step.
            status: Optional lifecycle status override.
            commit: Whether to commit immediately after flushing.

        Returns:
            None. The run request row is updated in place.
        """

        safe_total = max(total, 0)
        safe_completed = min(max(completed, 0), safe_total) if safe_total else max(completed, 0)
        run_request.current_step = step
        run_request.step_message = message
        run_request.step_unit = unit
        run_request.step_total = safe_total
        run_request.step_completed = safe_completed
        run_request.progress_percent = int((safe_completed / safe_total) * 100) if safe_total > 0 else 0
        if status:
            run_request.status = status
        self.session.add(run_request)
        self.session.flush()
        if commit:
            self._commit_progress()

    def _collect_source_entries(self, source_path: Path) -> tuple[list[tuple[Path, Path, int]], int]:
        """
        Walk the source directory once and collect file metadata for compression progress tracking.

        Args:
            source_path: Backup source directory path.

        Returns:
            Tuple of file entries and total source byte count.
        """

        file_entries: list[tuple[Path, Path, int]] = []
        total_bytes = 0
        for root, _, files in os.walk(source_path):
            for file_name in files:
                absolute_path = Path(root) / file_name
                try:
                    file_size = absolute_path.stat().st_size
                except FileNotFoundError:
                    continue
                relative_path = absolute_path.relative_to(source_path.parent)
                file_entries.append((absolute_path, relative_path, file_size))
                total_bytes += file_size
        return file_entries, total_bytes

    def _collect_source_entries_for_run(
        self,
        source_path: Path,
        run_request: BackupRunRequest | None,
    ) -> tuple[list[tuple[Path, Path, int]], int]:
        """
        Walk the source directory with cooperative cancel checks for one tracked backup run.

        Args:
            source_path: Backup source directory path.
            run_request: Active run request entity or None.

        Returns:
            Tuple of file entries and total source byte count.
        """

        self._raise_if_run_canceled(run_request)
        file_entries: list[tuple[Path, Path, int]] = []
        total_bytes = 0
        for root, _, files in os.walk(source_path):
            self._raise_if_run_canceled(run_request)
            for file_name in files:
                self._raise_if_run_canceled(run_request)
                absolute_path = Path(root) / file_name
                try:
                    file_size = absolute_path.stat().st_size
                except FileNotFoundError:
                    continue
                relative_path = absolute_path.relative_to(source_path.parent)
                file_entries.append((absolute_path, relative_path, file_size))
                total_bytes += file_size
        return file_entries, total_bytes

    def _calculate_file_sha256(
        self,
        file_path: Path,
        progress_callback: Callable[[int, int], None] | None = None,
    ) -> str:
        """
        Calculate SHA256 for one file with optional chunk-level progress callbacks.

        Args:
            file_path: File path to hash.
            progress_callback: Optional callback receiving completed and total bytes.

        Returns:
            Hexadecimal SHA256 digest string.
        """

        total_bytes = file_path.stat().st_size
        completed_bytes = 0
        digest = hashlib.sha256()
        with file_path.open("rb") as file_handle:
            while True:
                chunk = file_handle.read(1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                completed_bytes += len(chunk)
                if progress_callback:
                    progress_callback(completed_bytes, total_bytes)
        if progress_callback and total_bytes == 0:
            progress_callback(0, 0)
        return digest.hexdigest()

    def _build_archive(
        self,
        task: BackupTask,
        run_request: BackupRunRequest | None = None,
        progress_callback: Callable[[str, int, int, int, int], None] | None = None,
    ) -> tuple[Path, str, str]:
        """
        Build an AES ZIP archive and checksum for the task source directory.

        Args:
            task: Backup task entity.
            progress_callback: Optional callback receiving step code, completed bytes,
                total bytes, completed files, and total files during archive building.

        Returns:
            Tuple of archive path, archive filename, and SHA256 checksum.
        """

        source_path = ensure_allowed_path(task.source_path)
        zip_password = decrypt_text(task.zip_password_ciphertext, task.zip_password_nonce, f"zip_password:{task.name}")
        archive_name = f"{task.name}-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}.zip"
        archive_path = settings.temp_dir / archive_name
        file_entries, total_source_bytes = self._collect_source_entries_for_run(source_path, run_request)
        total_files = len(file_entries)
        manifest = {
            "task_id": task.id,
            "task_name": task.name,
            "source_path": str(source_path),
            "created_at": datetime.now(UTC).isoformat(),
            "skipped_files": [],
        }

        if progress_callback:
            progress_callback("compressing", 0, total_source_bytes, 0, total_files)

        processed_source_bytes = 0
        processed_files = 0
        try:
            with pyzipper.AESZipFile(archive_path, "w", compression=ZIP_DEFLATED, encryption=pyzipper.WZ_AES) as archive:
                archive.setpassword(zip_password.encode("utf-8"))
                for absolute_path, relative_path, file_size in file_entries:
                    self._raise_if_run_canceled(run_request)
                    try:
                        archive.write(absolute_path, arcname=str(relative_path))
                    except FileNotFoundError:
                        manifest["skipped_files"].append(str(relative_path))
                        total_source_bytes = max(processed_source_bytes, total_source_bytes - file_size)
                        total_files = max(processed_files, total_files - 1)
                        if progress_callback:
                            progress_callback(
                                "compressing",
                                processed_source_bytes,
                                total_source_bytes,
                                processed_files,
                                total_files,
                            )
                        continue
                    processed_source_bytes += file_size
                    processed_files += 1
                    if progress_callback:
                        progress_callback(
                            "compressing",
                            processed_source_bytes,
                            total_source_bytes,
                            processed_files,
                            total_files,
                        )
                archive.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))

            self._raise_if_run_canceled(run_request)
            if progress_callback:
                progress_callback("checksumming", 0, archive_path.stat().st_size, total_files, total_files)
            sha256 = self._calculate_file_sha256(
                archive_path,
                lambda completed, total: progress_callback("checksumming", completed, total, total_files, total_files)
                if progress_callback
                else None,
            )
        except Exception:
            archive_path.unlink(missing_ok=True)
            raise
        return archive_path, archive_name, sha256

    def run_task(self, task_id: int, run_request: BackupRunRequest | None = None) -> BackupArtifact:
        """
        Execute one backup task immediately, upload results, and clean up the archive.

        Args:
            task_id: Task primary key.
            run_request: Optional persisted run request used for real-time progress tracking.

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

        compression_state = {"last_commit_at": 0.0}

        def handle_archive_progress(
            step: str,
            completed_bytes: int,
            total_bytes: int,
            processed_files: int,
            total_files: int,
        ) -> None:
            """
            Persist archive-building progress for the active run request.

            Args:
                step: Current archive step code.
                completed_bytes: Completed byte count for the current step.
                total_bytes: Total byte count for the current step.
                processed_files: Processed file count during compression.
                total_files: Total file count during compression.

            Returns:
                None. Progress is flushed and throttled commits are applied.
            """

            if not run_request:
                return
            self._raise_if_run_canceled(run_request)
            if step == "compressing":
                message = f"正在压缩文件 {processed_files}/{total_files}"
            else:
                message = "正在计算压缩包校验值"
            should_commit = (monotonic() - compression_state["last_commit_at"]) >= 0.5 or completed_bytes >= total_bytes
            self._update_run_request_step(
                run_request,
                step,
                message,
                unit="bytes",
                total=total_bytes,
                completed=completed_bytes,
                status=JobStatus.RUNNING.value,
                commit=should_commit,
            )
            if should_commit:
                compression_state["last_commit_at"] = monotonic()

        archive_path: Path | None = None
        artifact: BackupArtifact | None = None
        success_count = 0
        created_replicas: list[tuple[object, ArtifactReplica]] = []
        try:
            archive_path, archive_name, sha256 = self._build_archive(
                task,
                run_request=run_request,
                progress_callback=handle_archive_progress if run_request else None,
            )
            self._raise_if_run_canceled(run_request)
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
            target_buckets = [self.cos_repository.get_bucket(task_bucket.bucket_id) for task_bucket in task.buckets]
            available_buckets = self._sort_buckets_for_upload([bucket for bucket in target_buckets if bucket])
            expected_upload_bytes_total = size_bytes * len(available_buckets)

            if run_request:
                self._update_run_request_step(
                    run_request,
                    "uploading",
                    f"正在准备上传到 {len(available_buckets)} 个存储桶",
                    unit="bytes",
                    total=expected_upload_bytes_total,
                    completed=0,
                    status=JobStatus.RUNNING.value,
                )

            bucket_progress_rows: list[BackupRunBucketProgress] = []
            for bucket in available_buckets:
                self._raise_if_run_canceled(run_request)
                object_key = f"autobackup/{task.name}/{archive_name}"
                bucket_progress = None
                bucket_commit_state = {"last_commit_at": 0.0}
                if run_request:
                    bucket_progress = self.repository.save_bucket_progress(
                        BackupRunBucketProgress(
                            run_request_id=run_request.id,
                            bucket_id=bucket.id,
                            bucket_name=bucket.name,
                            bucket_region=bucket.region,
                            object_key=object_key,
                            status=JobStatus.PENDING.value,
                            total_bytes=size_bytes,
                            uploaded_bytes=0,
                            progress_percent=0,
                        )
                    )
                    bucket_progress_rows.append(bucket_progress)
                    self._commit_progress()

                def handle_upload_progress(uploaded_bytes: int, total_bytes: int) -> None:
                    """
                    Persist one bucket upload progress callback from the COS SDK.

                    Args:
                        uploaded_bytes: Uploaded bytes already sent.
                        total_bytes: Total bytes expected for this bucket upload.

                    Returns:
                        None. Progress rows are updated in place.
                    """

                    if not run_request or not bucket_progress:
                        return
                    self._raise_if_run_canceled(run_request)
                    safe_total = max(total_bytes, 0)
                    safe_uploaded = min(max(uploaded_bytes, 0), safe_total) if safe_total else max(uploaded_bytes, 0)
                    bucket_progress.status = JobStatus.RUNNING.value
                    bucket_progress.total_bytes = safe_total
                    bucket_progress.uploaded_bytes = safe_uploaded
                    bucket_progress.progress_percent = int((safe_uploaded / safe_total) * 100) if safe_total > 0 else 0
                    self.session.add(bucket_progress)
                    total_uploaded = sum(item.uploaded_bytes for item in bucket_progress_rows)
                    should_commit = (monotonic() - bucket_commit_state["last_commit_at"]) >= 0.5 or safe_uploaded >= safe_total
                    self._update_run_request_step(
                        run_request,
                        "uploading",
                        f"正在上传到存储桶 {bucket.name} ({bucket.region})",
                        unit="bytes",
                        total=expected_upload_bytes_total,
                        completed=total_uploaded,
                        status=JobStatus.RUNNING.value,
                        commit=False,
                    )
                    self.session.flush()
                    if should_commit:
                        self._commit_progress()
                        bucket_commit_state["last_commit_at"] = monotonic()

                replica = self.repository.save_replica(
                    ArtifactReplica(
                        artifact_id=artifact.id,
                        bucket_id=bucket.id,
                        object_key=object_key,
                        upload_status=ReplicaStatus.PENDING.value,
                    )
                )
                created_replicas.append((bucket, replica))
                try:
                    upload_result = self.cos_service.upload_file(
                        bucket,
                        object_key,
                        str(archive_path),
                        progress_callback=handle_upload_progress if run_request else None,
                    )
                    replica.upload_status = ReplicaStatus.AVAILABLE.value
                    replica.etag = str(upload_result.get("ETag", ""))
                    replica.size_bytes = size_bytes
                    if bucket_progress:
                        bucket_progress.status = JobStatus.SUCCESS.value
                        bucket_progress.uploaded_bytes = size_bytes
                        bucket_progress.total_bytes = size_bytes
                        bucket_progress.progress_percent = 100
                    success_count += 1
                except BackupRunCanceledError:
                    replica.upload_status = ReplicaStatus.DELETED.value
                    replica.error_message = "备份作业已被手动终止"
                    if bucket_progress:
                        bucket_progress.status = JobStatus.CANCELED.value
                        bucket_progress.error_message = "备份作业已被手动终止"
                    self.cos_service.cleanup_object_uploads(bucket, object_key)
                    raise
                except Exception as error:
                    replica.upload_status = ReplicaStatus.FAILED.value
                    replica.error_message = str(error)
                    if bucket_progress:
                        bucket_progress.status = JobStatus.FAILED.value
                        bucket_progress.error_message = str(error)
                self.session.add(replica)
                if bucket_progress:
                    self.session.add(bucket_progress)
                self.session.flush()
                if run_request:
                    self._update_run_request_step(
                        run_request,
                        "uploading",
                        f"已完成 {success_count}/{len(available_buckets)} 个存储桶上传",
                        unit="bytes",
                        total=expected_upload_bytes_total,
                        completed=sum(item.uploaded_bytes for item in bucket_progress_rows),
                        status=JobStatus.RUNNING.value,
                    )

            artifact.status = JobStatus.SUCCESS.value if success_count > 0 else JobStatus.FAILED.value
            self.session.add(artifact)
            self.session.flush()
            if success_count > 0:
                self._prune_old_artifacts(task)
            if run_request:
                final_status = JobStatus.SUCCESS.value if success_count > 0 else JobStatus.FAILED.value
                final_step = "completed" if success_count > 0 else "failed"
                final_message = (
                    f"备份已完成，成功上传到 {success_count} 个存储桶"
                    if success_count > 0
                    else "备份执行失败，没有存储桶上传成功"
                )
                self._update_run_request_step(
                    run_request,
                    final_step,
                    final_message,
                    unit=None,
                    total=1,
                    completed=1 if success_count > 0 else 0,
                    status=final_status,
                )
        except BackupRunCanceledError:
            for bucket, replica in created_replicas:
                if replica.object_key and replica.upload_status in {ReplicaStatus.AVAILABLE.value, ReplicaStatus.PENDING.value}:
                    try:
                        self.cos_service.cleanup_object_uploads(bucket, replica.object_key)
                    except Exception:
                        self.log_service.app_log(
                            "WARNING",
                            __name__,
                            "Canceled backup cleanup could not clean remote object uploads.",
                            detail=f"bucket_id={bucket.id}, object_key={replica.object_key}",
                        )
                replica.upload_status = ReplicaStatus.DELETED.value
                replica.error_message = "备份作业已被手动终止"
                self.session.add(replica)
            if artifact:
                artifact.status = JobStatus.CANCELED.value
                self.session.add(artifact)
            self.session.flush()
            raise
        finally:
            if archive_path:
                archive_path.unlink(missing_ok=True)
        self.log_service.audit(
            action="backup.task_run",
            actor="worker",
            target_type="backup_task",
            target_id=str(task.id),
            outcome="success" if success_count > 0 else "failure",
            detail=f"Backup uploaded to {success_count} buckets.",
        )
        if not artifact:
            raise ValueError("Backup artifact was not created")
        return self.repository.get_artifact(artifact.id) or artifact

    def create_run_request(self, task_id: int, trigger_source: str, actor: str) -> BackupRunRequest:
        """
        Create one persisted backup run request row before worker execution starts.

        Args:
            task_id: Backup task primary key.
            trigger_source: Source of the run request, such as manual or scheduler.
            actor: Audit actor string for the queue event.

        Returns:
            Persisted backup run request entity.

        Raises:
            ValueError: Raised when the task does not exist or has no target buckets.
        """

        task = self.repository.get_task(task_id)
        if not task:
            raise ValueError("Backup task not found")
        if not task.buckets:
            raise ValueError("Backup task has no target buckets")

        run_request = self.repository.save_run_request(
            BackupRunRequest(
                task_id=task.id,
                trigger_source=trigger_source,
                status=JobStatus.PENDING.value,
                current_step="queued",
                step_message="等待 worker 执行",
                step_unit=None,
                step_total=0,
                step_completed=0,
                progress_percent=0,
                cancel_requested=False,
            )
        )
        self.log_service.audit(
            action="backup.task_enqueue",
            actor=actor,
            target_type="backup_task",
            target_id=str(task.id),
            outcome="success",
            detail=f"Backup run queued with request id {run_request.id} from {trigger_source}.",
        )
        return run_request

    def enqueue_task_run(self, task_id: int) -> BackupRunRequest:
        """
        Queue one manual backup execution for worker-side processing.

        Args:
            task_id: Backup task primary key.

        Returns:
            Persisted manual run request entity.
        """

        return self.create_run_request(task_id, trigger_source="manual", actor="admin")

    def start_scheduled_task_run(self, task_id: int) -> BackupArtifact:
        """
        Create and execute one scheduler-triggered backup run request immediately.

        Args:
            task_id: Backup task primary key.

        Returns:
            Persisted logical backup artifact.
        """

        run_request = self.create_run_request(task_id, trigger_source="scheduler", actor="worker")
        return self.execute_run_request(run_request.id)

    def execute_run_request(self, run_request_id: int) -> BackupArtifact:
        """
        Execute one queued backup request inside the worker process.

        Args:
            run_request_id: Run request primary key.

        Returns:
            Persisted logical backup artifact.

        Raises:
            ValueError: Raised when the run request does not exist.
            Exception: Re-raises backup execution failures after persisting failure state.
        """

        run_request = self.repository.get_run_request(run_request_id)
        if not run_request:
            raise ValueError("Backup run request not found")
        if run_request.status == JobStatus.CANCELED.value or (
            run_request.cancel_requested and run_request.status == JobStatus.PENDING.value
        ):
            run_request.status = JobStatus.CANCELED.value
            run_request.current_step = "canceled"
            run_request.step_message = "备份作业已取消，未进入执行"
            run_request.finished_at = datetime.now(UTC)
            self.session.add(run_request)
            self.session.flush()
            self._commit_progress()
            raise BackupRunCanceledError("Backup run request canceled before execution")

        run_request.started_at = datetime.now(UTC)
        run_request.finished_at = None
        run_request.error_message = None
        self._update_run_request_step(
            run_request,
            "scanning",
            "正在扫描源目录结构",
            unit=None,
            total=0,
            completed=0,
            status=JobStatus.RUNNING.value,
        )
        try:
            artifact = self.run_task(run_request.task_id, run_request=run_request)
            run_request.artifact_id = artifact.id
            run_request.finished_at = datetime.now(UTC)
            self.session.add(run_request)
            self.session.flush()
            self._commit_progress()
            return artifact
        except BackupRunCanceledError as error:
            run_request.finished_at = datetime.now(UTC)
            run_request.error_message = str(error)
            self._update_run_request_step(
                run_request,
                "canceled",
                "备份作业已安全终止并完成清理",
                unit=None,
                total=0,
                completed=0,
                status=JobStatus.CANCELED.value,
            )
            self.log_service.audit(
                action="backup.task_cancel",
                actor="admin",
                target_type="backup_run_request",
                target_id=str(run_request.id),
                outcome="success",
                detail="Backup run canceled safely.",
            )
            raise
        except Exception as error:
            run_request.finished_at = datetime.now(UTC)
            run_request.error_message = str(error)
            self._update_run_request_step(
                run_request,
                "failed",
                f"备份失败: {error}",
                unit=None,
                total=0,
                completed=0,
                status=JobStatus.FAILED.value,
            )
            self.log_service.audit(
                action="backup.task_enqueue_run",
                actor="worker",
                target_type="backup_run_request",
                target_id=str(run_request.id),
                outcome="failure",
                detail=f"Queued manual backup failed: {error}",
            )
            raise

    def cancel_run_request(self, run_request_id: int) -> BackupRunRequest:
        """
        Cancel one queued or running backup request and mark it for worker-side cleanup.

        Args:
            run_request_id: Backup run request primary key.

        Returns:
            Updated backup run request entity.

        Raises:
            ValueError: Raised when the run request does not exist or has already finished.
        """

        run_request = self.repository.get_run_request(run_request_id)
        if not run_request:
            raise ValueError("Backup run request not found")
        if run_request.status in {JobStatus.SUCCESS.value, JobStatus.FAILED.value, JobStatus.CANCELED.value}:
            raise ValueError("Backup run request has already finished")

        run_request.cancel_requested = True
        if run_request.status == JobStatus.PENDING.value:
            run_request.status = JobStatus.CANCELED.value
            run_request.current_step = "canceled"
            run_request.step_message = "备份作业已取消，未进入执行"
            run_request.finished_at = datetime.now(UTC)
        else:
            run_request.current_step = "cancel_requested"
            run_request.step_message = "正在安全终止并清理当前备份作业"
        self.session.add(run_request)
        self.session.flush()
        self.log_service.audit(
            action="backup.task_cancel_request",
            actor="admin",
            target_type="backup_run_request",
            target_id=str(run_request.id),
            outcome="success",
            detail="Backup run cancellation requested.",
        )
        return run_request

    def list_run_requests(self, limit: int = 100) -> list[BackupRunRequest]:
        """
        Return recent backup run requests for the admin UI.

        Args:
            limit: Maximum number of run requests to return.

        Returns:
            Recent backup run request entities.
        """

        return self.repository.list_recent_run_requests(limit=limit)

    def list_artifacts(self) -> list[BackupArtifact]:
        """
        Return all logical backup artifacts.

        Returns:
            Artifact entities.
        """

        return self.repository.list_artifacts()

    def _prune_old_artifacts(self, task: BackupTask) -> None:
        """
        Delete old successful artifacts exceeding the task retention count.

        Args:
            task: Backup task whose successful artifact history should be pruned.

        Returns:
            None. Old remote objects and database rows are removed when retention is enabled.
        """

        if not task.retention_count:
            return

        old_artifacts = self.repository.list_success_artifacts_exceeding_retention(
            task.id,
            task.retention_count,
        )
        for artifact in old_artifacts:
            self.delete_artifact(
                artifact.id,
                actor="worker",
                detail=f"Artifact {artifact.id} deleted by retention policy for task {task.id}.",
            )

    def delete_artifact(
        self,
        artifact_id: int,
        actor: str = "admin",
        detail: str | None = None,
    ) -> None:
        """
        Delete a logical artifact from all buckets and remove its database rows.

        Args:
            artifact_id: Artifact primary key.
            actor: Audit actor string.
            detail: Optional audit detail override.

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

        self.repository.clear_run_request_artifact_references(artifact_id)
        self.repository.delete_restore_jobs_for_artifact(artifact_id)
        self.repository.delete_artifact(artifact)
        self.log_service.audit(
            action="artifact.delete",
            actor=actor,
            target_type="backup_artifact",
            target_id=str(artifact_id),
            outcome="success",
            detail=detail or f"Artifact {artifact_id} deleted across configured replicas.",
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

    def list_pending_run_requests(self) -> list[BackupRunRequest]:
        """
        Retrieve manual backup run requests that are ready to execute.

        Returns:
            Pending manual run request entities.
        """

        return self.repository.list_pending_run_requests()

    def finalize_stale_cancel_requested_runs(self) -> int:
        """
        Mark cancel-requested running jobs as canceled when no worker is executing them.

        Returns:
            Number of run requests finalized.
        """

        finalized_count = 0
        for run_request in self.repository.list_cancel_requested_running_run_requests():
            for bucket_progress in run_request.bucket_progresses:
                bucket = self.cos_repository.get_bucket(bucket_progress.bucket_id)
                if bucket and bucket_progress.object_key:
                    self.cos_service.cleanup_object_uploads(bucket, bucket_progress.object_key)
                bucket_progress.status = JobStatus.CANCELED.value
                bucket_progress.error_message = "备份作业已被手动终止"
                self.session.add(bucket_progress)
            run_request.status = JobStatus.CANCELED.value
            run_request.current_step = "canceled"
            run_request.step_message = "备份作业已安全终止"
            run_request.step_unit = None
            run_request.step_total = 0
            run_request.step_completed = 0
            run_request.progress_percent = 0
            run_request.finished_at = datetime.now(UTC)
            if not run_request.error_message:
                run_request.error_message = "备份作业已被手动终止"
            self.session.add(run_request)
            finalized_count += 1
        if finalized_count:
            self.session.flush()
            self._commit_progress()
        return finalized_count
