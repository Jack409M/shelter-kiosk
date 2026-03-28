
from __future__ import annotations

from flask import flash, redirect, request, session, url_for, render_template

from core.db import db_execute, db_fetchone, db_fetchall
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.needs import normalize_need_status


ALLOWED_SERVICE_TYPES = {
    "Counseling",
    "Dental",
    "Vision",
    "Parenting Support",
    "Legal Assistance",
    "Transportation",
    "Daycare",
    "Other",
}


def _clean_service_types(raw_values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in raw_values:
        service_type = (value or "").strip()
        if not service_type:
            continue
        if service_type not in ALLOWED_SERVICE_TYPES:
            continue
        if service_type in seen:
            continue
        seen.add(service_type)
        cleaned.append(service_type)

    return cleaned


def _yes_no_to_int(value: str | None):
    value = (value or "").strip().lower()
    if value == "yes":
        return 1
    if value == "no":
        return 0
    return None


def _parse_quantity(value: str | None):
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _apply_need_updates(enrollment_id: int, staff_user_id: int, form) -> int:
    ph = placeholder()
    now = utcnow_iso()

    open_needs = db_fetchall(
        f"""
        SELECT
            id,
            need_key
        FROM resident_needs
        WHERE enrollment_id = {ph}
          AND status = 'open'
        """,
        (enrollment_id,),
    )

    resolved_count = 0

    for need in open_needs:
        need_id = need["id"]
        need_key = need["need_key"]

        status = normalize_need_status(form.get(f"need_status_{need_key}"))
        if status not in {"addressed", "not_applicable"}:
            continue

        resolution_note = (form.get(f"need_note_{need_key}") or "").strip()

        db_execute(
            f"""
            UPDATE resident_needs
            SET
                status = {ph},
                resolution_note = {ph},
                resolved_at = {ph},
                resolved_by_staff_user_id = {ph},
                updated_at = {ph}
            WHERE id = {ph}
            """,
            (
                status,
                resolution_note or None,
                now,
                staff_user_id,
                now,
                need_id,
            ),
        )
        resolved_count += 1

    return resolved_count


def add_case_note_view(resident_id: int):
    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    staff_user_id = session.get("staff_user_id")
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident = db_fetchone(
        f"""
        SELECT id, resident_identifier
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = db_fetchone(
        f"""
        SELECT id
        FROM program_enrollments
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    enrollment_id = enrollment["id"] if enrollment else None

    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not staff_user_id:
        flash("Your session is missing a staff user id. Please log in again.", "error")
        return redirect(url_for("auth.staff_login"))

    meeting_date = (request.form.get("meeting_date") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    progress_notes = (request.form.get("progress_notes") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()

    updated_grit_raw = (request.form.get("updated_grit") or "").strip()
    updated_grit = int(updated_grit_raw) if updated_grit_raw else None
    parenting_class_completed = _yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = _yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = _clean_service_types(request.form.getlist("service_type"))
    service_date = (request.form.get("service_date") or "").strip() or meeting_date

    if not meeting_date:
        flash("Meeting date is required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resolved_need_count = _apply_need_updates(enrollment_id, int(staff_user_id), request.form)

    has_structured_progress = (
        updated_grit is not None
        or parenting_class_completed is not None
        or warrants_or_fines_paid is not None
        or bool(service_types)
        or resolved_need_count > 0
    )

    if not notes and not progress_notes and not action_items and not has_structured_progress:
        flash("Enter notes, progress notes, action items, structured progress, need resolutions, or at least one service.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        f"""
        INSERT INTO case_manager_updates
        (
            enrollment_id,
            staff_user_id,
            meeting_date,
            notes,
            progress_notes,
            action_items,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            created_at,
            updated_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            enrollment_id,
            staff_user_id,
            meeting_date,
            notes or None,
            progress_notes or None,
            action_items or None,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            now,
            now,
        ),
    )

    note = db_fetchone(
        f"""
        SELECT id
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    note_id = note["id"]

    for service_type in service_types:
        service_note = (request.form.get(f"service_notes_{service_type}") or "").strip()
        quantity = _parse_quantity(request.form.get(f"quantity_{service_type}"))
        unit = (request.form.get(f"unit_{service_type}") or "").strip()

        db_execute(
            f"""
            INSERT INTO client_services
            (
                enrollment_id,
                case_manager_update_id,
                service_type,
                service_date,
                quantity,
                unit,
                notes,
                created_at,
                updated_at
            )
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """,
            (
                enrollment_id,
                note_id,
                service_type,
                service_date,
                quantity,
                unit or None,
                service_note or None,
                now,
                now,
            ),
        )

    flash("Case manager update saved.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def edit_case_note_view(resident_id: int, update_id: int):
    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    staff_user_id = session.get("staff_user_id")
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not staff_user_id:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("auth.staff_login"))

    resident = db_fetchone(
        f"""
        SELECT id, resident_identifier
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    note = db_fetchone(
        f"""
        SELECT cmu.*, pe.resident_id
        FROM case_manager_updates cmu
        JOIN program_enrollments pe ON pe.id = cmu.enrollment_id
        WHERE cmu.id = {ph}
        """,
        (update_id,),
    )

    if not note:
        flash("Note not found.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if note["resident_id"] != resident_id:
        flash("Invalid note access.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if request.method == "GET":
        services = db_fetchall(
            f"""
            SELECT service_type, quantity, unit, notes
            FROM client_services
            WHERE case_manager_update_id = {ph}
            """,
            (update_id,),
        )

        selected_services = []
        service_notes_map = {}
        service_quantity_map = {}
        service_unit_map = {}

        for s in services:
            st = s["service_type"]
            qty = s["quantity"]
            unit = s["unit"]
            sn = s["notes"]
            selected_services.append(st)
            service_notes_map[st] = sn or ""
            service_quantity_map[st] = qty if qty is not None else ""
            service_unit_map[st] = unit or ""

        return render_template(
            "case_management/edit_case_note.html",
            resident=resident,
            note=note,
            selected_services=selected_services,
            service_notes_map=service_notes_map,
            service_quantity_map=service_quantity_map,
            service_unit_map=service_unit_map,
        )

    meeting_date = (request.form.get("meeting_date") or "").strip()
    notes = (request.form.get("notes") or "").strip()
    progress_notes = (request.form.get("progress_notes") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()

    updated_grit_raw = (request.form.get("updated_grit") or "").strip()
    updated_grit = int(updated_grit_raw) if updated_grit_raw else None
    parenting_class_completed = _yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = _yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = _clean_service_types(request.form.getlist("service_type"))
    service_date = (request.form.get("service_date") or "").strip() or meeting_date

    if not meeting_date:
        flash("Meeting date is required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE case_manager_updates
        SET meeting_date = {ph},
            notes = {ph},
            progress_notes = {ph},
            action_items = {ph},
            updated_grit = {ph},
            parenting_class_completed = {ph},
            warrants_or_fines_paid = {ph},
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (
            meeting_date,
            notes or None,
            progress_notes or None,
            action_items or None,
            updated_grit,
            parenting_class_completed,
            warrants_or_fines_paid,
            now,
            update_id,
        ),
    )

    db_execute(
        f"""
        DELETE FROM client_services
        WHERE case_manager_update_id = {ph}
        """,
        (update_id,),
    )

    for service_type in service_types:
        service_note = (request.form.get(f"service_notes_{service_type}") or "").strip()
        quantity = _parse_quantity(request.form.get(f"quantity_{service_type}"))
        unit = (request.form.get(f"unit_{service_type}") or "").strip()

        db_execute(
            f"""
            INSERT INTO client_services
            (
                enrollment_id,
                case_manager_update_id,
                service_type,
                service_date,
                quantity,
                unit,
                notes,
                created_at,
                updated_at
            )
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
            """,
            (
                note["enrollment_id"],
                update_id,
                service_type,
                service_date,
                quantity,
                unit or None,
                service_note or None,
                now,
                now,
            ),
        )

    flash("Case note updated.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))

