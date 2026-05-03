from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from core.db import db_execute, db_fetchone
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.scheduler_job_history import (
    fail_job_run,
    finish_job_run,
    record_skipped_job_run,
    start_job_run,
)
from core.sh_events import safe_log_sh_event
from core.system_alerts import create_system_alert

CHICAGO_TZ = ZoneInfo("America/Chicago")
SHELTERS = ("abba", "haven", "gratitude")
PASS_RETENTION_JOB_NAME = "pass_retention_cleanup"
PASS_RETENTION_JOB_LABEL = "Pass Retention Cleanup"
PASS_RETENTION_LOCK_KEY = 40926001
PASS_RETENTION_SCHEDULE_LABEL = "6:00 AM, 3:00 PM, and 11:00 PM Chicago time"


@dataclass(frozen=True)
class PassRetentionJobResult:
    status: str
    total_backfilled: int
    total_deleted: int
    total_errors: int
    shelter_results: list[dict[str, object]]
    message: str
    skipped: bool = False


def _database_url_is_sqlite(app) -> bool:
    database_url = str(app.config.get("DATABASE_URL") or "").strip().lower()
    return database_url.startswith("sqlite:")


def _try_acquire_job_lock(app) -> bool:
    if _database_url_is_sqlite(app):
        app.extensions["pass_retention_scheduler_lock_status"] = "sqlite_noop"
        return True

    row = db_fetchone(
        "SELECT pg_try_advisory_lock(%s) AS acquired",
        (PASS_RETENTION_LOCK_KEY,),
    )
    acquired = bool(row and row.get("acquired"))
    app.extensions["pass_retention_scheduler_lock_status"] = "acquired" if acquired else "skipped_lock"
    return acquired


def _release_job_lock(app) -> None:
    if _database_url_is_sqlite(app):
        return

    db_execute(
        "SELECT pg_advisory_unlock(%s)",
        (PASS_RETENTION_LOCK_KEY,),
    )
    app.extensions["pass_retention_scheduler_lock_status"] = "released"


@contextmanager
def _pass_retention_job_lock(app):
    acquired = _try_acquire_job_lock(app)
    try:
        yield acquired
    finally:
        if acquired:
            _release_job_lock(app)


