from __future__ import annotations

from typing import Any

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.db import DbRow, db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    normalize_shelter_name,
    placeholder,
)
from routes.case_management_parts.update_needs import apply_need_updates
from routes.case_management_parts.update_note_helpers import (
    collect_note_form_values,
    service_form_payloads,
)
from routes.case_management_parts.update_note_loaders import (
    build_edit_service_maps,
    get_resident_and_enrollment_in_scope,
    load_note_for_edit,
    load_services_for_note,
)
from routes.case_management_parts.update_note_services import insert_client_services
from routes.case_management_parts.update_note_validation import validate_note_values
from routes.case_management_parts.update_snapshots import load_previous_snapshot_map
from routes.case_management_parts.update_summary import build_note_summary, get_previous_note_id
from routes.case_management_parts.update_summary_recorders import (
    record_service_summary,
    record_snapshot_change_group,
)
from routes.case_management_parts.update_summary_rows import (
    delete_summary_rows_by_group,
    get_next_summary_sort_order,
)
from routes.case_management_parts.update_utils import (
    ADVANCEMENT_BOOL_FIELD_LABELS,
    ADVANCEMENT_TEXT_FIELD_LABELS,
    MEETING_TEXT_FIELD_LABELS,
    display_label,
)

RedirectResponse = Any
TemplateResponse = Any
RouteResponse = RedirectResponse | TemplateResponse

_NOTE_INSERT_COLUMNS = (
    "enrollment_id",
    "staff_user_id",
    "meeting_date",
    "notes",
    "progress_notes",
    "setbacks_or_incidents",
    "action_items",
    "next_appointment",
    "overall_summary",
    "updated_grit",
    "parenting_class_completed",
    "warrants_or_fines_paid",
    "ready_for_next_level",
    "recommended_next_level",
    "blocker_reason",
    "override_or_exception",
    "staff_review_note",
    "created_at",
    "updated_at",
)


def _current_shelter() -> str:
    return normalize_shelter_name(session.get("shelter"))


def _current_staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        current_app.logger.warning(
            "Invalid staff_user_id in session during case note flow: %r",
            raw_staff_user_id,
        )
        return None


def _redirect_resident_case(resident_id: int) -> RedirectResponse:
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


def _redirect_staff_login() -> RedirectResponse:
    return redirect(url_for("auth.staff_login"))


def _require_case_manager_access(resident_id: int) -> RedirectResponse | None:
    if case_manager_allowed():
        return None

    flash("Case manager access required.", "error")
    return _redirect_resident_case(resident_id)


def _require_staff_user_session() -> int | None:
    staff_user_id = _current_staff_user_id()
    if staff_user_id is not None:
        return staff_user_id

    flash("Your session is missing a staff user id. Please log in again.", "error")
    return None


def _require_active_enrollment_id(
    resident_id: int,
    shelter: str,
) -> tuple[DbRow | None, int | None]:
    resident, enrollment = get_resident_and_enrollment_in_scope(resident_id, shelter)
    if not resident:
        return None, None

    if not enrollment:
        return resident, None

    enrollment_id_value = enrollment.get("id")
    if not isinstance(enrollment_id_value, int):
        current_app.logger.error(
            "Enrollment row missing integer id for resident_id=%s: %r",
            resident_id,
            enrollment,
        )
        return resident, None

    return resident, enrollment_id_value


def _none_if_blank(value: object) -> object:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return value


def _case_note_insert_params(
    *,
    enrollment_id: int,
    staff_user_id: int,
    values: dict[str, Any],
    now: str,
) -> tuple[Any, ...]:
    return (
        enrollment_id,
        staff_user_id,
        values["meeting_date"],
        _none_if_blank(values["notes"]),
        _none_if_blank(values["progress_notes"]),
        _none_if_blank(values["setbacks_or_incidents"]),
        _none_if_blank(values["action_items"]),
        None,
        _none_if_blank(values["overall_summary"]),
        values["updated_grit"],
        values["parenting_class_completed"],
        values["warrants_or_fines_paid"],
        values["ready_for_next_level"],
        _none_if_blank(values["recommended_next_level"]),
        _none_if_blank(values["blocker_reason"]),
        _none_if_blank(values["override_or_exception"]),
        _none_if_blank(values["staff_review_note"]),
        now,
        now,
    )


