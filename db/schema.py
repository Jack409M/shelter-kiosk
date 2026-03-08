"""
Database schema management.

This module will eventually contain the full schema creation
and migration logic for the application. The goal is to keep
database structure separate from the Flask application boot code.

Right now the real schema initializer still lives in app.py.
This module simply exposes a clean entry point that the app
can call until the migration is completed.
"""

from __future__ import annotations

from datetime import datetime
from flask import current_app


def init_db() -> None:
    """
    Entry point used by the application to initialize the database.

    For now this forwards to the initializer defined in app.py.
    Later the full schema logic will live here instead.
    """

    # Pull the initializer function from app configuration.
    # This avoids importing app directly and prevents circular imports.
    init_func = current_app.config.get("INIT_DB_FUNC")

    if callable(init_func):
        init_func()
        return

    raise RuntimeError("Database initializer is not configured")
