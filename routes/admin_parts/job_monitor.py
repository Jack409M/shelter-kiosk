from __future__ import annotations

import json
from typing import Any

from flask import flash, redirect, render_template, request, url_for

from core.admin_rbac import require_admin_role
from core.scheduler_job_history import load_recent_job_runs

STATUS_OPTIONS = ("all", "success", "error", "running", "skipped_lock")


def _parse_metadata(value: Any) -> dict[str, Any]:
    raw_value = str(value or "").strip()
    if not raw_value:
        return {}

    try:
        parsed = json.loads(raw_value)
    except Exception:
        return {"raw": raw_value}

    return parsed if isinstance(parsed, dict) else {"value": parsed}


def _status_matches(row: dict[str, Any], status_filter: str) -> bool:
    if status_filter == "all":
        return True

    return str(row.get("status") or "").strip().lower() == status_filter


def _job_matches(row: dict[str, Any], job_filter: str) -> bool:
    if not job_filter:
        return True

    job_name = str(row.get("job_name") or "").strip().lower()
    job_label = str(row.get("job_label") or "").strip().lower()
    needle = job_filter.strip().lower()
    return needle in job_name or needle in job_label


def _metadata_summary(metadata: dict[str, Any]) -> str:
    parts: list[str] = []

    if "total_backfilled" in metadata:
        parts.append(f"Backfilled {metadata.get('total_backfilled', 0)}")

    if "total_deleted" in metadata:
        parts.append(f"Deleted {metadata.get('total_deleted', 0)}")

    if "total_errors" in metadata:
        parts.append(f"Errors {metadata.get('total_errors', 0)}")

    if metadata.get("reason") == "advisory_lock_not_acquired":
        parts.append("Skipped because another instance held the lock")

    if metadata.get("lock_key"):
        parts.append(f"Lock {metadata.get('lock_key')}")

    return " | ".join(parts)


def _summarize_job_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total": len(rows),
        "running": sum(1 for row in rows if str(row.get("status") or "") == "running"),
        "success": sum(1 for row in rows if str(row.get("status") or "") == "success"),
        "error": sum(1 for row in rows if str(row.get("status") or "") == "error"),
        "skipped_lock": sum(
            1 for row in rows if str(row.get("status") or "") == "skipped_lock"
        ),
    }


def _available_jobs(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    jobs: list[dict[str, str]] = []

    for row in rows:
        job_name = str(row.get("job_name") or "").strip()
        if not job_name or job_name in seen:
            continue

        seen.add(job_name)
        jobs.append(
            {
                "name": job_name,
                "label": str(row.get("job_label") or job_name).strip(),
            }
        )

    return jobs


def job_monitor_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    status_filter = str(request.args.get("status") or "all").strip().lower()
    if status_filter not in STATUS_OPTIONS:
        status_filter = "all"

    job_filter = str(request.args.get("job") or "").strip()

    all_rows = load_recent_job_runs(limit=100)
    for row in all_rows:
        metadata = _parse_metadata(row.get("metadata"))
        row["metadata_parsed"] = metadata
        row["metadata_summary"] = _metadata_summary(metadata)

    rows = [
        row
        for row in all_rows
        if _status_matches(row, status_filter) and _job_matches(row, job_filter)
    ]

    return render_template(
        "job_monitor.html",
        title="Background Job Monitor",
        rows=rows,
        summary=_summarize_job_rows(all_rows),
        filtered_summary=_summarize_job_rows(rows),
        status_options=STATUS_OPTIONS,
        selected_status=status_filter,
        selected_job=job_filter,
        available_jobs=_available_jobs(all_rows),
    )
