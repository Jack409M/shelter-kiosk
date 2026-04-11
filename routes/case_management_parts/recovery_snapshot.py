from __future__ import annotations

from datetime import date
from typing import Any

from core.db import db_fetchone
from routes.case_management_parts.helpers import placeholder
from routes.inspection_v2 import build_inspection_stability_snapshot


def _safe_days_between(start_date: str | None, end_date: date | None) -> int | None:
    if not start_date or not end_date:
        return None

    try:
        parsed = date.fromisoformat(str(start_date)[:10])
    except Exception:
        return None

    delta = (end_date - parsed).days
    return max(delta, 0)


def _load_recovery_row(resident_id: int):
    ph = placeholder()

    return db_fetchone(
        f"""
        SELECT
            program_level,
            level_start_date,
            step_current,
            sponsor_name,
            sponsor_active,
            step_work_active,
            sobriety_date,
            treatment_graduation_date,
            drug_of_choice,
            employment_status_current,
            employment_type_current,
            monthly_income,
            current_job_start_date,
            continuous_employment_start_date,
            previous_job_end_date,
            upward_job_change
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    )


def _build_employment_metrics(row: dict[str, Any], today: date) -> dict:
    return {
        "current_job_days": _safe_days_between(
            row.get("current_job_start_date"), today
        ),
        "continuous_employment_days": _safe_days_between(
            row.get("continuous_employment_start_date"), today
        ),
        "employment_gap_days": _safe_days_between(
            row.get("previous_job_end_date"), today
        ),
    }


def _build_sobriety_metrics(row: dict[str, Any], today: date) -> dict:
    return {
        "days_sober_today": _safe_days_between(
            row.get("sobriety_date"), today
        )
    }


def _build_level_metrics(row: dict[str, Any], today: date) -> dict:
    return {
        "days_on_level": _safe_days_between(
            row.get("level_start_date"), today
        )
    }


def _load_inspection_snapshot(resident_id: int) -> dict | None:
    try:
        snapshot = build_inspection_stability_snapshot(resident_id)
        return snapshot
    except Exception:
        # Fail SAFE — never break case management over inspections
        return None


def load_recovery_snapshot(resident_id: int, enrollment_id: int | None = None) -> dict:
    row = _load_recovery_row(resident_id) or {}
    today = date.today()

    snapshot = {
        "program_level": row.get("program_level"),
        "level_start_date": row.get("level_start_date"),
        "step_current": row.get("step_current"),
        "sponsor_name": row.get("sponsor_name"),
        "sponsor_active": row.get("sponsor_active"),
        "step_work_active": row.get("step_work_active"),
        "sobriety_date": row.get("sobriety_date"),
        "treatment_graduation_date": row.get("treatment_graduation_date"),
        "drug_of_choice": row.get("drug_of_choice"),
        "employment_status_current": row.get("employment_status_current"),
        "employment_type_current": row.get("employment_type_current"),
        "monthly_income": row.get("monthly_income"),
        "current_job_start_date": row.get("current_job_start_date"),
        "continuous_employment_start_date": row.get("continuous_employment_start_date"),
        "previous_job_end_date": row.get("previous_job_end_date"),
        "upward_job_change": row.get("upward_job_change"),
    }

    # Derived metrics
    snapshot.update(_build_employment_metrics(row, today))
    snapshot.update(_build_sobriety_metrics(row, today))
    snapshot.update(_build_level_metrics(row, today))

    # SAFE integration with inspection system
    inspection_snapshot = _load_inspection_snapshot(resident_id)
    if inspection_snapshot:
        snapshot["latest_inspection"] = inspection_snapshot

    return snapshot
