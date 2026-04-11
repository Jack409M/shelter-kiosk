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


def _clean_text(value):
    return (value or "").strip()


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _current_staff_user_id():
    return session.get("staff_user_id")


def _redirect_resident_case(resident_id: int):
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _require_case_manager_access(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return _redirect_resident_case(resident_id)
    return None


def _require_staff_user_session():
    staff_user_id = _current_staff_user_id()
    if staff_user_id:
        return staff_user_id

    flash("Your session is missing a staff user id. Please log in again.", "error")
    return None


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


def _collect_note_form_values():
    meeting_date = _clean_text(request.form.get("meeting_date"))
    notes = _clean_text(request.form.get("notes"))
    progress_notes = _clean_text(request.form.get("progress_notes"))
    setbacks_or_incidents = _clean_text(request.form.get("setbacks_or_incidents"))
    action_items = _clean_text(request.form.get("action_items"))
    overall_summary = _clean_text(request.form.get("overall_summary"))
    ready_for_next_level = yes_no_to_int(request.form.get("ready_for_next_level"))
    recommended_next_level = _clean_text(request.form.get("recommended_next_level"))
    blocker_reason = _clean_text(request.form.get("blocker_reason"))
    override_or_exception = _clean_text(request.form.get("override_or_exception"))
    staff_review_note = _clean_text(request.form.get("staff_review_note"))

    updated_grit_raw = _clean_text(request.form.get("updated_grit"))
    updated_grit = parse_grit(updated_grit_raw)
    parenting_class_completed = yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = clean_service_types(request.form.getlist("service_type"))
    need_updates = collect_need_updates(request.form)

    return {
        "meeting_date": meeting_date,
        "notes": notes,
        "progress_notes": progress_notes,
        "setbacks_or_incidents": setbacks_or_incidents,
        "action_items": action_items,
        "overall_summary": overall_summary,
        "ready_for_next_level": ready_for_next_level,
        "recommended_next_level": recommended_next_level,
        "blocker_reason": blocker_reason,
        "override_or_exception": override_or_exception,
        "staff_review_note": staff_review_note,
        "updated_grit_raw": updated_grit_raw,
        "updated_grit": updated_grit,
        "parenting_class_completed": parenting_class_completed,
        "warrants_or_fines_paid": warrants_or_fines_paid,
        "service_types": service_types,
        "need_updates": need_updates,
    }


def _has_structured_progress(values, *, include_needs: bool):
    return (
        values["updated_grit"] is not None
        or values["parenting_class_completed"] is not None
        or values["warrants_or_fines_paid"] is not None
        or values["ready_for_next_level"] is not None
        or bool(values["recommended_next_level"])
        or bool(values["blocker_reason"])
        or bool(values["override_or_exception"])
        or bool(values["staff_review_note"])
        or bool(values["service_types"])
        or (include_needs and bool(values["need_updates"]))
    )


def _validate_note_values(values, *, resident_id: int, include_needs: bool):
    if values["updated_grit_raw"] and values["updated_grit"] is None:
        flash("Updated grit must be a whole number between 0 and 100.", "error")
        return _redirect_resident_case(resident_id)

    if not values["meeting_date"]:
        flash("Meeting date is required.", "error")
        return _redirect_resident_case(resident_id)

    has_structured_progress = _has_structured_progress(values, include_needs=include_needs)

    if (
        not values["notes"]
        and not values["progress_notes"]
        and not values["setbacks_or_incidents"]
        and not values["action_items"]
        and not values["overall_summary"]
        and not has_structured_progress
    ):
        if include_needs:
            flash(
                "Enter notes, progress notes, setbacks or incidents, action items, meeting summary, advancement review details, structured progress, need resolutions, or at least one service.",
                "error",
            )
        else:
            flash(
                "Enter notes, progress notes, setbacks or incidents, action items, meeting summary, advancement review details, structured progress, or at least one service.",
                "error",
            )
        return _redirect_resident_case(resident_id)

    return None


def _service_form_payloads(service_types: list[str]) -> list[dict]:
    items: list[dict] = []

    for service_type in service_types:
        service_note = _clean_text(request.form.get(f"service_notes_{service_type}"))
        quantity = parse_quantity(request.form.get(f"quantity_{service_type}"))
        unit = _clean_text(request.form.get(f"unit_{service_type}"))

        items.append(
            {
                "service_type": service_type,
                "service_note": service_note or None,
                "quantity": quantity,
                "unit": unit or None,
            }
        )

    return items


def _insert_client_services(
    *,
    enrollment_id: int,
    note_id: int,
    service_date: str,
    services: list[dict],
    now: str,
):
    ph = placeholder()

    for service in services:
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
                service["service_type"],
                service_date,
                service["quantity"],
                service["unit"],
                service["service_note"],
                now,
                now,
            ),
        )


