from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.attendance_hours import build_attendance_hours_snapshot
from core.db import db_fetchone
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case_children import load_children_with_services
from routes.case_management_parts.resident_case_discipline import load_active_writeup_restrictions
from routes.case_management_parts.resident_case_employment import (
    build_employment_income_snapshot,
    build_employment_stability_snapshot,
    load_employment_income_defaults,
    resolve_employment_status_snapshot,
    resolve_monthly_income_for_display,
)
from routes.case_management_parts.resident_case_enrollment_context import (
    base_empty_enrollment_context,
    calculate_grit_difference,
    load_enrollment_context,
)
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)
from routes.case_management_parts.resident_case_viewmodel import (
    build_meeting_defaults,
    build_operations_snapshot,
    build_workspace_header,
)
from routes.inspection_v2 import build_inspection_stability_snapshot
from routes.rent_tracking import build_rent_stability_snapshot


def _redirect_case_index():
    return redirect(url_for("case_management.index"))


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _require_case_manager_access():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))
    return None


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _load_employment_income_settings(shelter: str) -> dict:
    ph = placeholder()
    defaults = load_employment_income_defaults()

    try:
        row = db_fetchone(
            f"""
            SELECT
                employment_income_module_enabled,
                employment_income_graduation_minimum,
                employment_income_band_green_min,
                employment_income_band_yellow_min,
                employment_income_band_orange_min,
                employment_income_band_red_max
            FROM shelter_operation_settings
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
            LIMIT 1
            """,
            (shelter,),
        )
    except Exception:
        row = None

    if not row:
        return defaults

    resolved = dict(defaults)
    for key in resolved:
        if row.get(key) is not None:
            resolved[key] = row.get(key)
    return resolved


def _build_context(
    *,
    resident: dict,
    enrollment: dict | None,
    enrollment_id: int | None,
    enrollment_context: dict,
    recovery_snapshot: dict | None,
    children: list[dict],
    disciplinary_flags: list[dict],
    shelter: str,
) -> dict:
    grit_difference = calculate_grit_difference(
        enrollment_context["intake_assessment"],
        enrollment_context["exit_assessment"],
    )

    meeting_defaults = build_meeting_defaults(
        intake_assessment=enrollment_context["intake_assessment"],
        family_snapshot=enrollment_context["family_snapshot"],
        recovery_snapshot=recovery_snapshot,
        open_needs=enrollment_context["open_needs"],
        notes=enrollment_context["notes"],
        appointments=enrollment_context["appointments"],
    )

    workspace_header = build_workspace_header(
        resident=resident,
        enrollment=enrollment,
        recovery_snapshot=recovery_snapshot,
        open_needs=enrollment_context["open_needs"],
    )

    operations_snapshot = build_operations_snapshot(recovery_snapshot)
    rent_snapshot = build_rent_stability_snapshot(resident["id"])
    inspection_snapshot = build_inspection_stability_snapshot(resident["id"], shelter=shelter)
    attendance_hours_snapshot = build_attendance_hours_snapshot(
        resident_id=resident["id"],
        shelter=shelter,
        enrollment_entry_date=(enrollment.get("entry_date") if enrollment else None),
    )

    employment_income_settings = _load_employment_income_settings(shelter)
    intake_income_support = enrollment_context.get("intake_income_support") or {}

    monthly_income_for_display = resolve_monthly_income_for_display(enrollment_context)

    employment_income_snapshot = build_employment_income_snapshot(
        monthly_income_for_display,
        employment_income_settings,
    )

    employment_status_snapshot = resolve_employment_status_snapshot(
        recovery_snapshot,
        enrollment_context.get("intake_assessment"),
    )

    employment_stability_snapshot = build_employment_stability_snapshot(
        recovery_snapshot,
        employment_status_snapshot=employment_status_snapshot,
    )

    return {
        "resident": resident,
        "enrollment": enrollment,
        "enrollment_id": enrollment_id,
        "family_snapshot": enrollment_context["family_snapshot"],
        "intake_assessment": enrollment_context["intake_assessment"],
        "intake_income_support": intake_income_support,
        "exit_assessment": enrollment_context["exit_assessment"],
        "grit_difference": grit_difference,
        "goals": enrollment_context["goals"],
        "appointments": enrollment_context["appointments"],
        "notes": enrollment_context["notes"],
        "services": enrollment_context["services"],
        "children": children,
        "open_needs": enrollment_context["open_needs"],
        "recovery_snapshot": recovery_snapshot,
        "followup_6_month": enrollment_context["followup_6_month"],
        "followup_1_year": enrollment_context["followup_1_year"],
        "meeting_defaults": meeting_defaults,
        "workspace_header": workspace_header,
        "operations_snapshot": operations_snapshot,
        "rent_snapshot": rent_snapshot,
        "inspection_snapshot": inspection_snapshot,
        "attendance_hours_snapshot": attendance_hours_snapshot,
        "employment_income_snapshot": employment_income_snapshot,
        "employment_status_snapshot": employment_status_snapshot,
        "employment_stability_snapshot": employment_stability_snapshot,
        "is_deceased_case": enrollment_context["is_deceased_case"],
        "disciplinary_flags": disciplinary_flags,
        "has_disciplinary_block": len(disciplinary_flags) > 0,
    }


def resident_case_view(resident_id: int):
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
        "case_management/resident_case.html",
        **context,
    )
