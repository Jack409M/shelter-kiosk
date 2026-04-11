from __future__ import annotations

import threading
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app

from core.pass_retention import run_pass_retention_cleanup_for_shelter

CHICAGO_TZ = ZoneInfo("America/Chicago")

RUN_HOURS = {6, 15, 23}  # 6am, 3pm, 11pm


def _run_cleanup_cycle(app):
    with app.app_context():
        try:
            shelters = app.config.get("ACTIVE_SHELTERS", [])
            for shelter in shelters:
                run_pass_retention_cleanup_for_shelter(shelter)
        except Exception as e:
            app.logger.error("pass retention cleanup failed", exc_info=e)


def _scheduler_loop(app):
    last_run_hour = None

    while True:
        try:
            now = datetime.now(CHICAGO_TZ)
            current_hour = now.hour

            if current_hour in RUN_HOURS and current_hour != last_run_hour:
                _run_cleanup_cycle(app)
                last_run_hour = current_hour

            # reset guard after hour passes
            if current_hour != last_run_hour:
                last_run_hour = None

        except Exception as e:
            app.logger.error("scheduler loop failure", exc_info=e)

        time.sleep(60)  # check once per minute


def start_pass_retention_scheduler(app):
    thread = threading.Thread(
        target=_scheduler_loop,
        args=(app,),
        daemon=True,
        name="pass-retention-scheduler",
    )
    thread.start()
