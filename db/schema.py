"""
Database schema management helpers.
"""

from __future__ import annotations

from datetime import datetime

from flask import current_app, g

from core.db import db_execute, db_fetchall, db_fetchone, get_db


def _run_configured_init() -> None:
    """
    Run the initializer currently registered by the app.

    This remains available during the transition while schema logic
    is still being moved out of app.py.
    """
    init_func = current_app.config.get("INIT_DB_FUNC")
    if callable(init_func):
        init_func()
        return

    raise RuntimeError("Database initializer is not configured")


def _create(sqlite_sql: str, pg_sql: str, kind: str) -> None:
    """
    Execute the sqlite or postgres version of a schema statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)


def init_db() -> None:
    """
    Current public schema entry point.

    For now this still forwards to the configured initializer.
    Later this module will own the full database bootstrap logic.
    """
    _run_configured_init()
