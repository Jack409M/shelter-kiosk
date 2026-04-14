from __future__ import annotations

from typing import Any

from routes.case_management_parts.recovery_snapshot_formatters import days_since
from routes.case_management_parts.recovery_snapshot_formatters import parse_dateish


def _first_present(*values):
    for value in values:
        if value:
            return value
    return None


def normalize_level_start_date(resident: dict, enrollment_baseline: dict) -> Any:
    return _first_present(
        resident.get("level_start_date"),
        enrollment_baseline.get("entry_date"),
    )


def normalize_sobriety_date(resident: dict, enrollment_baseline: dict) -> Any:
    return _first_present(
        resident.get("sobriety_date"),
        enrollment_baseline.get("intake_sobriety_date"),
        enrollment_baseline.get("entry_date"),
    )


def normalize_treatment_graduation_date(resident: dict, enrollment_baseline: dict) -> Any:
    return _first_present(
        resident.get("treatment_graduation_date"),
        enrollment_baseline.get("intake_treatment_grad_date"),
    )


def employment_gap_days(current_job_start_date: Any, previous_job_end_date: Any):
    current_dt = parse_dateish(current_job_start_date)
    previous_dt = parse_dateish(previous_job_end_date)

    if not current_dt or not previous_dt:
        return None

    return max((current_dt - previous_dt).days, 0)


def count_writeups_last_30_days(writeup_rows) -> int:
    total = 0

    for row in writeup_rows or []:
        incident_days = days_since(row.get("incident_date"))
        if incident_days is not None and incident_days <= 30:
            total += 1

    return total
