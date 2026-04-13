from __future__ import annotations

from typing import Any

from routes.case_management_parts.recovery_snapshot_formatters import days_since, parse_dateish


def normalize_level_start_date(resident: dict, enrollment_baseline: dict) -> Any:
    return resident.get("level_start_date") or enrollment_baseline.get("entry_date")


def normalize_sobriety_date(resident: dict, enrollment_baseline: dict) -> Any:
    return (
        resident.get("sobriety_date")
        or enrollment_baseline.get("intake_sobriety_date")
        or enrollment_baseline.get("entry_date")
    )


def normalize_treatment_graduation_date(resident: dict, enrollment_baseline: dict) -> Any:
    return resident.get("treatment_graduation_date") or enrollment_baseline.get(
        "intake_treatment_grad_date"
    )


def employment_gap_days(current_job_start_date: Any, previous_job_end_date: Any):
    current_dt = parse_dateish(current_job_start_date)
    previous_dt = parse_dateish(previous_job_end_date)

    if not current_dt or not previous_dt:
        return None

    gap = (current_dt - previous_dt).days
    if gap < 0:
        gap = 0
    return gap


def count_writeups_last_30_days(writeup_rows) -> int:
    total = 0

    for row in writeup_rows or []:
        days_since_incident = days_since(row.get("incident_date"))
        if days_since_incident is not None and days_since_incident <= 30:
            total += 1

    return total
