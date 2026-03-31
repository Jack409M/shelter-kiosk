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
from routes.case_management_parts.needs import normalize_need_status


ALLOWED_SERVICE_TYPES = {
    "Counseling",
    "Dental",
    "Vision",
    "Legal Assistance",
    "Transportation",
    "Daycare",
    "Other",
}


EMPLOYMENT_FIELD_LABELS = {
    "employment_status_current": "Employment Status",
    "employment_type_current": "Employment Type",
    "employer_name": "Employer",
    "supervisor_name": "Supervisor Name",
    "supervisor_phone": "Supervisor Phone",
    "monthly_income": "Monthly Income",
    "unemployment_reason": "Unemployment Reason",
}


SOBRIETY_FIELD_LABELS = {
    "sobriety_date": "Sobriety Date",
    "drug_of_choice": "Drug of Choice",
    "treatment_graduation_date": "Treatment Graduation Date",
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


def _parse_grit(value: str | None):
    value = (value or "").strip()
    if not value:
        return None
    try:
        grit_value = int(value)
    except ValueError:
        return None
    if grit_value < 0 or grit_value > 100:
        return None
    return grit_value


def _display_label(value: str | None) -> str:
    if not value:
        return "—"
    return value.replace("_", " ").strip().title()


def _display_quantity_unit(quantity, unit: str | None) -> str:
    if quantity is None and not unit:
        return "—"
    if quantity is None:
        return (unit or "").strip() or "—"

    unit_clean = (unit or "").strip()
    if not unit_clean:
        return str(quantity)

    return f"{quantity} {unit_clean}"


def _clean_value(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _insert_summary_row(
    case_manager_update_id: int,
    change_group: str,
    change_type: str,
    item_key: str | None,
    item_label: str | None,
    old_value: str | None,
    new_value: str | None,
    detail: str | None,
    sort_order: int,
    created_at: str,
) -> None:
    ph = placeholder()

    db_execute(
        f"""
        INSERT INTO case_manager_update_summary
        (
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order,
            created_at
        )
        VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """,
        (
            case_manager_update_id,
            change_group,
            change_type,
            item_key,
            item_label,
            old_value,
            new_value,
            detail,
            sort_order,
            created_at,
        ),
    )


def _delete_summary_rows_by_group(case_manager_update_id: int, change_groups: list[str]) -> None:
    if not change_groups:
        return

    ph = placeholder()
    group_placeholders = ",".join([ph] * len(change_groups))

    db_execute(
        f"""
        DELETE FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
          AND change_group IN ({group_placeholders})
        """,
        (case_manager_update_id, *change_groups),
    )


def _get_next_summary_sort_order(case_manager_update_id: int) -> int:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT COALESCE(MAX(sort_order), -1) AS max_sort_order
        FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
        """,
        (case_manager_update_id,),
    )

    if not row:
        return 0

    max_sort_order = row["max_sort_order"]
    if max_sort_order is None:
        return 0

    return int(max_sort_order) + 1


def _get_previous_note_id(
    enrollment_id: int,
    current_note_id: int,
    current_meeting_date: str | None,
) -> int | None:
    ph = placeholder()

    if current_meeting_date:
        row = db_fetchone(
            f"""
            SELECT id
            FROM case_manager_updates
            WHERE enrollment_id = {ph}
              AND (
                    meeting_date < {ph}
                    OR (meeting_date = {ph} AND id < {ph})
                  )
            ORDER BY meeting_date DESC, id DESC
            LIMIT 1
            """,
            (enrollment_id, current_meeting_date, current_meeting_date, current_note_id),
        )
        return row["id"] if row else None

    row = db_fetchone(
        f"""
        SELECT id
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
          AND id < {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (enrollment_id, current_note_id),
    )

    return row["id"] if row else None


def _load_previous_snapshot_map(previous_note_id: int | None, change_group: str) -> dict[str, str]:
    if not previous_note_id:
        return {}

    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT item_key, detail
        FROM case_manager_update_summary
        WHERE case_manager_update_id = {ph}
          AND change_group = {ph}
          AND change_type = 'snapshot'
        ORDER BY sort_order ASC, id ASC
        """,
        (previous_note_id, change_group),
    )

    snapshot_map: dict[str, str] = {}

    for row in rows:
        item_key = row["item_key"] or ""
        snapshot_map[item_key] = row["detail"] or ""

    return snapshot_map


def _current_open_needs(enrollment_id: int) -> list[dict]:
    ph = placeholder()

    return db_fetchall(
        f"""
        SELECT
            need_key,
            need_label,
            resolution_note
        FROM resident_needs
        WHERE enrollment_id = {ph}
          AND status = 'open'
        ORDER BY need_label ASC, id ASC
        """,
        (enrollment_id,),
    )


def _collect_need_updates(form) -> list[dict]:
    updates: list[dict] = []

    for key in form.keys():
        if not key.startswith("need_status_"):
            continue

        need_key = key.removeprefix("need_status_")
        status = normalize_need_status(form.get(key))
        if status not in {"addressed", "not_applicable"}:
            continue

        resolution_note = (form.get(f"need_note_{need_key}") or "").strip()

        updates.append(
            {
                "need_key": need_key,
                "status": status,
                "resolution_note": resolution_note,
            }
        )

    return updates


def _apply_need_updates(
    enrollment_id: int,
    staff_user_id: int,
    need_updates: list[dict],
) -> list[dict]:
    if not need_updates:
        return []

    ph = placeholder()
    now = utcnow_iso()

    open_needs = db_fetchall(
        f"""
        SELECT
            id,
            need_key,
            need_label
        FROM resident_needs
        WHERE enrollment_id = {ph}
          AND status = 'open'
        ORDER BY need_label ASC, id ASC
        """,
        (enrollment_id,),
    )

    open_needs_by_key = {row["need_key"]: row for row in open_needs}
    changed_needs: list[dict] = []

    for update in need_updates:
        need = open_needs_by_key.get(update["need_key"])
        if not need:
            continue

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
                update["status"],
                update["resolution_note"] or None,
                now,
                staff_user_id,
                now,
                need["id"],
            ),
        )

        changed_needs.append(
            {
                "need_key": need["need_key"],
                "need_label": need["need_label"],
                "status": update["status"],
                "resolution_note": update["resolution_note"],
            }
        )

    return changed_needs


def _get_current_children_snapshot(resident_id: int) -> dict[str, str]:
    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            id,
            child_name,
            birth_year,
            relationship,
            living_status
        FROM resident_children
        WHERE resident_id = {ph}
          AND is_active = TRUE
        ORDER BY id ASC
        """,
        (resident_id,),
    )

    snapshot: dict[str, str] = {}

    for row in rows:
        child_id = str(row["id"])
        child_name = _clean_value(row["child_name"]) or "Unnamed Child"
        birth_year = _clean_value(row["birth_year"])
        relationship = _display_label(row.get("relationship"))
        living_status = _display_label(row.get("living_status"))

        parts = [child_name]
        if birth_year:
            parts.append(f"Birth Year {birth_year}")
        if relationship != "—":
            parts.append(relationship)
        if living_status != "—":
            parts.append(living_status)

        snapshot[child_id] = " | ".join(parts)

    return snapshot


def _get_current_medication_snapshot(resident_id: int) -> dict[str, str]:
    ph = placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            id,
            medication_name,
            dosage,
            frequency,
            purpose,
            prescribed_by
        FROM resident_medications
        WHERE resident_id = {ph}
          AND is_active = TRUE
        ORDER BY id ASC
        """,
        (resident_id,),
    )

    snapshot: dict[str, str] = {}

    for row in rows:
        med_id = str(row["id"])
        medication_name = _clean_value(row["medication_name"]) or "Medication"
        parts = [medication_name]

        dosage = _clean_value(row.get("dosage"))
        frequency = _clean_value(row.get("frequency"))
        purpose = _clean_value(row.get("purpose"))
        prescribed_by = _clean_value(row.get("prescribed_by"))

        if dosage:
            parts.append(dosage)
        if frequency:
            parts.append(frequency)
        if purpose:
            parts.append(f"Purpose: {purpose}")
        if prescribed_by:
            parts.append(f"Prescribed by: {prescribed_by}")

        snapshot[med_id] = " | ".join(parts)

    return snapshot


def _get_current_employment_snapshot(resident_id: int) -> dict[str, str]:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            employment_status_current,
            employment_type_current,
            employer_name,
            supervisor_name,
            supervisor_phone,
            monthly_income,
            unemployment_reason
        FROM residents
        WHERE id = {ph}
        """,
        (resident_id,),
    )

    if not row:
        return {key: "" for key in EMPLOYMENT_FIELD_LABELS}

    snapshot: dict[str, str] = {}

    for field_name in EMPLOYMENT_FIELD_LABELS:
        value = row.get(field_name)
        if field_name in {"employment_status_current", "employment_type_current"}:
            snapshot[field_name] = _display_label(value) if value else ""
        else:
            snapshot[field_name] = _clean_value(value)

    return snapshot


