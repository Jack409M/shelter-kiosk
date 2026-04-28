from __future__ import annotations

from flask import flash, redirect, render_template, url_for

from core.runtime import init_db
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case import (
    _build_context,
    _current_shelter,
    _redirect_case_index,
    _require_case_manager_access,
)
from routes.case_management_parts.resident_case_children import load_children_with_services
from routes.case_management_parts.resident_case_discipline import load_active_writeup_restrictions
from routes.case_management_parts.resident_case_enrollment_context import (
    base_empty_enrollment_context,
    load_enrollment_context,
)
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)


def cwr_workspace_view(resident_id: int):
    denied = _require_case_manager_access()
    if denied is not None:
        return denied

    init_db()

    shelter = _current_shelter()
    resident = load_resident_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return _redirect_case_index()

    enrollment = load_current_enrollment(resident_id, shelter)
    enrollment_id = enrollment["id"] if enrollment else None

    children = load_children_with_services(resident_id)
    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)
    disciplinary_flags = load_active_writeup_restrictions(resident_id)

    enrollment_context = base_empty_enrollment_context()
    if enrollment_id:
        enrollment_context = load_enrollment_context(enrollment_id)

    context = _build_context(
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        enrollment_context=enrollment_context,
        recovery_snapshot=recovery_snapshot,
        children=children,
        disciplinary_flags=disciplinary_flags,
        shelter=shelter,
    )

    return render_template(
        "case_management/cwr_workspace.html",
        **context,
    )
