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

            # Run during the first three days of the month to ensure catch up
            if now.day in {1, 2, 3} and run_key != last_run_key:
                run_monthly_rent_charge_job(app, source="rent_charge_scheduler")
                last_run_key = run_key
        except Exception:
            app.logger.exception("rent charge scheduler loop failure")

        time.sleep(60)


def start_rent_charge_scheduler(app) -> None:
    if app.config.get("TESTING"):
        return

    if _scheduler_disabled_by_env():
        app.logger.info("rent charge scheduler disabled by env")
        return

    if os.environ.get("RUN_MAIN") == "true":
        return

    if app.extensions.get("rent_charge_scheduler_started"):
        return

    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        daemon=True,
        name="rent-charge-scheduler",
    )
    thread.start()

    app.extensions["rent_charge_scheduler_started"] = True
    app.logger.info("rent charge scheduler started")
