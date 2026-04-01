from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import fetch_current_enrollment_for_resident
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.update_needs import apply_need_updates
from routes.case_management_parts.update_needs import collect_need_updates
from routes.case_management_parts.update_summary import build_note_summary
from routes.case_management_parts.update_summary import delete_summary_rows_by_group
from routes.case_management_parts.update_summary import get_next_summary_sort_order
from routes.case_management_parts.update_summary import get_previous_note_id
from routes.case_management_parts.update_summary import record_service_summary
from routes.case_management_parts.update_summary import record_snapshot_change_group
from routes.case_management_parts.update_snapshots import load_previous_snapshot_map
from routes.case_management_parts.update_utils import ADVANCEMENT_BOOL_FIELD_LABELS
from routes.case_management_parts.update_utils import ADVANCEMENT_TEXT_FIELD_LABELS
from routes.case_management_parts.update_utils import MEETING_TEXT_FIELD_LABELS
from routes.case_management_parts.update_utils import clean_service_types
from routes.case_management_parts.update_utils import display_label
from routes.case_management_parts.update_utils import parse_grit
from routes.case_management_parts.update_utils import parse_quantity
from routes.case_management_parts.update_utils import yes_no_to_int


def _get_resident_and_enrollment_in_scope(resident_id: int, shelter: str):
    ph = placeholder()

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
        return None, None

    enrollment = fetch_current_enrollment_for_resident(resident_id, columns="id")
    return resident, enrollment