def run_pass_retention_job(app, *, source: str = "external") -> PassRetentionJobResult:
    with app.app_context():
        with _pass_retention_job_lock(app) as lock_acquired:
            if not lock_acquired:
                message = "Skipped because another app instance already held the pass retention cleanup lock."
                record_skipped_job_run(
                    job_name=PASS_RETENTION_JOB_NAME,
                    job_label=PASS_RETENTION_JOB_LABEL,
                    result_summary=message,
                    metadata={
                        "lock_key": PASS_RETENTION_LOCK_KEY,
                        "reason": "advisory_lock_not_acquired",
                        "source": source,
                    },
                )
                app.logger.info(
                    "pass retention cleanup skipped because advisory lock was already held lock_key=%s source=%s",
                    PASS_RETENTION_LOCK_KEY,
                    source,
                )
                return PassRetentionJobResult(
                    status="skipped_lock",
                    total_backfilled=0,
                    total_deleted=0,
                    total_errors=0,
                    shelter_results=[],
                    message=message,
                    skipped=True,
                )

            run_key = start_job_run(
                job_name=PASS_RETENTION_JOB_NAME,
                job_label=PASS_RETENTION_JOB_LABEL,
                metadata={
                    "shelters": list(SHELTERS),
                    "schedule": PASS_RETENTION_SCHEDULE_LABEL,
                    "lock_key": PASS_RETENTION_LOCK_KEY,
                    "source": source,
                },
            )

            try:
                cycle_started_at = datetime.now(CHICAGO_TZ)
                app.extensions["pass_retention_scheduler_last_started_at"] = cycle_started_at.isoformat(
                    timespec="seconds"
                )
                app.logger.info(
                    "pass retention cleanup cycle started at %s source=%s",
                    cycle_started_at.isoformat(timespec="seconds"),
                    source,
                )

                total_backfilled = 0
                total_deleted = 0
                total_errors = 0
                shelter_results: list[dict[str, object]] = []

                for shelter in SHELTERS:
                    try:
                        result = run_pass_retention_cleanup_for_shelter(shelter)
                        backfilled = int(result.get("backfilled", 0))
                        deleted = int(result.get("deleted", 0))

                        total_backfilled += backfilled
                        total_deleted += deleted
                        shelter_results.append(
                            {
                                "shelter": shelter,
                                "status": "success",
                                "backfilled": backfilled,
                                "deleted": deleted,
                            }
                        )

                        app.logger.info(
                            "pass retention cleanup shelter=%s backfilled=%s deleted=%s source=%s",
                            shelter,
                            backfilled,
                            deleted,
                            source,
                        )
                    except Exception as err:
                        total_errors += 1
                        shelter_results.append(
                            {
                                "shelter": shelter,
                                "status": "error",
                                "error": str(err),
                            }
                        )
                        app.logger.exception(
                            "pass retention cleanup failed for shelter=%s source=%s",
                            shelter,
                            source,
                        )
                        safe_log_sh_event(
                            event_type="pass_retention_cleanup",
                            event_status="error",
                            event_source="pass_retention_job",
                            shelter=shelter,
                            message=f"Pass cleanup failed for {shelter}.",
                            metadata={"error": str(err), "source": source},
                        )
                        create_system_alert(
                            alert_type="scheduled_job",
                            severity="error",
                            title=f"Pass cleanup failed for {shelter}",
                            message="The scheduled pass cleanup job failed for one shelter.",
                            source_module="pass_retention_job",
                            alert_key=f"pass_retention_cleanup:{shelter}:failed",
                            metadata=str(err),
                        )

                cycle_finished_at = datetime.now(CHICAGO_TZ)
                finished_at = cycle_finished_at.isoformat(timespec="seconds")
                app.extensions["pass_retention_scheduler_last_finished_at"] = finished_at
                app.extensions["pass_retention_scheduler_last_result"] = {
                    "finished_at": finished_at,
                    "total_backfilled": total_backfilled,
                    "total_deleted": total_deleted,
                    "total_errors": total_errors,
                }

                if total_errors:
                    status = "error"
                    message = (
                        f"Pass cleanup completed with {total_errors} shelter error(s). "
                        f"Backfilled {total_backfilled}; deleted {total_deleted}."
                    )
                    fail_job_run(
                        run_key=run_key,
                        error_message=message,
                        metadata={
                            "total_backfilled": total_backfilled,
                            "total_deleted": total_deleted,
                            "total_errors": total_errors,
                            "shelter_results": shelter_results,
                            "lock_key": PASS_RETENTION_LOCK_KEY,
                            "source": source,
                        },
                    )
                else:
                    status = "success"
                    message = (
                        f"Pass cleanup completed successfully. "
                        f"Backfilled {total_backfilled}; deleted {total_deleted}."
                    )
                    finish_job_run(
                        run_key=run_key,
                        result_summary=message,
                        metadata={
                            "total_backfilled": total_backfilled,
                            "total_deleted": total_deleted,
                            "total_errors": total_errors,
                            "shelter_results": shelter_results,
                            "lock_key": PASS_RETENTION_LOCK_KEY,
                            "source": source,
                        },
                    )

                safe_log_sh_event(
                    event_type="pass_retention_cleanup",
                    event_status=status,
                    event_source="pass_retention_job",
                    message=message,
                    metadata={
                        "total_backfilled": total_backfilled,
                        "total_deleted": total_deleted,
                        "total_errors": total_errors,
                        "source": source,
                    },
                )

                app.logger.info(
                    "pass retention cleanup cycle finished at %s total_backfilled=%s total_deleted=%s total_errors=%s source=%s",
                    finished_at,
                    total_backfilled,
                    total_deleted,
                    total_errors,
                    source,
                )
                return PassRetentionJobResult(
                    status=status,
                    total_backfilled=total_backfilled,
                    total_deleted=total_deleted,
                    total_errors=total_errors,
                    shelter_results=shelter_results,
                    message=message,
                )
            except Exception as err:
                app.logger.exception("pass retention cleanup cycle failed source=%s", source)
                fail_job_run(
                    run_key=run_key,
                    error_message=str(err),
                    metadata={
                        "phase": "cleanup_cycle",
                        "lock_key": PASS_RETENTION_LOCK_KEY,
                        "source": source,
                    },
                )
                raise
