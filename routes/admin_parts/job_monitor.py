from __future__ import annotations

import json
from typing import Any

from flask import flash, redirect, render_template, url_for

from core.admin_rbac import require_admin_role
from core.scheduler_job_history import load_recent_job_runs


def _parse_metadata(value: Any) -> dict[str, Any]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except Exception:
        return {"raw": raw_value}

    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _summarize_job_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    total = len(rows)
    running = sum(1 for row in rows if str(row.get("status") or "") == "running")
    success = sum(1 for row in rows if str(row.get("status") or "") == "success")
    error = sum(1 for row in rows if str(row.get("status") or "") == "error")

    return {
        "total": total,
        "running": running,
        "success": success,
        "error": error,
    }


def job_monitor_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    rows = load_recent_job_runs(limit=100)
    for row in rows:
        row["metadata_parsed"] = _parse_metadata(row.get("metadata"))

    return render_template(
        "job_monitor.html",
        title="Background Job Monitor",
        rows=rows,
        summary=_summarize_job_rows(rows),
    )
