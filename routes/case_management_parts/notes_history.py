from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed, normalize_shelter_name
from routes.case_management_parts.resident_case_enrollment_context import load_case_history
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)


NOTES_ACTIVE_PANEL = "notes"


def _require_case_manager_access():
    if case_manager_allowed():
        return None
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _came_from_cwr() -> bool:
    return (
        request.args.get("return_to")
        or request.form.get("return_to")
        or ""
    ).strip().lower() == "cwr"


def _active_panel() -> str:
    return (
        request.args.get("active_panel")
        or request.form.get("active_panel")
        or NOTES_ACTIVE_PANEL
    ).strip() or NOTES_ACTIVE_PANEL


def _back_url(resident_id: int) -> str:
    if _came_from_cwr():
        return url_for(
            "case_management.cwr_workspace",
            resident_id=resident_id,
            active_panel=_active_panel(),
        )
    return url_for("case_management.resident_case", resident_id=resident_id)


def _back_redirect(resident_id: int):
    return redirect(_back_url(resident_id))


def notes_history_view(resident_id: int):
    init_db()

    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    shelter = _current_shelter()
    resident = load_resident_in_scope(resident_id, shelter)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = load_current_enrollment(resident_id, shelter)
    if not enrollment:
        flash("Resident does not have an active enrollment record yet.", "error")
        return _back_redirect(resident_id)

    enrollment_id = enrollment.get("id")
    if not isinstance(enrollment_id, int):
        flash("Active enrollment record is invalid.", "error")
        return _back_redirect(resident_id)

    notes, services = load_case_history(enrollment_id)

    first_name = resident.get("first_name") or ""
    last_name = resident.get("last_name") or ""
    initials = (
        (first_name[:1] if first_name else "") + (last_name[:1] if last_name else "")
    ) or "R"

    return render_template(
        "case_management/notes_history.html",
        resident=resident,
        resident_id=resident_id,
        resident_active=resident.get("is_active"),
        resident_code=resident.get("resident_code"),
        first_name=first_name,
        last_name=last_name,
        initials=initials.upper(),
        shelter=resident.get("shelter"),
        enrollment=enrollment,
        enrollment_entry_date=enrollment.get("entry_date"),
        notes=notes,
        services=services,
        return_to="cwr" if _came_from_cwr() else "",
        active_panel=_active_panel(),
        back_url=_back_url(resident_id),
    )
