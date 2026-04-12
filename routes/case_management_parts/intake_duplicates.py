from __future__ import annotations

from typing import Any

from flask import flash, redirect, render_template, session, url_for

from core.intake_service import create_intake
from core.intake_service import create_intake_for_existing_resident
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.intake_drafts import _dismiss_intake_draft
from routes.case_management_parts.intake_drafts import _load_intake_draft
from routes.case_management_parts.intake_validation import _find_possible_duplicate


def _row_value(row: Any, key: str, index: int):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key)
    return row[index]


def _fetch_existing_duplicate_for_draft(current_shelter: str, pending_form_data: dict[str, Any]):
    return _find_possible_duplicate(
        first_name=pending_form_data.get("first_name"),
        last_name=pending_form_data.get("last_name"),
        birth_year=parse_int(pending_form_data.get("birth_year")),
        phone=pending_form_data.get("phone"),
        email=pending_form_data.get("email"),
        shelter=current_shelter,
        shelter_equals_sql=None,
    )


def _fetch_existing_enrollment_for_resident(resident_id: int):
    return fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            entry_date,
            exit_date,
            program_status,
            shelter
        """,
    )


def duplicate_review_view(draft_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    pending_form_data = _load_intake_draft(current_shelter, draft_id)

    if not pending_form_data:
        flash("Pending intake review not found.", "error")
        return redirect(url_for("case_management.intake_index"))

    if pending_form_data.get("draft_status") != "pending_duplicate_review":
        flash("This intake is not waiting on duplicate review.", "error")
        return redirect(url_for("case_management.intake_form", draft_id=draft_id))

    existing_resident = _fetch_existing_duplicate_for_draft(current_shelter, pending_form_data)
    if not existing_resident:
        flash("No active duplicate match was found for this pending intake.", "error")
        return redirect(url_for("case_management.intake_form", draft_id=draft_id))

    existing_resident_id = _row_value(existing_resident, "id", 0)
    existing_enrollment = _fetch_existing_enrollment_for_resident(existing_resident_id)

    return render_template(
        "case_management/intake_duplicate_review.html",
        draft_id=draft_id,
        pending_form_data=pending_form_data,
        existing_resident=existing_resident,
        existing_enrollment=existing_enrollment,
        current_shelter=current_shelter,
    )


def duplicate_review_use_existing_view(draft_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    pending_form_data = _load_intake_draft(current_shelter, draft_id)

    if not pending_form_data:
        flash("Pending intake review not found.", "error")
        return redirect(url_for("case_management.intake_index"))

    existing_resident = _fetch_existing_duplicate_for_draft(current_shelter, pending_form_data)
    if not existing_resident:
        flash("No duplicate resident was found to continue on.", "error")
        return redirect(url_for("case_management.intake_form", draft_id=draft_id))

    existing_resident_id = _row_value(existing_resident, "id", 0)
    existing_enrollment = _fetch_existing_enrollment_for_resident(existing_resident_id)

    if existing_enrollment:
        flash(
            "This resident already has an active enrollment. Open the existing case manager workspace instead of starting a new enrollment.",
            "error",
        )
        return redirect(url_for("case_management.resident_case", resident_id=existing_resident_id))

    create_intake_for_existing_resident(
        current_shelter=current_shelter,
        existing_resident_id=existing_resident_id,
        data=pending_form_data,
        draft_id=draft_id,
    )

    flash(
        "Returning resident matched. Existing resident record kept and a new enrollment was started.",
        "success",
    )
    return redirect(url_for("case_management.resident_case", resident_id=existing_resident_id))


def duplicate_review_create_new_view(draft_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    pending_form_data = _load_intake_draft(current_shelter, draft_id)

    if not pending_form_data:
        flash("Pending intake review not found.", "error")
        return redirect(url_for("case_management.intake_index"))

    create_result = create_intake(
        current_shelter=current_shelter,
        data=pending_form_data,
        draft_id=draft_id,
    )

    flash(
        f"New resident created successfully after duplicate review. Resident ID: {create_result.resident_identifier}. Resident Code: {create_result.resident_code}",
        "success",
    )
    return redirect(url_for("case_management.resident_case", resident_id=create_result.resident_id))


def duplicate_review_dismiss_view(draft_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    pending_form_data = _load_intake_draft(current_shelter, draft_id)

    if not pending_form_data:
        flash("Pending intake review not found.", "error")
        return redirect(url_for("case_management.intake_index"))

    _dismiss_intake_draft(draft_id)
    flash("Pending intake review was dismissed. No resident was created.", "success")
    return redirect(url_for("case_management.intake_index"))


def duplicate_review_return_to_edit_view(draft_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    pending_form_data = _load_intake_draft(current_shelter, draft_id)

    if not pending_form_data:
        flash("Pending intake review not found.", "error")
        return redirect(url_for("case_management.intake_index"))

    flash("Returned pending intake to edit mode.", "success")
    return redirect(url_for("case_management.intake_form", draft_id=draft_id))
