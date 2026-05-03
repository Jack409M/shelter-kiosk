from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from core.rent_charge_job import run_monthly_rent_charge_job

CHICAGO_TZ = ZoneInfo("America/Chicago")
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _env_value(name: str) -> str:
    return (os.environ.get(name) or "").strip().lower()


def _scheduler_disabled_by_env() -> bool:
    return _env_value("DISABLE_RENT_CHARGE_SCHEDULER") in TRUTHY_ENV_VALUES


def _scheduler_loop(app) -> None:
    last_run_key: tuple[int, int] | None = None

    while True:
        try:
            now = datetime.now(CHICAGO_TZ)
            run_key = (now.year, now.month)
            app.extensions["rent_charge_scheduler_last_seen_at"] = now.isoformat(
                timespec="seconds"
            )
            app.extensions["rent_charge_scheduler_status"] = "running"
            app.extensions["rent_charge_scheduler_schedule"] = (
                "Runs once per month during days 1 through 3 in Chicago time."
            )

            # Run during the first three days of the month to ensure catch up.
            if now.day in {1, 2, 3} and run_key != last_run_key:
                app.logger.info(
                    "rent charge scheduler running monthly rent check year=%s month=%s day=%s",
                    now.year,
                    now.month,
                    now.day,
                )
                run_monthly_rent_charge_job(app, source="rent_charge_scheduler")
                app.extensions["rent_charge_scheduler_last_run_at"] = now.isoformat(
                    timespec="seconds"
                )
                app.extensions["rent_charge_scheduler_last_run_key"] = f"{now.year:04d}-{now.month:02d}"
                last_run_key = run_key
        except Exception:
            app.extensions["rent_charge_scheduler_status"] = "error"
            app.logger.exception("rent charge scheduler loop failure")

        time.sleep(60)


def start_rent_charge_scheduler(app) -> None:
    if app.config.get("TESTING"):
        app.extensions["rent_charge_scheduler_status"] = "testing_skipped"
        app.logger.info("rent charge scheduler skipped in testing")
        return

    if _scheduler_disabled_by_env():
        app.extensions["rent_charge_scheduler_status"] = "disabled"
        app.logger.info("rent charge scheduler disabled by DISABLE_RENT_CHARGE_SCHEDULER")
        return

    if os.environ.get("RUN_MAIN") == "true":
        app.extensions["rent_charge_scheduler_status"] = "werkzeug_reloader_skipped"
        app.logger.info("rent charge scheduler skipped for Werkzeug reloader child")
        return

    if app.extensions.get("rent_charge_scheduler_started"):
        app.logger.info("rent charge scheduler already started")
        return

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        daemon=True,
        name="rent-charge-scheduler",
    )
    thread.start()

    app.extensions["rent_charge_scheduler_started"] = True
    app.extensions["rent_charge_scheduler_status"] = "running"
    app.extensions["rent_charge_scheduler_schedule"] = (
        "Runs once per month during days 1 through 3 in Chicago time."
    )
    app.logger.info(
        "rent charge scheduler started schedule='days 1-3 monthly, Chicago time'"
    )
