from __future__ import annotations

from typing import Any

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.meeting_progress import calculate_meeting_progress
from core.promotion_readiness import build_promotion_readiness
from routes.case_management_parts.helpers import (
    fetch_current_enrollment_id_for_resident,
    normalize_shelter_name,
)
from routes.case_management_parts.recovery_snapshot_formatters import (
    bool_display,
    days_since,
    employment_status_display,
    employment_type_display,
    money_display,
)
from routes.case_management_parts.recovery_snapshot_loaders import (
    load_budget_rows,
    load_enrollment_baseline,
    load_inspection_rows,
    load_medications,
    load_resident_profile,
    load_ua_rows,
    load_writeup_rows,
)
from routes.case_management_parts.recovery_snapshot_metrics import (
    count_writeups_last_30_days,
    employment_gap_days,
    normalize_level_start_date,
    normalize_sobriety_date,
    normalize_treatment_graduation_date,
)


def load_recovery_snapshot(
    resident_id: int,
    enrollment_id: int | None,
) -> dict[str, Any]:
    resident = load_resident_profile(resident_id)
    resident_shelter = normalize_shelter_name(resident.get("shelter"))

    enrollment_id = enrollment_id or fetch_current_enrollment_id_for_resident(
        resident_id,
        shelter=resident_shelter or None,
    )

    enrollment_baseline = load_enrollment_baseline(enrollment_id)

    medications = load_medications(resident_id, enrollment_id)
    ua_rows = load_ua_rows(resident_id, enrollment_id)
    inspection_rows = load_inspection_rows(resident_id, enrollment_id)
    budget_rows = load_budget_rows(resident_id, enrollment_id)
    writeup_rows = load_writeup_rows(resident_id)

    level_start_date = normalize_level_start_date(resident, enrollment_baseline)
    sobriety_date = normalize_sobriety_date(resident, enrollment_baseline)
    treatment_graduation_date = normalize_treatment_graduation_date(resident, enrollment_baseline)

    meeting_progress = calculate_meeting_progress(
        resident_id=resident_id,
        shelter=str(resident.get("shelter") or ""),
        program_start_date=enrollment_baseline.get("entry_date"),
        level_value=resident.get("program_level"),
    )

    attendance_snapshot = calculate_prior_week_attendance_hours(
        resident_id=resident_id,
        shelter=str(resident.get("shelter") or ""),
    )

    writeups_last_30_days = count_writeups_last_30_days(writeup_rows)

    promotion_readiness = build_promotion_readiness(
        {
            **meeting_progress,
            "program_level": resident.get("program_level"),
            "days_on_level": days_since(level_start_date),
            "sponsor_active": resident.get("sponsor_active"),
            "step_work_active": resident.get("step_work_active"),
            "monthly_income": resident.get("monthly_income"),
            "rad_complete": enrollment_baseline.get("rad_complete"),
            "writeups_last_30_days": writeups_last_30_days,
            "no_writeups_last_30_days": writeups_last_30_days == 0,
            "work_hours_last_week": attendance_snapshot.get("work_hours"),
            "productive_hours_last_week": attendance_snapshot.get("productive_hours"),
            "work_required_hours": attendance_snapshot.get("work_required_hours"),
            "productive_required_hours": attendance_snapshot.get("productive_required_hours"),
            "meets_work_requirement": attendance_snapshot.get("meets_work_requirement"),
            "meets_productive_requirement": attendance_snapshot.get("meets_productive_requirement"),
            "passes_attendance_requirement": attendance_snapshot.get("passes_requirement"),
        }
    )

    return {
        "program_level": resident.get("program_level"),
        "level_start_date": level_start_date,
        "days_on_level": days_since(level_start_date),
        "sobriety_date": sobriety_date,
        "days_sober_today": days_since(sobriety_date),
        "treatment_graduation_date": treatment_graduation_date,
        "employment_status_display": employment_status_display(
            resident.get("employment_status_current")
        ),
        "employment_type_display": employment_type_display(resident.get("employment_type_current")),
        "monthly_income_display": money_display(resident.get("monthly_income")),
        "employment_gap_days": employment_gap_days(
            resident.get("current_job_start_date"),
            resident.get("previous_job_end_date"),
        ),
        "sponsor_active_display": bool_display(resident.get("sponsor_active")),
        "step_work_active_display": bool_display(resident.get("step_work_active")),
        "medications": medications,
        "ua_rows": ua_rows,
        "inspection_rows": inspection_rows,
        "budget_rows": budget_rows,
        "latest_writeup": writeup_rows[0] if writeup_rows else None,
        "writeups_last_30_days": writeups_last_30_days,
        "no_writeups_last_30_days": writeups_last_30_days == 0,
        "meeting_progress": meeting_progress,
        "promotion_readiness": promotion_readiness,
    }
