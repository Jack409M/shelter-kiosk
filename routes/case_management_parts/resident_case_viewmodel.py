from __future__ import annotations

from datetime import date


def safe_days_since(date_text: str | None):
    if not date_text:
        return None

    try:
        parsed = date.fromisoformat(str(date_text)[:10])
    except Exception:
        return None

    days = (date.today() - parsed).days
    if days < 0:
        return 0
    return days


def build_meeting_defaults():
    return {
        "meeting_date": date.today().isoformat(),
        "notes": "",
        "progress_notes": "",
        "setbacks_or_incidents": "",
        "action_items": "",
        "next_appointment": "",
        "overall_summary": "",
        "ready_for_next_level": "",
        "recommended_next_level": "",
        "blocker_reason": "",
        "override_or_exception": "",
        "staff_review_note": "",
        "updated_grit": None,
        "parenting_class_completed": "",
        "warrants_or_fines_paid": "",
    }


def build_workspace_header(*, resident, enrollment, recovery_snapshot, open_needs):
    rs = recovery_snapshot or {}

    sobriety_date = rs.get("sobriety_date")
    days_sober = rs.get("days_sober_today")
    if days_sober is None:
        days_sober = safe_days_since(sobriety_date)

    level_start_date = rs.get("level_start_date")
    days_on_level = rs.get("days_on_level")
    if days_on_level is None:
        days_on_level = safe_days_since(level_start_date)

    return {
        "resident_name": f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip(),
        "shelter": resident.get("shelter"),
        "resident_status": "Active" if resident.get("is_active") else "Inactive",
        "program_status": enrollment.get("program_status") if enrollment else None,
        "entry_date": enrollment.get("entry_date") if enrollment else None,
        "level": rs.get("program_level"),
        "level_start_date": level_start_date,
        "days_on_level": days_on_level,
        "step": rs.get("step_current"),
        "days_sober": days_sober,
        "open_needs_count": len(open_needs or []),
    }


def build_operations_snapshot(recovery_snapshot):
    rs = recovery_snapshot or {}
    latest = rs.get("latest_inspection")
    if not latest:
        return None

    return {
        "inspection_date": latest.get("inspection_date"),
        "result_display": latest.get("passed_display"),
        "notes": latest.get("notes"),
    }
