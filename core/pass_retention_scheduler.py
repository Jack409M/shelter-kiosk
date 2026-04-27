from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.sh_events import safe_log_sh_event
from core.system_alerts import create_system_alert

CHICAGO_TZ = ZoneInfo("America/Chicago")
RUN_SLOTS = {(6, 0), (15, 0), (23, 0)}
SHELTERS = ("abba", "haven", "gratitude")
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
FALSY_ENV_VALUES = {"0", "false", "no", "off"}


def _env_value(name: str) -> str:
    return (os.environ.get(name) or "").strip().lower()


def _scheduler_disabled_by_env() -> bool:
    return _env_value("SCHEDULER_ENABLED") in FALSY_ENV_VALUES


def _run_cleanup_cycle(app) -> None:
    with app.app_context():
        cycle_started_at = datetime.now(CHICAGO_TZ)
        app.extensions["pass_retention_scheduler_last_started_at"] = cycle_started_at.isoformat(
            timespec="seconds"
        )
        app.logger.info(
            "pass retention cleanup cycle started at %s",
            cycle_started_at.isoformat(timespec="seconds"),
        )

        total_backfilled = 0
        total_deleted = 0
        total_errors = 0

        for shelter in SHELTERS:
            try:
                result = run_pass_retention_cleanup_for_shelter(shelter)
                backfilled = int(result.get("backfilled", 0))
                deleted = int(result.get("deleted", 0))

                total_backfilled += backfilled
                total_deleted += deleted

                app.logger.info(
                    "pass retention cleanup shelter=%s backfilled=%s deleted=%s",
                    shelter,
                    backfilled,
                    deleted,
                )
            except Exception as err:
                total_errors += 1
                app.logger.exception(
                    "pass retention cleanup failed for shelter=%s",
                    shelter,
                )
                safe_log_sh_event(
                    event_type="pass_retention_cleanup",
                    event_status="error",
                    event_source="pass_retention_scheduler",
                    shelter=shelter,
                    message=f"Pass cleanup failed for {shelter}.",
                    metadata={"error": str(err)},
                )
                create_system_alert(
                    alert_type="scheduled_job",
                    severity="error",
                    title=f"Pass cleanup failed for {shelter}",
                    message="The scheduled pass cleanup job failed for one shelter.",
                    source_module="pass_retention_scheduler",
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
        else:
            status = "success"
            message = (
                f"Pass cleanup completed successfully. "
                f"Backfilled {total_backfilled}; deleted {total_deleted}."
            )

        safe_log_sh_event(
            event_type="pass_retention_cleanup",
            event_status=status,
            event_source="pass_retention_scheduler",
            message=message,
            metadata={
                "total_backfilled": total_backfilled,
                "total_deleted": total_deleted,
                "total_errors": total_errors,
            },
        )

        app.logger.info(
            "pass retention cleanup cycle finished at %s total_backfilled=%s total_deleted=%s total_errors=%s",
            finished_at,
            total_backfilled,
            total_deleted,
            total_errors,
        )


def _scheduler_loop(app) -> None:
    last_run_key: tuple[int, int, int] | None = None

    while True:
        try:
            now = datetime.now(CHICAGO_TZ)
            run_key = (now.year, now.timetuple().tm_yday, now.hour)
            app.extensions["pass_retention_scheduler_last_seen_at"] = now.isoformat(
                timespec="seconds"
            )

            if (now.hour, now.minute) in RUN_SLOTS and run_key != last_run_key:
                _run_cleanup_cycle(app)
                last_run_key = run_key
        except Exception as err:
            app.logger.exception("pass retention scheduler loop failure")
            with app.app_context():
                safe_log_sh_event(
                    event_type="pass_retention_scheduler",
                    event_status="error",
                    event_source="pass_retention_scheduler",
                    message="Pass retention scheduler loop failed.",
                    metadata={"error": str(err)},
                )
                create_system_alert(
                    alert_type="scheduled_job",
                    severity="critical",
                    title="Pass cleanup scheduler failed",
                    message="The pass retention scheduler loop failed.",
                    source_module="pass_retention_scheduler",
                    alert_key="pass_retention_scheduler:loop_failed",
                    metadata=str(err),
                )

        time.sleep(30)


def start_pass_retention_scheduler(app) -> None:
    if app.config.get("TESTING"):
        app.extensions["pass_retention_scheduler_status"] = "testing_skipped"
        app.logger.info("pass retention scheduler skipped in testing")
        return

    if _scheduler_disabled_by_env():
        app.extensions["pass_retention_scheduler_status"] = "disabled"
        app.logger.info("pass retention scheduler disabled by SCHEDULER_ENABLED")
        return

    if os.environ.get("RUN_MAIN") == "true":
        return

    if app.extensions.get("pass_retention_scheduler_started"):
        return

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        daemon=True,
        name="pass-retention-scheduler",
    )
    thread.start()

    app.extensions["pass_retention_scheduler_started"] = True
    app.extensions["pass_retention_scheduler_status"] = "running"
    app.extensions["pass_retention_scheduler_schedule"] = "6:00 AM, 3:00 PM, and 11:00 PM Chicago time"
    app.logger.info("pass retention scheduler started")
