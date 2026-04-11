from __future__ import annotations

import os
import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from core.pass_retention import run_pass_retention_cleanup_for_shelter

CHICAGO_TZ = ZoneInfo("America/Chicago")
RUN_SLOTS = {(6, 0), (15, 0), (23, 0)}
SHELTERS = ("abba", "haven", "gratitude")


def _run_cleanup_cycle(app) -> None:
    with app.app_context():
        for shelter in SHELTERS:
            try:
                run_pass_retention_cleanup_for_shelter(shelter)
            except Exception:
                app.logger.exception(
                    "pass retention cleanup failed for shelter=%s",
                    shelter,
                )


def _scheduler_loop(app) -> None:
    last_run_key: tuple[int, int, int] | None = None

    while True:
        try:
            now = datetime.now(CHICAGO_TZ)
            run_key = (now.year, now.timetuple().tm_yday, now.hour)

            if (now.hour, now.minute) in RUN_SLOTS and run_key != last_run_key:
                _run_cleanup_cycle(app)
                last_run_key = run_key
        except Exception:
            app.logger.exception("pass retention scheduler loop failure")

        time.sleep(30)


def start_pass_retention_scheduler(app) -> None:
    if app.config.get("TESTING"):
        app.logger.info("pass retention scheduler skipped in testing")
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
    app.logger.info("pass retention scheduler started")
