from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone
from core.helpers import fmt_pretty_dt, utcnow_iso
from core.runtime import init_db
from routes.case_management import case_management
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.recovery_snapshot import load_recovery_snapshot
from routes.case_management_parts.resident_case_notes import build_note_objects


def _load_current_enrollment(resident_id: int):
    return fetch_current_enrollment_for_resident(
        resident_id,
        columns="""
            id,
            shelter,
            program_status,
            entry_date,
            exit_date
        """,
    )


def _load_single_case_note(enrollment_id: int, update_id: int):
    ph = placeholder()

    notes_raw = db_fetchall(
        f"""
        SELECT
            id,
            staff_user_id,
            meeting_date,
            notes,
            progress_notes,
            setbacks_or_incidents,
            action_items,
            next_appointment,
            overall_summary,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            created_at
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND id = {ph}
        LIMIT 1
        """,
        (enrollment_id, update_id),
    )

    if not notes_raw:
        return None

    services_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            service_type,
            service_date,
            quantity,
            unit,
            notes
        FROM client_services
        WHERE enrollment_id = {ph}
          AND case_manager_update_id = {ph}
        ORDER BY service_date DESC, id DESC
        """,
        (enrollment_id, update_id),
    )

    summary_rows_raw = db_fetchall(
        f"""
        SELECT
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order
        FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
        ORDER BY sort_order ASC, id ASC
        """,
        (update_id,),
    )

    notes, _ = build_note_objects(notes_raw, services_raw, summary_rows_raw)
    return notes[0] if notes else None


def _load_case_manager_name(staff_user_id: int | None) -> str:
    if not staff_user_id:
        return "Current Staff"

    ph = placeholder()
    row = db_fetchone(
        f"""
        SELECT
            first_name,
            last_name,
            username
        FROM staff_users
        WHERE id = {ph}
        LIMIT 1
        """,
        (staff_user_id,),
    )

    if not row:
        return "Current Staff"

    first_name = (row.get("first_name") or "").strip()
    last_name = (row.get("last_name") or "").strip()
    username = (row.get("username") or "").strip()

    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or username or "Current Staff"


def _build_progress_report_context(
    *,
    resident: dict,
    enrollment: dict | None,
    note: dict,
    goals: list[dict],
    recovery_snapshot: dict | None,
    case_manager_name: str,
):
    recovery_snapshot = recovery_snapshot or {}
    note_services = note.get("services") or []

    resident_name = " ".join(
        part for part in [resident.get("first_name"), resident.get("last_name")] if part
    ).strip() or "Resident"

    resident_display_id = (
        resident.get("resident_identifier")
        or resident.get("resident_code")
        or str(resident.get("id") or "")
    )

    service_rows = []
    for service in note_services:
        quantity_display = service.get("quantity_display")
        service_rows.append(
            {
                "service_type": service.get("service_type") or "—",
                "service_date": service.get("service_date") or note.get("meeting_date") or "—",
                "quantity_display": quantity_display if quantity_display and quantity_display != "—" else "",
                "notes": service.get("notes") or "",
            }
        )

    goal_rows = []
    for goal in goals:
        goal_rows.append(
            {
                "goal_text": goal.get("goal_text") or "—",
                "status": goal.get("status") or "—",
                "target_date": goal.get("target_date") or "",
            }
        )

    generated_at = utcnow_iso()

    return {
        "report_title": "Progress Report",
        "generated_at_display": fmt_pretty_dt(generated_at),
        "resident_name": resident_name,
        "resident_display_id": resident_display_id,
        "resident": resident,
        "enrollment": enrollment,
        "note": note,
        "goals": goal_rows,
        "case_manager_name": case_manager_name,
        "service_rows": service_rows,
        "program_snapshot": [
            {"label": "Program Status", "value": enrollment.get("program_status") if enrollment else "—"},
            {"label": "Level", "value": recovery_snapshot.get("program_level") or "—"},
            {"label": "Level Start Date", "value": recovery_snapshot.get("level_start_date") or "—"},
            {
                "label": "Days On Level",
                "value": recovery_snapshot.get("days_on_level")
                if recovery_snapshot.get("days_on_level") is not None
                else "—",
            },
            {
                "label": "Days Sober",
                "value": recovery_snapshot.get("days_sober_today")
                if recovery_snapshot.get("days_sober_today") is not None
                else "—",
            },
            {"label": "Sobriety Date", "value": recovery_snapshot.get("sobriety_date") or "—"},
            {"label": "Drug Of Choice", "value": recovery_snapshot.get("drug_of_choice") or "—"},
            {"label": "Sponsor", "value": recovery_snapshot.get("sponsor_name") or "—"},
            {"label": "Employment Status", "value": recovery_snapshot.get("employment_status_current") or "—"},
            {
                "label": "Monthly Income",
                "value": recovery_snapshot.get("monthly_income")
                if recovery_snapshot.get("monthly_income") not in (None, "")
                else "—",
            },
        ],
        "advancement_rows": [
            {"label": "Ready For Next Level", "value": note.get("ready_for_next_level_display") or "—"},
            {"label": "Recommended Next Level", "value": note.get("recommended_next_level") or "—"},
            {"label": "Blocker Reason", "value": note.get("blocker_reason") or "—"},
            {"label": "Override Or Exception", "value": note.get("override_or_exception") or "—"},
            {"label": "Staff Review Note", "value": note.get("staff_review_note") or "—"},
        ],
    }


@case_management.get("/<int:resident_id>/case-notes/<int:update_id>/print")
@require_login
@require_shelter
def progress_report_print(resident_id: int, update_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = _load_current_enrollment(resident_id)
    enrollment_id = enrollment["id"] if enrollment else None

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    note = _load_single_case_note(enrollment_id, update_id)
    if not note:
        flash("Case note not found.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    goals = db_fetchall(
        f"""
        SELECT
            goal_text,
            status,
            target_date
        FROM goals
        WHERE enrollment_id = {ph}
        ORDER BY created_at DESC, id DESC
        """,
        (enrollment_id,),
    )

    recovery_snapshot = load_recovery_snapshot(resident_id, enrollment_id)
    case_manager_name = _load_case_manager_name(note.get("staff_user_id"))

    report = _build_progress_report_context(
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
