from __future__ import annotations

from urllib.parse import urlencode

from flask import flash, render_template, request, url_for

from core.runtime import init_db
from routes.admin_parts.sh_data_quality import _load_data_quality_issues
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

CWR_NOTES_ACTIVE_PANEL = "notes"

_NOTE_VALUE_FIELDS = (
    "meeting_date",
    "notes",
    "progress_notes",
    "setbacks_or_incidents",
    "action_items",
    "overall_summary",
    "updated_grit",
    "parenting_class_completed",
    "warrants_or_fines_paid",
    "ready_for_next_level",
    "recommended_next_level",
    "blocker_reason",
    "override_or_exception",
    "staff_review_note",
)


def _clean_note_value(value):
    if value is None:
        return ""
    return value


def _build_cwr_note_maps(resident_id: int, notes: list[dict]) -> tuple[dict, dict]:
    note_edit_by_date = {}
    note_values_by_date = {}

    for note in notes or []:
        meeting_date = str(note.get("meeting_date") or "")[:10]
        note_id = note.get("id")

        if not meeting_date or not note_id:
            continue

        note_edit_by_date[meeting_date] = url_for(
            "case_management.edit_case_note",
            resident_id=resident_id,
            update_id=note_id,
            redirect_to="cwr",
            active_panel=CWR_NOTES_ACTIVE_PANEL,
        )
        note_values_by_date[meeting_date] = {
            field_name: _clean_note_value(note.get(field_name))
            for field_name in _NOTE_VALUE_FIELDS
        }

    return note_edit_by_date, note_values_by_date


def _append_next_param(action_url: str, next_url: str) -> str:
    if not action_url or not next_url:
        return action_url

    separator = "&" if "?" in action_url else "?"
    return f"{action_url}{separator}{urlencode({'next': next_url})}"


def _load_cwr_data_quality_issues(resident_id: int) -> list[dict]:
    next_url = request.path
    resident_issues: list[dict] = []

    for issue in _load_data_quality_issues():
        for row in issue.get("rows", []):
            if int(row.get("id") or 0) != int(resident_id):
                continue

            action_url = row.get("action_url") or ""

            # CWR is a case manager workspace. Keep admin-only POST repairs on the
            # admin Data Quality screen and surface only safe navigation fixes here.
            if not action_url:
                continue

            resident_issues.append(
                {
                    "label": issue.get("label", "Data quality issue"),
                    "description": issue.get("description", ""),
                    "severity": issue.get("severity", "warn"),
                    "action_label": row.get("action_label") or "Fix",
                    "action_url": _append_next_param(action_url, next_url),
                }
            )

    return resident_issues


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

    note_edit_by_date, note_values_by_date = _build_cwr_note_maps(
        resident_id,
        context.get("notes", []),
    )
    context["cwr_note_edit_by_date"] = note_edit_by_date
    context["cwr_note_values_by_date"] = note_values_by_date
    context["data_quality_issues"] = _load_cwr_data_quality_issues(resident_id)

    return render_template(
        "case_management/cwr_workspace.html",
        **context,
    )
