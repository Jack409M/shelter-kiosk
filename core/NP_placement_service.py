from __future__ import annotations

from typing import Any

from flask import g, session

from core.db import DbRow, db_execute, db_fetchone
from core.helpers import utcnow_iso


PLACEMENT_TYPE_NONE = "none"
PLACEMENT_TYPE_BED = "bed"
PLACEMENT_TYPE_APARTMENT = "apartment"


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _normalize_shelter(value: object) -> str:
    return str(value or "").strip().lower()


def _normalize_level(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _current_staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        return None


def _placement_type_for_unit(unit: DbRow | None) -> str:
    if not unit:
        return PLACEMENT_TYPE_NONE

    unit_type = str(unit.get("unit_type") or "").strip().lower()
    if unit_type == PLACEMENT_TYPE_BED:
        return PLACEMENT_TYPE_BED

    return PLACEMENT_TYPE_APARTMENT


def get_housing_unit_by_label(*, shelter: str, unit_label: str | None) -> DbRow | None:
    normalized_shelter = _normalize_shelter(shelter)
    normalized_label = str(unit_label or "").strip()
    if not normalized_shelter or not normalized_label:
        return None

    ph = _placeholder()
    return db_fetchone(
        f"""
        SELECT *
        FROM housing_units
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND unit_label = {ph}
          AND is_active = {('TRUE' if g.get('db_kind') == 'pg' else '1')}
        LIMIT 1
        """,
        (normalized_shelter, normalized_label),
    )


def get_active_placement(*, resident_id: int, shelter: str | None = None) -> DbRow | None:
    ph = _placeholder()
    params: tuple[Any, ...]
    shelter_clause = ""

    if shelter:
        shelter_clause = f"AND LOWER(COALESCE(shelter, '')) = {ph}"
        params = (resident_id, _normalize_shelter(shelter))
    else:
        params = (resident_id,)

    return db_fetchone(
        f"""
        SELECT *
        FROM resident_placements
        WHERE resident_id = {ph}
          AND COALESCE(end_date, '') = ''
          {shelter_clause}
        ORDER BY start_date DESC, id DESC
        LIMIT 1
        """,
        params,
    )


def end_active_placement(
    *,
    resident_id: int,
    shelter: str | None = None,
    end_date: str,
    note: str | None = None,
    now: str | None = None,
) -> None:
    active = get_active_placement(resident_id=resident_id, shelter=shelter)
    if not active:
        return

    timestamp = now or utcnow_iso()
    ph = _placeholder()
    db_execute(
        f"""
        UPDATE resident_placements
        SET end_date = {ph},
            note = COALESCE(note, {ph}),
            updated_at = {ph}
        WHERE id = {ph}
        """,
        (end_date, note, timestamp, active["id"]),
    )


def create_placement(
    *,
    resident_id: int,
    enrollment_id: int | None,
    shelter: str,
    program_level: object,
    housing_unit_id: int | None,
    placement_type: str,
    start_date: str,
    change_reason: str,
    note: str | None = None,
    now: str | None = None,
    created_by_staff_user_id: int | None = None,
) -> int | None:
    normalized_shelter = _normalize_shelter(shelter)
    normalized_level = _normalize_level(program_level)
    timestamp = now or utcnow_iso()
    staff_user_id = created_by_staff_user_id
    if staff_user_id is None:
        staff_user_id = _current_staff_user_id()

    ph = _placeholder()
    row = db_fetchone(
        f"""
        INSERT INTO resident_placements (
            resident_id,
            enrollment_id,
            shelter,
            program_level,
            housing_unit_id,
            placement_type,
            start_date,
            end_date,
            change_reason,
            note,
            created_by_staff_user_id,
            created_at,
            updated_at
        )
        VALUES ({ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph}, {ph})
        RETURNING id
        """,
        (
            resident_id,
            enrollment_id,
            normalized_shelter,
            normalized_level,
            housing_unit_id,
            placement_type,
            start_date,
            None,
            change_reason,
            note,
            staff_user_id,
            timestamp,
            timestamp,
        ),
    )
    return int(row["id"]) if row and row.get("id") is not None else None


def replace_active_placement(
    *,
    resident_id: int,
    enrollment_id: int | None,
    shelter: str,
    program_level: object,
    housing_unit_id: int | None,
    placement_type: str,
    effective_date: str,
    change_reason: str,
    note: str | None = None,
    now: str | None = None,
) -> int | None:
    timestamp = now or utcnow_iso()
    end_active_placement(
        resident_id=resident_id,
        shelter=None,
        end_date=effective_date,
        note=note,
        now=timestamp,
    )
    return create_placement(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        shelter=shelter,
        program_level=program_level,
        housing_unit_id=housing_unit_id,
        placement_type=placement_type,
        start_date=effective_date,
        change_reason=change_reason,
        note=note,
        now=timestamp,
    )


def sync_placement_from_rent_config(
    *,
    resident_id: int,
    enrollment_id: int | None,
    shelter: str,
    program_level: object,
    apartment_number: str | None,
    effective_date: str,
    change_reason: str,
    note: str | None = None,
    now: str | None = None,
) -> int | None:
    normalized_shelter = _normalize_shelter(shelter)
    unit = get_housing_unit_by_label(
        shelter=normalized_shelter,
        unit_label=apartment_number,
    )

    if normalized_shelter == "haven" and unit is None:
        unit = get_housing_unit_by_label(
            shelter=normalized_shelter,
            unit_label="Dorm Bed",
        )

    return replace_active_placement(
        resident_id=resident_id,
        enrollment_id=enrollment_id,
        shelter=normalized_shelter,
        program_level=program_level,
        housing_unit_id=unit.get("id") if unit else None,
        placement_type=_placement_type_for_unit(unit),
        effective_date=effective_date,
        change_reason=change_reason,
        note=note,
        now=now,
    )
