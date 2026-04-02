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


def _clean_text(value):
    if value is None:
        return ""
    return str(value).strip()


def _first_non_empty(*values):
    for value in values:
        if value is None:
            continue
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned:
                return cleaned
            continue
        return value
    return None


def _yes_no_from_need_state(is_need_present):
    if is_need_present is None:
        return ""
    return "no" if not bool(is_need_present) else ""


def _build_blocker_from_open_needs(open_needs):
    labels = []
    for need in open_needs or []:
        label = _clean_text((need or {}).get("need_label"))
        if label:
            labels.append(label)

    if not labels:
        return ""

    if len(labels) == 1:
        return f"Open need still blocking progress: {labels[0]}"

    preview = ", ".join(labels[:4])
    if len(labels) > 4:
        preview += ", and more"

    return f"Open needs still blocking progress: {preview}"


def _build_summary_hint(*, recovery_snapshot, family_snapshot, open_needs):
    rs = recovery_snapshot or {}
    fs = family_snapshot or {}

    parts = []

    level = _clean_text(rs.get("program_level"))
    if level:
        parts.append(f"Level {level}")

    days_sober = rs.get("days_sober_today")
    if days_sober is not None and str(days_sober).strip() != "":
        parts.append(f"{days_sober} days sober")

    employment_status = _clean_text(rs.get("employment_status_display") or rs.get("employment_status_current"))
    if employment_status and employment_status != "—":
        parts.append(f"employment status {employment_status.lower()}")

    sponsor_active = rs.get("sponsor_active")
    if sponsor_active is not None:
        parts.append("sponsor active yes" if sponsor_active else "sponsor active no")

    kids_at_dwc = fs.get("kids_at_dwc")
    if kids_at_dwc not in (None, ""):
        parts.append(f"children at DWC {kids_at_dwc}")

    open_need_count = len(open_needs or [])
    if open_need_count:
        parts.append(f"{open_need_count} open needs")
    else:
        parts.append("no open intake needs")

    return " | ".join(parts)


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

    next_appointment = _first_non_empty(
        latest_appointment.get("appointment_date"),
        last_note.get("next_appointment"),
        "",
    )

    blocker_reason = _first_non_empty(
        last_note.get("blocker_reason"),
        _build_blocker_from_open_needs(open_needs),
        "",
    )

    summary_hint = _build_summary_hint(
        recovery_snapshot=recovery_snapshot,
        family_snapshot=family_snapshot,
        open_needs=open_needs,
    )

    return {
        "meeting_date": date.today().isoformat(),
        "notes": "",
        "progress_notes": "",
        "setbacks_or_incidents": "",
        "action_items": "",
        "next_appointment": next_appointment or "",
        "overall_summary": summary_hint or "",
        "ready_for_next_level": (
            "yes"
            if last_note.get("ready_for_next_level") == 1
            else "no"
            if last_note.get("ready_for_next_level") == 0
            else ""
        ),
        "recommended_next_level": _clean_text(last_note.get("recommended_next_level")),
        "blocker_reason": blocker_reason or "",
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