def add_case_note_view(resident_id: int):
    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    staff_user_id = session.get("staff_user_id")
    ph = placeholder()

    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    resident, enrollment = _get_resident_and_enrollment_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

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
    setbacks_or_incidents = (request.form.get("setbacks_or_incidents") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()
    next_appointment = (request.form.get("next_appointment") or "").strip()
    overall_summary = (request.form.get("overall_summary") or "").strip()
    ready_for_next_level = yes_no_to_int(request.form.get("ready_for_next_level"))
    recommended_next_level = (request.form.get("recommended_next_level") or "").strip()
    blocker_reason = (request.form.get("blocker_reason") or "").strip()
    override_or_exception = (request.form.get("override_or_exception") or "").strip()
    staff_review_note = (request.form.get("staff_review_note") or "").strip()

    updated_grit_raw = (request.form.get("updated_grit") or "").strip()
    updated_grit = parse_grit(updated_grit_raw)
    parenting_class_completed = yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = clean_service_types(request.form.getlist("service_type"))
    need_updates = collect_need_updates(request.form)

    if updated_grit_raw and updated_grit is None:
        flash("Updated grit must be a whole number between 0 and 100.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not meeting_date:
        flash("Meeting date is required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    service_date = meeting_date

    has_structured_progress = (
        updated_grit is not None
        or parenting_class_completed is not None
        or warrants_or_fines_paid is not None
        or ready_for_next_level is not None
        or bool(recommended_next_level)
        or bool(blocker_reason)
        or bool(override_or_exception)
        or bool(staff_review_note)
        or bool(service_types)
        or bool(need_updates)
    )

    if (
        not notes
        and not progress_notes
        and not setbacks_or_incidents
        and not action_items
        and not next_appointment
        and not overall_summary
        and not has_structured_progress
    ):
        flash(
            "Enter notes, progress notes, setbacks or incidents, action items, next appointment, meeting summary, advancement review details, structured progress, need resolutions, or at least one service.",
            "error",
        )
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    try:
        with db_transaction():
            changed_needs = apply_need_updates(enrollment_id, int(staff_user_id), need_updates)

            note = db_fetchone(
                f"""
                INSERT INTO case_manager_updates
                (
                    enrollment_id,
                    staff_user_id,
                    meeting_date,
                    notes,
                    progress_notes,
                    setbacks_or_incidents,
                    action_items,
                    next_appointment,
                    overall_summary,
                    updated_grit,
                    parenting_class_completed,
                    warrants_or_fines_paid,
                    ready_for_next_level,
                    recommended_next_level,
                    blocker_reason,
                    override_or_exception,
                    staff_review_note,
                    created_at,
                    updated_at
                )
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                RETURNING id
                """,
                (
                    enrollment_id,
                    staff_user_id,
                    meeting_date,
                    notes or None,
                    progress_notes or None,
                    setbacks_or_incidents or None,
                    action_items or None,
                    next_appointment or None,
                    overall_summary or None,
                    updated_grit,
                    parenting_class_completed,
                    warrants_or_fines_paid,
                    ready_for_next_level,
                    recommended_next_level or None,
                    blocker_reason or None,
                    override_or_exception or None,
                    staff_review_note or None,
                    now,
                    now,
                ),
            )

            note_id = note["id"]

            for service_type in service_types:
                service_note = (request.form.get(f"service_notes_{service_type}") or "").strip()
                quantity = parse_quantity(request.form.get(f"quantity_{service_type}"))
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

            build_note_summary(
                case_manager_update_id=note_id,
                enrollment_id=enrollment_id,
                resident_id=resident_id,
                meeting_date=meeting_date,
                form=request.form,
                service_types=service_types,
                changed_needs=changed_needs,
                created_at=now,
            )

    except Exception:
        current_app.logger.exception(
            "Failed to add case note for resident_id=%s enrollment_id=%s",
            resident_id,
            enrollment_id,
        )
        flash("Unable to save the case manager update. Please try again or contact an administrator.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    flash("Case manager update saved.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id, case_note_saved=1))


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

    resident, _ = _get_resident_and_enrollment_in_scope(resident_id, shelter)

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
    setbacks_or_incidents = (request.form.get("setbacks_or_incidents") or "").strip()
    action_items = (request.form.get("action_items") or "").strip()
    next_appointment = (request.form.get("next_appointment") or "").strip()
    overall_summary = (request.form.get("overall_summary") or "").strip()
    ready_for_next_level = yes_no_to_int(request.form.get("ready_for_next_level"))
    recommended_next_level = (request.form.get("recommended_next_level") or "").strip()
    blocker_reason = (request.form.get("blocker_reason") or "").strip()
    override_or_exception = (request.form.get("override_or_exception") or "").strip()
    staff_review_note = (request.form.get("staff_review_note") or "").strip()

    updated_grit_raw = (request.form.get("updated_grit") or "").strip()
    updated_grit = parse_grit(updated_grit_raw)
    parenting_class_completed = yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = clean_service_types(request.form.getlist("service_type"))

    if updated_grit_raw and updated_grit is None:
        flash("Updated grit must be a whole number between 0 and 100.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not meeting_date:
        flash("Meeting date is required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    has_structured_progress = (
        updated_grit is not None
        or parenting_class_completed is not None
        or warrants_or_fines_paid is not None
        or ready_for_next_level is not None
        or bool(recommended_next_level)
        or bool(blocker_reason)
        or bool(override_or_exception)
        or bool(staff_review_note)
        or bool(service_types)
    )

    if (
        not notes
        and not progress_notes
        and not setbacks_or_incidents
        and not action_items
        and not next_appointment
        and not overall_summary
        and not has_structured_progress
    ):
        flash(
            "Enter notes, progress notes, setbacks or incidents, action items, next appointment, meeting summary, advancement review details, structured progress, or at least one service.",
            "error",
        )
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    service_date = meeting_date
    now = utcnow_iso()

    try:
        with db_transaction():
            db_execute(
                f"""
                UPDATE case_manager_updates
                SET meeting_date = {ph},
                    notes = {ph},
                    progress_notes = {ph},
                    setbacks_or_incidents = {ph},
                    action_items = {ph},
                    next_appointment = {ph},
                    overall_summary = {ph},
                    updated_grit = {ph},
                    parenting_class_completed = {ph},
                    warrants_or_fines_paid = {ph},
                    ready_for_next_level = {ph},
                    recommended_next_level = {ph},
                    blocker_reason = {ph},
                    override_or_exception = {ph},
                    staff_review_note = {ph},
                    updated_at = {ph}
                WHERE id = {ph}
                """,
                (
                    meeting_date,
                    notes or None,
                    progress_notes or None,
                    setbacks_or_incidents or None,
                    action_items or None,
                    next_appointment or None,
                    overall_summary or None,
                    updated_grit,
                    parenting_class_completed,
                    warrants_or_fines_paid,
                    ready_for_next_level,
                    recommended_next_level or None,
                    blocker_reason or None,
                    override_or_exception or None,
                    staff_review_note or None,
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
                quantity = parse_quantity(request.form.get(f"quantity_{service_type}"))
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

            delete_summary_rows_by_group(update_id, ["service", "advancement"])

            next_sort_order = get_next_summary_sort_order(update_id)
            next_sort_order = record_service_summary(
                case_manager_update_id=update_id,
                service_types=service_types,
                form=request.form,
                created_at=now,
                starting_sort_order=next_sort_order,
            )

            record_snapshot_change_group(
                case_manager_update_id=update_id,
                change_group="advancement",
                previous_snapshot=load_previous_snapshot_map(
                    get_previous_note_id(note["enrollment_id"], update_id, meeting_date),
                    "advancement",
                ),
                current_snapshot={
                    "setbacks_or_incidents": setbacks_or_incidents,
                    "ready_for_next_level": display_label("yes" if ready_for_next_level == 1 else "no") if ready_for_next_level is not None else "",
                    "recommended_next_level": recommended_next_level,
                    "blocker_reason": blocker_reason,
                    "override_or_exception": override_or_exception,
                    "staff_review_note": staff_review_note,
                },
                label_map={
                    **MEETING_TEXT_FIELD_LABELS,
                    **ADVANCEMENT_BOOL_FIELD_LABELS,
                    **ADVANCEMENT_TEXT_FIELD_LABELS,
                },
                added_label="",
                removed_label="",
                updated_label="",
                created_at=now,
                starting_sort_order=next_sort_order,
            )

    except Exception:
        current_app.logger.exception(
            "Failed to edit case note update_id=%s resident_id=%s",
            update_id,
            resident_id,
        )
        flash("Unable to update the case note. Please try again or contact an administrator.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    flash("Case note updated.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))