def _case_note_update_params(
    *,
    update_id: int,
    values: dict[str, Any],
    now: str,
) -> tuple[Any, ...]:
    return (
        values["meeting_date"],
        _none_if_blank(values["notes"]),
        _none_if_blank(values["progress_notes"]),
        _none_if_blank(values["setbacks_or_incidents"]),
        _none_if_blank(values["action_items"]),
        None,
        _none_if_blank(values["overall_summary"]),
        values["updated_grit"],
        values["parenting_class_completed"],
        values["warrants_or_fines_paid"],
        values["ready_for_next_level"],
        _none_if_blank(values["recommended_next_level"]),
        _none_if_blank(values["blocker_reason"]),
        _none_if_blank(values["override_or_exception"]),
        _none_if_blank(values["staff_review_note"]),
        now,
        update_id,
    )


def _insert_case_note(
    *,
    enrollment_id: int,
    staff_user_id: int,
    values: dict[str, Any],
    now: str,
) -> int:
    ph = placeholder()
    insert_columns_sql = ",\n                    ".join(_NOTE_INSERT_COLUMNS)
    values_sql = ",".join([ph] * len(_NOTE_INSERT_COLUMNS))

    note = db_fetchone(
        f"""
        INSERT INTO case_manager_updates
        (
            {insert_columns_sql}
        )
        VALUES ({values_sql})
        RETURNING id
        """,
        _case_note_insert_params(
            enrollment_id=enrollment_id,
            staff_user_id=staff_user_id,
            values=values,
            now=now,
        ),
    )

    if note is None:
        raise RuntimeError(f"Case note insert returned no row for enrollment_id={enrollment_id}")

    note_id = note.get("id")
    if not isinstance(note_id, int):
        raise RuntimeError(f"Case note insert returned invalid id payload: {note!r}")

    return note_id


def _update_case_note(
    *,
    update_id: int,
    values: dict[str, Any],
    now: str,
) -> None:
    ph = placeholder()

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
        _case_note_update_params(update_id=update_id, values=values, now=now),
    )


def _replace_note_services(
    *,
    enrollment_id: int,
    note_id: int,
    service_date: str,
    service_payloads_list: list[dict[str, Any]],
    now: str,
) -> None:
    ph = placeholder()

    db_execute(
        f"""
        DELETE FROM client_services
        WHERE case_manager_update_id = {ph}
        """,
        (note_id,),
    )

    insert_client_services(
        enrollment_id=enrollment_id,
        note_id=note_id,
        service_date=service_date,
        services=service_payloads_list,
        now=now,
    )


