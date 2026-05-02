"""
Scheduler schema.

This module stores durable scheduler job run history so operational pages can
show what ran, when it ran, whether it succeeded, and why it failed even after
an application restart.
"""

from __future__ import annotations

from flask import current_app

from core.db import db_execute

from .schema_helpers import create_table, safe_add_column


def ensure_scheduler_job_runs_table(kind: str) -> None:
    create_table(
        kind,
        """
        CREATE TABLE IF NOT EXISTS scheduler_job_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_key TEXT NOT NULL,
            job_name TEXT NOT NULL,
            job_label TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_ms INTEGER,
            result_summary TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scheduler_job_runs (
            id SERIAL PRIMARY KEY,
            run_key TEXT NOT NULL,
            job_name TEXT NOT NULL,
            job_label TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            started_at TEXT NOT NULL,
            finished_at TEXT,
            duration_ms INTEGER,
            result_summary TEXT NOT NULL DEFAULT '',
            error_message TEXT NOT NULL DEFAULT '',
            metadata TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """,
    )

    safe_add_column(kind, "scheduler_job_runs", "job_label TEXT NOT NULL DEFAULT ''")
    safe_add_column(kind, "scheduler_job_runs", "duration_ms INTEGER")
    safe_add_column(kind, "scheduler_job_runs", "result_summary TEXT NOT NULL DEFAULT ''")
    safe_add_column(kind, "scheduler_job_runs", "error_message TEXT NOT NULL DEFAULT ''")
    safe_add_column(kind, "scheduler_job_runs", "metadata TEXT NOT NULL DEFAULT ''")


def ensure_tables(kind: str) -> None:
    ensure_scheduler_job_runs_table(kind)


def ensure_indexes() -> None:
    try:
        db_execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS scheduler_job_runs_run_key_uidx
            ON scheduler_job_runs (run_key)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create scheduler job run key index.")

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS scheduler_job_runs_job_started_idx
            ON scheduler_job_runs (job_name, started_at)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create scheduler job run job index.")

    try:
        db_execute(
            """
            CREATE INDEX IF NOT EXISTS scheduler_job_runs_status_started_idx
            ON scheduler_job_runs (status, started_at)
            """
        )
    except Exception:
        current_app.logger.exception("Failed to create scheduler job run status index.")