def _load_note_for_edit(update_id: int):
    ph = placeholder()
    return db_fetchone(
        f"""
        SELECT cmu.*, pe.resident_id
        FROM case_manager_updates cmu
        JOIN program_enrollments pe ON pe.id = cmu.enrollment_id
        WHERE cmu.id = {ph}
        """,
        (update_id,),
    )


def _load_services_for_note(update_id: int):
    ph = placeholder()
    return db_fetchall(
        f"""
        SELECT service_type, quantity, unit, notes
        FROM client_services
        WHERE case_manager_update_id = {ph}
        """,
        (update_id,),
    )


def _build_edit_service_maps(services: list[dict]):
    selected_services = []
    service_notes_map = {}
    service_quantity_map = {}
    service_unit_map = {}

    for service in services:
        service_type = service["service_type"]
        quantity = service["quantity"]
        unit = service["unit"]
        service_note = service["notes"]

        selected_services.append(service_type)
        service_notes_map[service_type] = service_note or ""
        service_quantity_map[service_type] = quantity if quantity is not None else ""
        service_unit_map[service_type] = unit or ""

    return {
        "selected_services": selected_services,
        "service_notes_map": service_notes_map,
        "service_quantity_map": service_quantity_map,
        "service_unit_map": service_unit_map,
    }


