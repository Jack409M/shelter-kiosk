from __future__ import annotations

from core.db import db_fetchall, db_fetchone
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.update_utils import ADVANCEMENT_BOOL_FIELD_LABELS
from routes.case_management_parts.update_utils import ADVANCEMENT_TEXT_FIELD_LABELS
from routes.case_management_parts.update_utils import EMPLOYMENT_FIELD_LABELS
from routes.case_management_parts.update_utils import MEETING_TEXT_FIELD_LABELS
from routes.case_management_parts.update_utils import SOBRIETY_FIELD_LABELS
from routes.case_management_parts.update_utils import clean_value
from routes.case_management_parts.update_utils import display_label


def _join_snapshot_parts(parts: list[str]) -> str:
    cleaned = [part.strip() for part in parts if part and str(part).strip()]
    return " | ".join(cleaned)


def load_previous_snapshot_map(previous_note_id: int | None, change_group: str) -> dict[str, str]:
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


def get_current_children_snapshot(resident_id: int) -> dict[str, str]:
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
        child_name = clean_value(row["child_name"]) or "Unnamed child"
        birth_year = clean_value(row["birth_year"])
        relationship = display_label(row.get("relationship"))
        living_status = display_label(row.get("living_status"))

        parts = [child_name]
        if birth_year:
            parts.append(f"Birth year {birth_year}")
        if relationship != "—":
            parts.append(relationship)
        if living_status != "—":
            parts.append(living_status)

        snapshot[child_id] = _join_snapshot_parts(parts)

    return snapshot


def get_current_medication_snapshot(resident_id: int) -> dict[str, str]:
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
        medication_name = clean_value(row["medication_name"]) or "Medication"
        dosage = clean_value(row.get("dosage"))
        frequency = clean_value(row.get("frequency"))
        purpose = clean_value(row.get("purpose"))
        prescribed_by = clean_value(row.get("prescribed_by"))

        parts = [medication_name]
        if dosage:
            parts.append(dosage)
        if frequency:
            parts.append(frequency)
        if purpose:
            parts.append(f"Purpose: {purpose}")
        if prescribed_by:
            parts.append(f"Prescribed by: {prescribed_by}")

        snapshot[med_id] = _join_snapshot_parts(parts)

    return snapshot


def _empty_snapshot(field_labels: dict[str, str]) -> dict[str, str]:
    return {key: "" for key in field_labels}


def get_current_employment_snapshot(resident_id: int) -> dict[str, str]:
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
            unemployment_reason,
            employment_notes
        FROM residents
        WHERE id = {ph}
        """,
        (resident_id,),
    )

    if not row:
        return _empty_snapshot(EMPLOYMENT_FIELD_LABELS)

    snapshot: dict[str, str] = {}

    for field_name in EMPLOYMENT_FIELD_LABELS:
        value = row.get(field_name)
        if field_name in {"employment_status_current", "employment_type_current"}:
            snapshot[field_name] = display_label(value) if value else ""
        else:
            snapshot[field_name] = clean_value(value)

    return snapshot


def get_current_sobriety_snapshot(resident_id: int) -> dict[str, str]:
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
        return _empty_snapshot(SOBRIETY_FIELD_LABELS)

    snapshot: dict[str, str] = {}

    for field_name in SOBRIETY_FIELD_LABELS:
        snapshot[field_name] = clean_value(row.get(field_name))

    return snapshot


def get_current_advancement_snapshot(enrollment_id: int) -> dict[str, str]:
    ph = placeholder()

    row = db_fetchone(
        f"""
        SELECT
            setbacks_or_incidents,
            ready_for_next_level,
            recommended_next_level,
            blocker_reason,
            override_or_exception,
            staff_review_note
        FROM case_manager_updates
        WHERE enrollment_id = {ph}
        ORDER BY meeting_date DESC, id DESC
        LIMIT 1
        """,
        (enrollment_id,),
    )

    if not row:
        snapshot = _empty_snapshot(MEETING_TEXT_FIELD_LABELS)
        snapshot.update(_empty_snapshot(ADVANCEMENT_TEXT_FIELD_LABELS))
        snapshot.update(_empty_snapshot(ADVANCEMENT_BOOL_FIELD_LABELS))
        return snapshot

    snapshot: dict[str, str] = {}

    for field_name in MEETING_TEXT_FIELD_LABELS:
        snapshot[field_name] = clean_value(row.get(field_name))

    for field_name in ADVANCEMENT_TEXT_FIELD_LABELS:
        snapshot[field_name] = clean_value(row.get(field_name))

    for field_name in ADVANCEMENT_BOOL_FIELD_LABELS:
        value = row.get(field_name)
        if value is None:
            snapshot[field_name] = ""
        else:
            snapshot[field_name] = display_label("yes" if bool(value) else "no")

    return snapshot
