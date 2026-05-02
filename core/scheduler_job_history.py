from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any

from flask import current_app

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


def _now_iso() -> str:
    return utcnow_iso()


def start_job_run(*, job_name: str, job_label: str = "", metadata: dict[str, Any] | None = None) -> str:
    run_key = str(uuid.uuid4())
    now = _now_iso()

    db_execute(
        """
        INSERT INTO scheduler_job_runs (
            run_key,
            job_name,
            job_label,
            status,
            started_at,
            metadata,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            run_key,
            job_name,
            job_label,
            "running",
            now,
            json.dumps(metadata or {}),
            now,
            now,
        ),
    )

    return run_key


def finish_job_run(*, run_key: str, result_summary: str = "", metadata: dict[str, Any] | None = None) -> None:
    now = _now_iso()

    row = db_fetchone(
        "SELECT started_at FROM scheduler_job_runs WHERE run_key = %s LIMIT 1",
        (run_key,),
    )

    duration_ms = None
    if row and row.get("started_at"):
        try:
            started = datetime.fromisoformat(str(row.get("started_at")).replace("Z", "+00:00"))
            finished = datetime.fromisoformat(now.replace("Z", "+00:00"))
            duration_ms = int((finished - started).total_seconds() * 1000)
        except Exception:
            duration_ms = None

    db_execute(
        """
        UPDATE scheduler_job_runs
        SET status = %s,
            finished_at = %s,
            duration_ms = %s,
            result_summary = %s,
            metadata = %s,
            updated_at = %s
        WHERE run_key = %s
        """,
        (
            "success",
            now,
            duration_ms,
            str(result_summary or ""),
            json.dumps(metadata or {}),
            now,
            run_key,
        ),
    )


def fail_job_run(*, run_key: str, error_message: str = "", metadata: dict[str, Any] | None = None) -> None:
    now = _now_iso()

    db_execute(
        """
        UPDATE scheduler_job_runs
        SET status = %s,
            finished_at = %s,
            error_message = %s,
            metadata = %s,
            updated_at = %s
        WHERE run_key = %s
        """,
        (
            "error",
            now,
            str(error_message or ""),
            json.dumps(metadata or {}),
            now,
            run_key,
        ),
    )


def load_recent_job_runs(limit: int = 25) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 25), 100))
    return db_fetchall(
        """
        SELECT
            id,
            run_key,
            job_name,
            job_label,
            status,
            started_at,
            finished_at,
            duration_ms,
            result_summary,
            error_message,
            metadata,
            created_at,
            updated_at
        FROM scheduler_job_runs
        ORDER BY id DESC
        LIMIT %s
        """,
        (safe_limit,),
    )


def load_latest_job_run(job_name: str) -> dict[str, Any] | None:
    return db_fetchone(
        """
        SELECT *
        FROM scheduler_job_runs
        WHERE job_name = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (job_name,),
    )