def add_case_note_view(resident_id: int):
    init_db()

    denied = _require_case_manager_access(resident_id)
    if denied is not None:
        return denied

    staff_user_id = _require_staff_user_session()
    if not staff_user_id:
        return redirect(url_for("auth.staff_login"))

    shelter = _current_shelter()
    resident, enrollment = _get_resident_and_enrollment_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment_id = enrollment["id"] if enrollment else None
    if not enrollment_id:
        flash("Resident does not have an active enrollment record yet.", "error")
        return _redirect_resident_case(resident_id)

    values = _collect_note_form_values()
    validation_error = _validate_note_values(values, resident_id=resident_id, include_needs=True)
    if validation_error is not None:
        return validation_error

    service_date = values["meeting_date"]
    now = utcnow_iso()
    service_payloads = _service_form_payloads(values["service_types"])
    ph = placeholder()

    try:
        with db_transaction():
            changed_needs = apply_need_updates(enrollment_id, int(staff_user_id), values["need_updates"])

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
                    values["meeting_date"],
                    values["notes"] or None,
                    values["progress_notes"] or None,
                    values["setbacks_or_incidents"] or None,
                    values["action_items"] or None,
                    None,
                    values["overall_summary"] or None,
                    values["updated_grit"],
                    values["parenting_class_completed"],
                    values["warrants_or_fines_paid"],
                    values["ready_for_next_level"],
                    values["recommended_next_level"] or None,
                    values["blocker_reason"] or None,
                    values["override_or_exception"] or None,
                    values["staff_review_note"] or None,
                    now,
                    now,
                ),
            )

            note_id = note["id"]

            _insert_client_services(
                enrollment_id=enrollment_id,
                note_id=note_id,
                service_date=service_date,
                services=service_payloads,
                now=now,
            )

            build_note_summary(
                case_manager_update_id=note_id,
                enrollment_id=enrollment_id,
                resident_id=resident_id,
                meeting_date=values["meeting_date"],
                form=request.form,
                service_types=values["service_types"],
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
        return _redirect_resident_case(resident_id)

    flash("Case manager update saved.", "success")
    return redirect(url_for("case_management.resident_case", resident_id=resident_id, case_note_saved=1))


def edit_case_note_view(resident_id: int, update_id: int):
    init_db()

    denied = _require_case_manager_access(resident_id)
    if denied is not None:
        return denied

    staff_user_id = _require_staff_user_session()
    if not staff_user_id:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("auth.staff_login"))

    shelter = _current_shelter()
    resident, _ = _get_resident_and_enrollment_in_scope(resident_id, shelter)

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    note = _load_note_for_edit(update_id)
    if not note:
        flash("Note not found.", "error")
        return _redirect_resident_case(resident_id)

    if note["resident_id"] != resident_id:
        flash("Invalid note access.", "error")
        return _redirect_resident_case(resident_id)

    if request.method == "GET":
        services = _load_services_for_note(update_id)
        service_maps = _build_edit_service_maps(services)

        return render_template(
            "case_management/edit_case_note.html",
            resident=resident,
            note=note,
            selected_services=service_maps["selected_services"],
            service_notes_map=service_maps["service_notes_map"],
            service_quantity_map=service_maps["service_quantity_map"],
            service_unit_map=service_maps["service_unit_map"],
        )

    values = _collect_note_form_values()
    validation_error = _validate_note_values(values, resident_id=resident_id, include_needs=False)
    if validation_error is not None:
        return validation_error

    service_date = values["meeting_date"]
    now = utcnow_iso()
    service_payloads = _service_form_payloads(values["service_types"])
    ph = placeholder()

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
                    values["meeting_date"],
                    values["notes"] or None,
                    values["progress_notes"] or None,
                    values["setbacks_or_incidents"] or None,
                    values["action_items"] or None,
                    None,
                    values["overall_summary"] or None,
                    values["updated_grit"],
                    values["parenting_class_completed"],
                    values["warrants_or_fines_paid"],
                    values["ready_for_next_level"],
                    values["recommended_next_level"] or None,
                    values["blocker_reason"] or None,
                    values["override_or_exception"] or None,
                    values["staff_review_note"] or None,
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

            _insert_client_services(
                enrollment_id=note["enrollment_id"],
                note_id=update_id,
                service_date=service_date,
                services=service_payloads,
                now=now,
            )

            delete_summary_rows_by_group(update_id, ["service", "advancement"])

            next_sort_order = get_next_summary_sort_order(update_id)
            next_sort_order = record_service_summary(
                case_manager_update_id=update_id,
                service_types=values["service_types"],
                form=request.form,
                created_at=now,
                starting_sort_order=next_sort_order,
            )

            record_snapshot_change_group(
                case_manager_update_id=update_id,
                change_group="advancement",
                previous_snapshot=load_previous_snapshot_map(
                    get_previous_note_id(note["enrollment_id"], update_id, values["meeting_date"]),
                    "advancement",
                ),
                current_snapshot={
                    "setbacks_or_incidents": values["setbacks_or_incidents"],
                    "ready_for_next_level": display_label("yes" if values["ready_for_next_level"] == 1 else "no") if values["ready_for_next_level"] is not None else "",
                    "recommended_next_level": values["recommended_next_level"],
                    "blocker_reason": values["blocker_reason"],
                    "override_or_exception": values["override_or_exception"],
                    "staff_review_note": values["staff_review_note"],
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
        return _redirect_resident_case(resident_id)

    flash("Case note updated.", "success")
    return _redirect_resident_case(resident_id)
