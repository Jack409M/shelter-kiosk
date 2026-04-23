from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.db import db_fetchone
from core.l9_support_lifecycle import start_level9_lifecycle
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
from routes.case_management_parts.resident_case_scope import (
    load_current_enrollment,
    load_resident_in_scope,
)


def _require_case_manager_access():
    if case_manager_allowed():
        return None
    flash("Case manager access required.", "error")
    return redirect(url_for("attendance.staff_attendance"))


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _current_staff_user_id() -> int | None:
    raw = session.get("staff_user_id")
    if raw in (None, ""):
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _normalized_level_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _load_current_program_level(resident_id: int, shelter: str) -> str | None:
    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT program_level
        FROM residents
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = LOWER({ph})
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    if not row:
        return None
    return _normalized_level_text(row.get("program_level"))


def _load_existing_level9_lifecycle(enrollment_id: int):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT
            id,
            status,
            participation_status,
            start_date,
            initial_end_date,
            extended_end_date,
            final_end_date
        FROM level9_support_lifecycles
        WHERE enrollment_id = {ph}
        LIMIT 1
        """,
        (enrollment_id,),
    )


def l9_disposition_view(resident_id: int):
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
        flash("Resident does not have an active enrollment record.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment.get("id")
    if not isinstance(enrollment_id, int):
        flash("Active enrollment record is invalid.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    current_level = _load_current_program_level(resident_id, shelter)
    if current_level != "9":
        flash(
            "Resident must already be promoted to Level 9 before disposition can be completed.",
            "error",
        )
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    existing_lifecycle = _load_existing_level9_lifecycle(enrollment_id)

    return render_template(
        "case_management/l9_disposition.html",
        resident=resident,
        enrollment=enrollment,
        existing_lifecycle=existing_lifecycle,
    )


def submit_l9_disposition_view(resident_id: int):
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
        flash("Resident does not have an active enrollment record.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    enrollment_id = enrollment.get("id")
    if not isinstance(enrollment_id, int):
        flash("Active enrollment record is invalid.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    current_level = _load_current_program_level(resident_id, shelter)
    if current_level != "9":
        flash(
            "Resident must already be promoted to Level 9 before disposition can be completed.",
            "error",
        )
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    action = (request.form.get("disposition_action") or "").strip().lower()
    staff_user_id = _current_staff_user_id()

    if action == "exit_now":
        flash(
            "Complete the exit interview to terminate and deactivate this resident.",
            "success",
        )
        return redirect(url_for("case_management.exit_assessment", resident_id=resident_id))

    if action == "enroll_support":
        existing_lifecycle = _load_existing_level9_lifecycle(enrollment_id)
        if existing_lifecycle:
            flash("Level 9 supportive services have already been started for this resident.", "error")
            return redirect(url_for("case_management.l9_workspace"))

        try:
            start_level9_lifecycle(
                resident_id=resident_id,
                enrollment_id=enrollment_id,
                shelter=shelter,
                case_manager_user_id=staff_user_id,
                started_by_user_id=staff_user_id,
                apartment_exit_reason="Promoted to Level 9 and enrolled in supportive services.",
                notes="Level 9 supportive services started from disposition step after housing exit.",
            )
        except Exception:
            flash("Unable to start Level 9 supportive services.", "error")
            return redirect(url_for("case_management.l9_disposition", resident_id=resident_id))

        flash("Level 9 supportive services started.", "success")
        return redirect(url_for("case_management.l9_workspace"))

    flash("Select a valid Level 9 disposition action.", "error")
    return redirect(url_for("case_management.l9_disposition", resident_id=resident_id))
