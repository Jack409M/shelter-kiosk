from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.progress_report_builders import build_progress_report_context
from routes.case_management_parts.progress_report_loaders import load_case_manager_name
from routes.case_management_parts.progress_report_loaders import load_goals
from routes.case_management_parts.progress_report_loaders import load_single_case_note
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case_scope import load_current_enrollment
from routes.case_management_parts.resident_case_scope import load_resident_in_scope


def _redirect_case_index():
    return redirect(url_for("case_management.index"))


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def progress_report_print_view(resident_id: int, update_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    resident = load_resident_in_scope(resident_id, shelter)
    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    enrollment = load_current_enrollment(resident_id)
    enrollment_id = enrollment["id"] if enrollment else None

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return _redirect_resident_case(resident_id)

    note = load_single_case_note(enrollment_id, update_id)
    if not note:
        flash("Case note not found.", "error")
        return _redirect_resident_case(resident_id)

    goals = load_goals(enrollment_id)
    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)
    case_manager_name = load_case_manager_name(note.get("staff_user_id"))

    report = build_progress_report_context(
        resident=resident,
        enrollment=enrollment,
        note=note,
        goals=goals,
        recovery_snapshot=recovery_snapshot,
        case_manager_name=case_manager_name,
    )

    return render_template(
        "case_management/progress_report_print_v2.html",
        report=report,
    )