def _get_current_sobriety_snapshot(resident_id: int) -> dict[str, str]:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            sobriety_date,
            drug_of_choice,
            treatment_graduation_date
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    )

    if not row:
        return {key: "" for key in SOBRIETY_FIELD_LABELS}

    snapshot: dict[str, str] = {}

    for field_name in SOBRIETY_FIELD_LABELS:
        value = row.get(field_name)
        if field_name == "drug_of_choice":
            snapshot[field_name] = _display_label(value) if value else ""
        else:
            snapshot[field_name] = _clean_value(value)

    return snapshot


def _record_snapshot_change_group(
    case_manager_update_id: int,
    change_group: str,
    previous_snapshot: dict[str, str],
    current_snapshot: dict[str, str],
    label_map: dict[str, str] | None,
    added_label: str,
    removed_label: str,
    updated_label: str,
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    all_keys = sorted(set(previous_snapshot.keys()) | set(current_snapshot.keys()), key=lambda x: str(x))

    for item_key in all_keys:
        old_value = previous_snapshot.get(item_key, "")
        new_value = current_snapshot.get(item_key, "")

        if old_value == new_value:
            continue

        item_label = label_map[item_key] if label_map and item_key in label_map else item_key

        if old_value and not new_value:
            change_type = "removed"
            display_label = removed_label if not label_map else item_label
            detail = old_value
        elif not old_value and new_value:
            change_type = "added"
            display_label = added_label if not label_map else item_label
            detail = new_value
        else:
            change_type = "updated"
            display_label = updated_label if not label_map else item_label
            detail = new_value

        _insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group=change_group,
            change_type=change_type,
            item_key=item_key,
            item_label=display_label,
            old_value=old_value or None,
            new_value=new_value or None,
            detail=detail or None,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    for item_key in sorted(current_snapshot.keys(), key=lambda x: str(x)):
        _insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group=change_group,
            change_type="snapshot",
            item_key=item_key,
            item_label=(label_map[item_key] if label_map and item_key in label_map else item_key),
            old_value=None,
            new_value=None,
            detail=current_snapshot.get(item_key, ""),
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    return sort_order


def _record_service_summary(
    case_manager_update_id: int,
    service_types: list[str],
    form,
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    for service_type in service_types:
        service_note = (form.get(f"service_notes_{service_type}") or "").strip()
        quantity = _parse_quantity(form.get(f"quantity_{service_type}"))
        unit = (form.get(f"unit_{service_type}") or "").strip()
        quantity_display = _display_quantity_unit(quantity, unit or None)

        detail_parts = []
        if quantity_display != "—":
            detail_parts.append(quantity_display)
        if service_note:
            detail_parts.append(service_note)

        detail = " | ".join(detail_parts) if detail_parts else service_type

        _insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group="service",
            change_type="provided",
            item_key=service_type.lower().replace(" ", "_"),
            item_label=service_type,
            old_value=None,
            new_value=None,
            detail=detail,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    return sort_order


def _record_need_summary(
    case_manager_update_id: int,
    changed_needs: list[dict],
    outstanding_needs: list[dict],
    created_at: str,
    starting_sort_order: int = 0,
) -> int:
    sort_order = starting_sort_order

    for need in changed_needs:
        status = _display_label(need.get("status"))
        resolution_note = _clean_value(need.get("resolution_note"))
        detail = status
        if resolution_note:
            detail = f"{status} | {resolution_note}"

        _insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group="need_addressed",
            change_type=need.get("status") or "addressed",
            item_key=need.get("need_key"),
            item_label=need.get("need_label"),
            old_value="Open",
            new_value=status,
            detail=detail,
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    for need in outstanding_needs:
        _insert_summary_row(
            case_manager_update_id=case_manager_update_id,
            change_group="need_outstanding",
            change_type="open",
            item_key=need.get("need_key"),
            item_label=need.get("need_label"),
            old_value=None,
            new_value="Open",
            detail=need.get("need_label"),
            sort_order=sort_order,
            created_at=created_at,
        )
        sort_order += 1

    return sort_order


def _build_note_summary(
    case_manager_update_id: int,
    enrollment_id: int,
    resident_id: int,
    meeting_date: str | None,
    form,
    service_types: list[str],
    changed_needs: list[dict],
    created_at: str,
) -> None:
    previous_note_id = _get_previous_note_id(
        enrollment_id=enrollment_id,
        current_note_id=case_manager_update_id,
        current_meeting_date=meeting_date,
    )

    previous_child_snapshot = _load_previous_snapshot_map(previous_note_id, "child")
    previous_medication_snapshot = _load_previous_snapshot_map(previous_note_id, "medication")
    previous_employment_snapshot = _load_previous_snapshot_map(previous_note_id, "employment")
    previous_sobriety_snapshot = _load_previous_snapshot_map(previous_note_id, "sobriety")

    current_child_snapshot = _get_current_children_snapshot(resident_id)
    current_medication_snapshot = _get_current_medication_snapshot(resident_id)
    current_employment_snapshot = _get_current_employment_snapshot(resident_id)
    current_sobriety_snapshot = _get_current_sobriety_snapshot(resident_id)
    current_outstanding_needs = _current_open_needs(enrollment_id)

    sort_order = 0

    sort_order = _record_service_summary(
        case_manager_update_id=case_manager_update_id,
        service_types=service_types,
        form=form,
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = _record_need_summary(
        case_manager_update_id=case_manager_update_id,
        changed_needs=changed_needs,
        outstanding_needs=current_outstanding_needs,
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = _record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="child",
        previous_snapshot=previous_child_snapshot,
        current_snapshot=current_child_snapshot,
        label_map=None,
        added_label="Child Added",
        removed_label="Child Removed",
        updated_label="Child Updated",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = _record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="medication",
        previous_snapshot=previous_medication_snapshot,
        current_snapshot=current_medication_snapshot,
        label_map=None,
        added_label="Medication Added",
        removed_label="Medication Removed",
        updated_label="Medication Updated",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    sort_order = _record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="employment",
        previous_snapshot=previous_employment_snapshot,
        current_snapshot=current_employment_snapshot,
        label_map=EMPLOYMENT_FIELD_LABELS,
        added_label="",
        removed_label="",
        updated_label="",
        created_at=created_at,
        starting_sort_order=sort_order,
    )

    _record_snapshot_change_group(
        case_manager_update_id=case_manager_update_id,
        change_group="sobriety",
        previous_snapshot=previous_sobriety_snapshot,
        current_snapshot=current_sobriety_snapshot,
        label_map=SOBRIETY_FIELD_LABELS,
        added_label="",
        removed_label="",
        updated_label="",
        created_at=created_at,
        starting_sort_order=sort_order,
    )


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
    action_items = (request.form.get("action_items") or "").strip()
    next_appointment = (request.form.get("next_appointment") or "").strip()
    overall_summary = (request.form.get("overall_summary") or "").strip()

    updated_grit_raw = (request.form.get("updated_grit") or "").strip()
    updated_grit = _parse_grit(updated_grit_raw)
    parenting_class_completed = _yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = _yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = _clean_service_types(request.form.getlist("service_type"))
    need_updates = _collect_need_updates(request.form)

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
        or bool(service_types)
        or bool(need_updates)
    )

    if (
        not notes
        and not progress_notes
        and not action_items
        and not next_appointment
        and not overall_summary
        and not has_structured_progress
    ):
        flash(
            "Enter notes, progress notes, action items, next appointment, meeting summary, structured progress, need resolutions, or at least one service.",
            "error",
        )
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    now = utcnow_iso()

    try:
        with db_transaction():
            changed_needs = _apply_need_updates(enrollment_id, int(staff_user_id), need_updates)

            note = db_fetchone(
                f"""
                INSERT INTO case_manager_updates
                (
                    enrollment_id,
                    staff_user_id,
                    meeting_date,
                    notes,
                    progress_notes,
                    action_items,
                    next_appointment,
                    overall_summary,
                    updated_grit,
                    parenting_class_completed,
                    warrants_or_fines_paid,
                    created_at,
                    updated_at
                )
                VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
                RETURNING id
                """,
                (
                    enrollment_id,
                    staff_user_id,
                    meeting_date,
                    notes or None,
                    progress_notes or None,
                    action_items or None,
                    next_appointment or None,
                    overall_summary or None,
                    updated_grit,
                    parenting_class_completed,
                    warrants_or_fines_paid,
                    now,
                    now,
                ),
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

            _build_note_summary(
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
    action_items = (request.form.get("action_items") or "").strip()
    next_appointment = (request.form.get("next_appointment") or "").strip()
    overall_summary = (request.form.get("overall_summary") or "").strip()

    updated_grit_raw = (request.form.get("updated_grit") or "").strip()
    updated_grit = _parse_grit(updated_grit_raw)
    parenting_class_completed = _yes_no_to_int(request.form.get("parenting_class_completed"))
    warrants_or_fines_paid = _yes_no_to_int(request.form.get("warrants_or_fines_paid"))

    service_types = _clean_service_types(request.form.getlist("service_type"))

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
        or bool(service_types)
    )

    if (
        not notes
        and not progress_notes
        and not action_items
        and not next_appointment
        and not overall_summary
        and not has_structured_progress
    ):
        flash(
            "Enter notes, progress notes, action items, next appointment, meeting summary, structured progress, or at least one service.",
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
                    action_items = {ph},
                    next_appointment = {ph},
                    overall_summary = {ph},
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
                    next_appointment or None,
                    overall_summary or None,
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

            _delete_summary_rows_by_group(update_id, ["service"])

            next_sort_order = _get_next_summary_sort_order(update_id)
            _record_service_summary(
                case_manager_update_id=update_id,
                service_types=service_types,
                form=request.form,
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
