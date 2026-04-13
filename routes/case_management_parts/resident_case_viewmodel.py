from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo


CHI = ZoneInfo("America/Chicago")

APPOINTMENT_PARSE_FORMATS = [
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y",
    "%m/%d/%y",
    "%m/%d/%Y %I:%M %p",
    "%m/%d/%y %I:%M %p",
    "%m/%d/%Y %H:%M",
    "%m/%d/%y %H:%M",
]


def chicago_today() -> date:
    return datetime.now(CHI).date()


def _clean_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def safe_days_since(date_text: str | None):
    if not date_text:
        return None

    try:
        parsed = date.fromisoformat(str(date_text)[:10])
    except Exception:
        return None

    days = (chicago_today() - parsed).days
    if days < 0:
        return 0
    return days


def _yes_no_from_need_state(is_need_present):
    if is_need_present is None:
        return ""
    return "no" if not bool(is_need_present) else ""


def _build_summary_hint(*, recovery_snapshot, family_snapshot, open_needs):
    rs = recovery_snapshot or {}
    fs = family_snapshot or {}
    needs = open_needs or []

    parts: list[str] = []

    level = _clean_text(rs.get("program_level"))
    if level:
        parts.append(f"Level {level}")

    days_sober = rs.get("days_sober_today")
    if days_sober is not None and _clean_text(days_sober) != "":
        parts.append(f"{days_sober} days sober")

    employment_status = _clean_text(
        rs.get("employment_status_display") or rs.get("employment_status_current")
    )
    if employment_status and employment_status != "—":
        parts.append(f"employment status {employment_status.lower()}")

    sponsor_active = rs.get("sponsor_active")
    if sponsor_active is not None:
        parts.append("sponsor active" if sponsor_active else "no active sponsor")

    kids_at_dwc = fs.get("kids_at_dwc")
    if kids_at_dwc not in (None, ""):
        parts.append(f"children at DWC {kids_at_dwc}")

    if needs:
        parts.append(f"{len(needs)} open needs")

    return ". ".join(parts)


def _parse_future_date_from_text(value: str | None) -> datetime | None:
    text = _clean_text(value)
    if not text:
        return None

    for fmt in APPOINTMENT_PARSE_FORMATS:
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    return None


def _normalize_appointment_display(value: str | None) -> str:
    text = _clean_text(value)
    if not text:
        return ""

    parsed_dt = _parse_future_date_from_text(text)
    if not parsed_dt:
        return text

    if parsed_dt.hour == 0 and parsed_dt.minute == 0:
        return parsed_dt.strftime("%m/%d/%Y")

    return parsed_dt.strftime("%m/%d/%Y %I:%M %p").replace(" 0", " ")


def _is_current_or_future_appointment(value: str | None) -> bool:
    parsed_dt = _parse_future_date_from_text(value)
    if not parsed_dt:
        return False
    return parsed_dt.date() >= chicago_today()


def _resolve_meeting_default_next_appointment(latest_appointment) -> str:
    latest_appointment_date = (
        _clean_text(latest_appointment.get("appointment_date"))
        if latest_appointment
        else ""
    )

    if latest_appointment_date and _is_current_or_future_appointment(latest_appointment_date):
        return _normalize_appointment_display(latest_appointment_date)

    return ""


def _resolve_ready_for_next_level(value) -> str:
    if value == 1:
        return "yes"
    if value == 0:
        return "no"
    return ""


def _resolve_days_sober(recovery_snapshot: dict) -> object:
    sobriety_date = recovery_snapshot.get("sobriety_date")
    days_sober = recovery_snapshot.get("days_sober_today")
    if days_sober is None:
        days_sober = safe_days_since(sobriety_date)
    return days_sober


def _resolve_days_on_level(recovery_snapshot: dict) -> tuple[object, object]:
    level_start_date = recovery_snapshot.get("level_start_date")
    days_on_level = recovery_snapshot.get("days_on_level")
    if days_on_level is None:
        days_on_level = safe_days_since(level_start_date)
    return level_start_date, days_on_level


def build_meeting_defaults(
    *,
    intake_assessment=None,
    family_snapshot=None,
    recovery_snapshot=None,
    open_needs=None,
    notes=None,
    appointments=None,
):
    intake_assessment = intake_assessment or {}
    family_snapshot = family_snapshot or {}
    recovery_snapshot = recovery_snapshot or {}
    open_needs = open_needs or []
    notes = notes or []
    appointments = appointments or []

    last_note = notes[-1] if notes else {}
    latest_appointment = appointments[0] if appointments else {}

    return {
        "meeting_date": chicago_today().isoformat(),
        "notes": "",
        "progress_notes": "",
        "setbacks_or_incidents": "",
        "action_items": "",
        "next_appointment": _resolve_meeting_default_next_appointment(latest_appointment),
        "overall_summary": _build_summary_hint(
            recovery_snapshot=recovery_snapshot,
            family_snapshot=family_snapshot,
            open_needs=open_needs,
        ),
        "ready_for_next_level": _resolve_ready_for_next_level(
            last_note.get("ready_for_next_level")
        ),
        "recommended_next_level": _clean_text(last_note.get("recommended_next_level")),
        "blocker_reason": "",
        "override_or_exception": _clean_text(last_note.get("override_or_exception")),
        "staff_review_note": _clean_text(last_note.get("staff_review_note")),
        "updated_grit": intake_assessment.get("grit_score"),
        "parenting_class_completed": _yes_no_from_need_state(
            intake_assessment.get("parenting_class_needed")
        ),
        "warrants_or_fines_paid": _yes_no_from_need_state(
            intake_assessment.get("warrants_unpaid")
        ),
    }


def build_workspace_header(*, resident, enrollment, recovery_snapshot, open_needs):
    rs = recovery_snapshot or {}

    level_start_date, days_on_level = _resolve_days_on_level(rs)
    days_sober = _resolve_days_sober(rs)

    return {
        "resident_name": f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip(),
        "resident_identifier": resident.get("resident_identifier"),
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
