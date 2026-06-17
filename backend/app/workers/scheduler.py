"""APScheduler bootstrap for backup and restore worker jobs."""

from __future__ import annotations

from datetime import datetime

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import configure_logging, get_logger
from app.db.base import Base, engine, ensure_schema_compatibility, session_scope
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService
from app.services.backup_service import BackupRunCanceledError


logger = get_logger(__name__)


def _run_task(task_id: int) -> None:
    """
    Execute a backup task inside a managed database session.

    Args:
        task_id: Backup task primary key.

    Returns:
        None. The task is run for its side effects.
    """

    with session_scope() as session:
        BackupService(session).start_scheduled_task_run(task_id)


def _run_pending_backup_requests() -> None:
    """
    Execute queued manual backup requests in FIFO order.

    Returns:
        None. Pending backup requests are processed for their side effects.
    """

    with session_scope() as session:
        service = BackupService(session)
        for run_request in service.list_pending_run_requests():
            try:
                service.execute_run_request(run_request.id)
            except BackupRunCanceledError:
                logger.info(
                    "Manual backup run request canceled safely",
                    extra={"run_request_id": run_request.id, "task_id": run_request.task_id},
                )
            except Exception:
                logger.exception(
                    "Manual backup run request failed",
                    extra={"run_request_id": run_request.id, "task_id": run_request.task_id},
                )


def _run_pending_restores() -> None:
    """
    Execute all restore jobs that are pending and approved.

    Returns:
        None. Ready restore jobs are processed for their side effects.
    """

    with session_scope() as session:
        service = BackupService(session)
        for restore_job in service.list_pending_restore_jobs():
            try:
                service.run_restore_job(restore_job.id)
            except Exception:
                logger.exception("Restore job failed", extra={"restore_job_id": restore_job.id})


def build_scheduler() -> BlockingScheduler:
    """
    Build a scheduler instance from active backup task definitions.

    Returns:
        Configured APScheduler instance.
    """

    scheduler = BlockingScheduler()
    scheduler.add_job(
        _run_pending_backup_requests,
        IntervalTrigger(seconds=15),
        id="manual-backup-request-poller",
        replace_existing=True,
    )
    scheduler.add_job(
        _run_pending_restores,
        IntervalTrigger(minutes=1),
        id="restore-job-poller",
        replace_existing=True,
    )
    with session_scope() as session:
        service = BackupService(session)
        for task in service.list_tasks():
            if not task.enabled:
                continue
            if task.schedule_type == "interval" and task.interval_minutes:
                scheduler.add_job(
                    _run_task,
                    IntervalTrigger(minutes=task.interval_minutes),
                    args=[task.id],
                    id=f"backup-task-{task.id}",
                    replace_existing=True,
                )
            elif task.schedule_type == "weekly" and task.weekday_mask and task.run_time:
                scheduler.add_job(
                    _run_task,
                    CronTrigger(
                        day_of_week=task.weekday_mask,
                        hour=task.run_time.hour,
                        minute=task.run_time.minute,
                    ),
                    args=[task.id],
                    id=f"backup-task-{task.id}",
                    replace_existing=True,
                )
            elif task.schedule_type == "once" and task.scheduled_at:
                scheduled_at = task.scheduled_at
                current_time = datetime.now(scheduled_at.tzinfo) if scheduled_at.tzinfo else datetime.now()
                if scheduled_at <= current_time:
                    logger.warning("Skip expired one-time backup task %s at %s", task.id, scheduled_at.isoformat())
                    continue
                scheduler.add_job(
                    _run_task,
                    DateTrigger(run_date=scheduled_at),
                    args=[task.id],
                    id=f"backup-task-{task.id}",
                    replace_existing=True,
                )
    return scheduler


def main() -> None:
    """
    Start the worker scheduler loop.

    Returns:
        None. The process blocks until shutdown.
    """

    configure_logging()
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    with session_scope() as session:
        AuthService(session).ensure_bootstrap_admin()
    scheduler = build_scheduler()
    logger.info("Starting backup scheduler")
    scheduler.start()


if __name__ == "__main__":
    main()
