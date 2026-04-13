from __future__ import annotations

from core.meeting_progress import calculate_meeting_progress
from core.promotion_readiness import build_promotion_readiness
from routes.case_management_parts.helpers import fetch_current_enrollment_id_for_resident
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
from routes.case_management_parts.recovery_snapshot_mappers import (
    budget_items,
    inspection_items,
    medication_items,
    ua_items,
)
from routes.case_management_parts.recovery_snapshot_metrics import (
    count_writeups_last_30_days,
    employment_gap_days,
    normalize_level_start_date,
    normalize_sobriety_date,
    normalize_treatment_graduation_date,
)


def load_recovery_snapshot(resident_id: int, enrollment_id: int | None):
    current_enrollment_id = enrollment_id or fetch_current_enrollment_id_for_resident(resident_id)

    resident = load_resident_profile(resident_id)
    enrollment_baseline = load_enrollment_baseline(current_enrollment_id)

    level_start_date = normalize_level_start_date(resident, enrollment_baseline)
    sobriety_date = normalize_sobriety_date(resident, enrollment_baseline)
    treatment_graduation_date = normalize_treatment_graduation_date(resident, enrollment_baseline)

    step_changed_at = resident.get("step_changed_at")
    employment_updated_at = resident.get("employment_updated_at")
    current_job_start_date = resident.get("current_job_start_date")
    continuous_employment_start_date = resident.get("continuous_employment_start_date")
    previous_job_end_date = resident.get("previous_job_end_date")

    medications_raw = load_medications(resident_id, current_enrollment_id)
    ua_rows_raw = load_ua_rows(resident_id, current_enrollment_id)
    inspection_rows_raw = load_inspection_rows(resident_id, current_enrollment_id)
    budget_rows_raw = load_budget_rows(resident_id, current_enrollment_id)
    writeup_rows_raw = load_writeup_rows(resident_id)

    medication_items_list = medication_items(medications_raw)
    ua_items_list = ua_items(ua_rows_raw)
    inspection_items_list = inspection_items(inspection_rows_raw)
    budget_items_list = budget_items(budget_rows_raw)

    writeups_last_30_days = count_writeups_last_30_days(writeup_rows_raw)
    latest_writeup = writeup_rows_raw[0] if writeup_rows_raw else None

    meeting_progress = calculate_meeting_progress(
        resident_id=resident_id,
        shelter=resident.get("shelter") or "",
        program_start_date=enrollment_baseline.get("entry_date"),
        level_value=resident.get("program_level"),
    )

    promotion_readiness = build_promotion_readiness(
        {
            **meeting_progress,
            "program_level": resident.get("program_level"),
            "days_on_level": days_since(level_start_date),
            "sponsor_active": resident.get("sponsor_active"),
            "step_work_active": resident.get("step_work_active"),
            "monthly_income": resident.get("monthly_income"),
            "rad_complete": resident.get("rad_completed"),
            "writeups_last_30_days": writeups_last_30_days,
            "no_writeups_last_30_days": writeups_last_30_days == 0,
        }
    )

    return {
        "program_level": resident.get("program_level") or "1",
        "level_start_date": level_start_date,
        "days_on_level": days_since(level_start_date),
        "sponsor_name": resident.get("sponsor_name"),
        "sponsor_active": resident.get("sponsor_active"),
        "sponsor_active_display": bool_display(resident.get("sponsor_active")),
        "employer_name": resident.get("employer_name"),
        "employment_status_current": resident.get("employment_status_current"),
        "employment_status_display": employment_status_display(
            resident.get("employment_status_current")
        ),
        "employment_type_current": resident.get("employment_type_current"),
        "employment_type_display": employment_type_display(resident.get("employment_type_current")),
        "supervisor_name": resident.get("supervisor_name"),
        "supervisor_phone": resident.get("supervisor_phone"),
        "unemployment_reason": resident.get("unemployment_reason"),
        "employment_notes": resident.get("employment_notes"),
        "monthly_income": resident.get("monthly_income"),
        "monthly_income_display": money_display(resident.get("monthly_income")),
        "current_job_start_date": current_job_start_date,
        "current_job_days": days_since(current_job_start_date),
        "continuous_employment_start_date": continuous_employment_start_date,
        "continuous_employment_days": days_since(continuous_employment_start_date),
        "previous_job_end_date": previous_job_end_date,
        "employment_gap_days": employment_gap_days(current_job_start_date, previous_job_end_date),
        "upward_job_change": resident.get("upward_job_change"),
        "upward_job_change_display": bool_display(resident.get("upward_job_change")),
        "job_change_notes": resident.get("job_change_notes"),
        "employment_updated_at": employment_updated_at,
        "employment_days": days_since(employment_updated_at),
        "step_current": resident.get("step_current"),
        "step_work_active": resident.get("step_work_active"),
        "step_work_active_display": bool_display(resident.get("step_work_active")),
        "step_changed_at": step_changed_at,
        "step_days": days_since(step_changed_at),
        "sobriety_date": sobriety_date,
        "days_sober_today": days_since(sobriety_date),
        "days_sober_at_entry": None,
        "drug_of_choice": resident.get("drug_of_choice"),
        "treatment_graduation_date": treatment_graduation_date,
        "rad_classes_attended": resident.get("rad_classes_attended") or 0,
        "rad_completed": resident.get("rad_completed"),
        "rad_completed_display": bool_display(resident.get("rad_completed")),
        "rad_completed_at": resident.get("rad_completed_at"),
        "medications": medication_items_list,
        "medication_count": len(medication_items_list),
        "ua_rows": ua_items_list,
        "inspection_rows": inspection_items_list,
        "budget_rows": budget_items_list,
        "latest_ua": ua_items_list[0] if ua_items_list else None,
        "latest_inspection": inspection_items_list[0] if inspection_items_list else None,
        "latest_budget_session": budget_items_list[0] if budget_items_list else None,
        "latest_writeup": latest_writeup,
        "writeups_last_30_days": writeups_last_30_days,
        "no_writeups_last_30_days": writeups_last_30_days == 0,
        "meeting_progress": meeting_progress,
        "total_meetings": meeting_progress.get("total_meetings", 0),
        "meetings_this_week": meeting_progress.get("meetings_this_week", 0),
        "meetings_last_30_days": meeting_progress.get("meetings_last_30_days", 0),
        "meetings_last_90_days": meeting_progress.get("meetings_last_90_days", 0),
        "days_in_program": meeting_progress.get("days_in_program", 0),
        "expected_meetings_so_far": meeting_progress.get("expected_meetings_so_far", 0),
        "pace_percent": meeting_progress.get("pace_percent", 0.0),
        "pace_percent_display": meeting_progress.get("pace_percent_display", "0.0%"),
        "projected_90_day_total": meeting_progress.get("projected_90_day_total", 0),
        "meetings_remaining_to_90": meeting_progress.get("meetings_remaining_to_90", 0),
        "completed_90_in_90": meeting_progress.get("completed_90_in_90", False),
        "completed_116_meetings": meeting_progress.get("completed_116_meetings", False),
        "completed_168_meetings": meeting_progress.get("completed_168_meetings", False),
        "required_weekly_meetings": meeting_progress.get("required_weekly_meetings"),
        "weekly_requirement_met": meeting_progress.get("weekly_requirement_met"),
        "meeting_status_label": meeting_progress.get("status_label", "Not Started"),
        "meeting_weekly_rows": meeting_progress.get("weekly_rows", []),
        "has_meeting_data": meeting_progress.get("has_meeting_data", False),
        "promotion_readiness": promotion_readiness,
    }
