"""APScheduler bootstrap for backup and restore worker jobs."""

from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from app.core.logging import configure_logging, get_logger
from app.db.base import Base, engine, session_scope
from app.services.auth_service import AuthService
from app.services.backup_service import BackupService


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
        BackupService(session).run_task(task_id)


def _run_pending_restores() -> None:
    """
    Execute all restore jobs that are pending and approved.

    Returns:
        None. Ready restore jobs are processed for their side effects.
    """

    with session_scope() as session:
        service = BackupService(session)
        for restore_job in service.list_pending_restore_jobs():
            service.run_restore_job(restore_job.id)


def build_scheduler() -> BlockingScheduler:
    """
    Build a scheduler instance from active backup task definitions.

    Returns:
        Configured APScheduler instance.
    """

    scheduler = BlockingScheduler()
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
    return scheduler


def main() -> None:
    """
    Start the worker scheduler loop.

    Returns:
        None. The process blocks until shutdown.
    """

    configure_logging()
    Base.metadata.create_all(bind=engine)
    with session_scope() as session:
        AuthService(session).ensure_bootstrap_admin()
    scheduler = build_scheduler()
    logger.info("Starting backup scheduler")
    scheduler.start()


if __name__ == "__main__":
    main()