def _record_edit_note_summary(
    *,
    note: DbRow,
    update_id: int,
    values: dict[str, Any],
    now: str,
) -> None:
    delete_summary_rows_by_group(update_id, ["service", "advancement"])

    next_sort_order = get_next_summary_sort_order(update_id)
    next_sort_order = record_service_summary(
        case_manager_update_id=update_id,
        service_types=values["service_types"],
        form=request.form,
        created_at=now,
        starting_sort_order=next_sort_order,
    )

    enrollment_id = note.get("enrollment_id")
    if not isinstance(enrollment_id, int):
        raise RuntimeError(
            f"Existing note missing integer enrollment_id for update_id={update_id}: {note!r}"
        )

    previous_note_id = get_previous_note_id(
        enrollment_id,
        update_id,
        values["meeting_date"],
    )

    record_snapshot_change_group(
        case_manager_update_id=update_id,
        change_group="advancement",
        previous_snapshot=load_previous_snapshot_map(previous_note_id, "advancement"),
        current_snapshot={
            "setbacks_or_incidents": values["setbacks_or_incidents"],
            "ready_for_next_level": (
                display_label("yes" if values["ready_for_next_level"] == 1 else "no")
                if values["ready_for_next_level"] is not None
                else ""
            ),
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


def _handle_case_note_write_failure(
    *,
    resident_id: int,
    log_message: str,
    flash_message: str,
    **log_context: object,
) -> RedirectResponse:
    current_app.logger.exception(log_message, *log_context.values())
    flash(flash_message, "error")
    return _redirect_resident_case(resident_id)


def add_case_note_view(resident_id: int) -> RouteResponse:
    init_db()

    denied = _require_case_manager_access(resident_id)
    if denied is not None:
        return denied

    staff_user_id = _require_staff_user_session()
    if staff_user_id is None:
        return _redirect_staff_login()

    shelter = _current_shelter()
    resident, enrollment_id = _require_active_enrollment_id(resident_id, shelter)

    if resident is None:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    if enrollment_id is None:
        flash("Resident does not have an active enrollment record yet.", "error")
        return _redirect_resident_case(resident_id)

    values = collect_note_form_values(request.form)
    validation_error = validate_note_values(
        values,
        resident_id=resident_id,
        include_needs=True,
    )
    if validation_error is not None:
        return validation_error

    service_date = values["meeting_date"]
    now = utcnow_iso()
    service_payloads_list = service_form_payloads(request.form, values["service_types"])

    try:
        with db_transaction():
            changed_needs = apply_need_updates(
                enrollment_id,
                staff_user_id,
                values["need_updates"],
            )

            note_id = _insert_case_note(
                enrollment_id=enrollment_id,
                staff_user_id=staff_user_id,
                values=values,
                now=now,
            )

            insert_client_services(
                enrollment_id=enrollment_id,
                note_id=note_id,
                service_date=service_date,
                services=service_payloads_list,
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
        return _handle_case_note_write_failure(
            resident_id=resident_id,
            log_message="Failed to add case note for resident_id=%s enrollment_id=%s",
            flash_message=(
                "Unable to save the case manager update. Please try again or contact an administrator."
            ),
            resident_id_log=resident_id,
            enrollment_id_log=enrollment_id,
        )

    flash("Case manager update saved.", "success")
    return redirect(
        url_for(
            "case_management.resident_case",
            resident_id=resident_id,
            case_note_saved=1,
        )
    )


def edit_case_note_view(resident_id: int, update_id: int) -> RouteResponse:
    init_db()

    denied = _require_case_manager_access(resident_id)
    if denied is not None:
        return denied

    staff_user_id = _require_staff_user_session()
    if staff_user_id is None:
        flash("Session expired. Please log in again.", "error")
        return _redirect_staff_login()

    shelter = _current_shelter()
    resident, _ = get_resident_and_enrollment_in_scope(resident_id, shelter)

    if resident is None:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    note = load_note_for_edit(update_id, shelter)
    if note is None:
        flash("Note not found.", "error")
        return _redirect_resident_case(resident_id)

    note_resident_id = note.get("resident_id")
    if note_resident_id != resident_id:
        flash("Invalid note access.", "error")
        return _redirect_resident_case(resident_id)

    if request.method == "GET":
        services = load_services_for_note(update_id)
        service_maps = build_edit_service_maps(services)

        return render_template(
            "case_management/edit_case_note.html",
            resident=resident,
            note=note,
            selected_services=service_maps["selected_services"],
            service_notes_map=service_maps["service_notes_map"],
            service_quantity_map=service_maps["service_quantity_map"],
            service_unit_map=service_maps["service_unit_map"],
        )

    values = collect_note_form_values(request.form)
    validation_error = validate_note_values(
        values,
        resident_id=resident_id,
        include_needs=False,
    )
    if validation_error is not None:
        return validation_error

    note_enrollment_id = note.get("enrollment_id")
    if not isinstance(note_enrollment_id, int):
        current_app.logger.error(
            "Case note edit aborted because note enrollment_id was invalid. update_id=%s note=%r",
            update_id,
            note,
        )
        flash("Unable to update the case note because the enrollment record is invalid.", "error")
        return _redirect_resident_case(resident_id)

    service_date = values["meeting_date"]
    now = utcnow_iso()
    service_payloads_list = service_form_payloads(request.form, values["service_types"])

    try:
        with db_transaction():
            _update_case_note(
                update_id=update_id,
                values=values,
                now=now,
            )

            _replace_note_services(
                enrollment_id=note_enrollment_id,
                note_id=update_id,
                service_date=service_date,
                service_payloads_list=service_payloads_list,
                now=now,
            )

            _record_edit_note_summary(
                note=note,
                update_id=update_id,
                values=values,
                now=now,
            )

    except Exception:
        return _handle_case_note_write_failure(
            resident_id=resident_id,
            log_message="Failed to edit case note update_id=%s resident_id=%s",
            flash_message=(
                "Unable to update the case note. Please try again or contact an administrator."
            ),
            update_id_log=update_id,
            resident_id_log=resident_id,
        )

    flash("Case note updated.", "success")
    return _redirect_resident_case(resident_id)
