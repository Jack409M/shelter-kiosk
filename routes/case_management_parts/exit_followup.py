from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed, normalize_shelter_name
from routes.case_management_parts.resident_case_enrollment_context import load_enrollment_context
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)


def _redirect_case_index():
    return redirect(url_for("case_management.index"))



def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))



def exit_followup_view(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    resident = load_resident_in_scope(resident_id, shelter)
    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    enrollment = load_current_enrollment(resident_id, shelter)
    if not enrollment:
        flash("Resident does not have an active enrollment record yet.", "error")
        return _redirect_resident_case(resident_id)

    enrollment_id = enrollment.get("id")
    if not isinstance(enrollment_id, int):
        flash("Active enrollment record is invalid.", "error")
        return _redirect_resident_case(resident_id)

    enrollment_context = load_enrollment_context(enrollment_id)

    return render_template(
        "case_management/exit_followup.html",
        resident=resident,
        enrollment=enrollment,
        exit_assessment=enrollment_context.get("exit_assessment"),
        followup_6_month=enrollment_context.get("followup_6_month"),
        followup_1_year=enrollment_context.get("followup_1_year"),
        is_deceased_case=enrollment_context.get("is_deceased_case", False),
    )
