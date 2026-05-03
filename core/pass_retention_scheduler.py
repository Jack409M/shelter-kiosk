from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from core.pass_retention_job import run_pass_retention_job
from core.sh_events import safe_log_sh_event
from core.system_alerts import create_system_alert

CHICAGO_TZ = ZoneInfo("America/Chicago")
RUN_SLOTS = {(6, 0), (15, 0), (23, 0)}
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
FALSY_ENV_VALUES = {"0", "false", "no", "off"}


def _env_value(name: str) -> str:
    return (os.environ.get(name) or "").strip().lower()


def _scheduler_disabled_by_env() -> bool:
    explicit_value = _env_value("ENABLE_PASS_RETENTION_SCHEDULER")
    if explicit_value in FALSY_ENV_VALUES:
        return True

    legacy_value = _env_value("SCHEDULER_ENABLED")
    return legacy_value in FALSY_ENV_VALUES


def _run_cleanup_cycle(app) -> None:
    run_pass_retention_job(app, source="in_app_scheduler")


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
        app.logger.info("pass retention scheduler disabled by environment")
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
