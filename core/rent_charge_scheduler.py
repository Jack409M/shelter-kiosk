from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from core.rent_charge_job import run_monthly_rent_charge_job

CHICAGO_TZ = ZoneInfo("America/Chicago")
TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _emit_status(app, message: str) -> None:
    print(f"RENT_CHARGE_SCHEDULER: {message}", flush=True)
    app.logger.warning("RENT_CHARGE_SCHEDULER: %s", message)


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

            if now.day in {1, 2, 3} and run_key != last_run_key:
                _emit_status(
                    app,
                    f"running monthly rent check year={now.year} month={now.month} day={now.day}",
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
            print("RENT_CHARGE_SCHEDULER: loop failure", flush=True)

        time.sleep(60)


def start_rent_charge_scheduler(app) -> None:
    if app.config.get("TESTING"):
        app.extensions["rent_charge_scheduler_status"] = "testing_skipped"
        _emit_status(app, "skipped in testing")
        return

    if _scheduler_disabled_by_env():
        app.extensions["rent_charge_scheduler_status"] = "disabled"
        _emit_status(app, "disabled by DISABLE_RENT_CHARGE_SCHEDULER")
        return

    if os.environ.get("RUN_MAIN") == "true":
        app.extensions["rent_charge_scheduler_status"] = "werkzeug_reloader_skipped"
        _emit_status(app, "skipped for Werkzeug reloader child")
        return

    if app.extensions.get("rent_charge_scheduler_started"):
        _emit_status(app, "already started")
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
    _emit_status(app, "started schedule=days 1-3 monthly Chicago time")
