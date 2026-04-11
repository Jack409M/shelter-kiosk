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
        cycle_started_at = datetime.now(CHICAGO_TZ)
        app.logger.info(
            "pass retention cleanup cycle started at %s",
            cycle_started_at.isoformat(timespec="seconds"),
        )

        total_backfilled = 0
        total_deleted = 0

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
            except Exception:
                app.logger.exception(
                    "pass retention cleanup failed for shelter=%s",
                    shelter,
                )

        cycle_finished_at = datetime.now(CHICAGO_TZ)
        app.logger.info(
            "pass retention cleanup cycle finished at %s total_backfilled=%s total_deleted=%s",
            cycle_finished_at.isoformat(timespec="seconds"),
            total_backfilled,
            total_deleted,
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
