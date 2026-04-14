from __future__ import annotations

import secrets
from collections.abc import Mapping
from typing import Any

from flask import session

from core.audit import log_action
from core.db import DbRow, db_execute, db_fetchone
from core.helpers import utcnow_iso


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _require_row_mapping(row: object, *, label: str) -> DbRow:
    if not isinstance(row, Mapping):
        raise RuntimeError(f"{label} must be a mapping row")
    return dict(row)


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _session_staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None

    try:
        return int(raw_staff_user_id)
    except (TypeError, ValueError):
        return None


def _resident_identity_row_by_id(resident_id: int) -> DbRow | None:
    return db_fetchone(
        """
        SELECT id, resident_identifier, first_name, last_name, phone, shelter
        FROM residents
        WHERE id = %s
        LIMIT 1
        """,
        (resident_id,),
    )


def _resident_identity_row_by_code(
    *,
    resident_code: str,
    shelter: str,
) -> DbRow | None:
    return db_fetchone(
        """
        SELECT id, resident_identifier, first_name, last_name, phone, shelter
        FROM residents
        WHERE resident_code = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
        LIMIT 1
        """,
        (resident_code, shelter),
    )


def make_resident_code(length: int = 8) -> str:
    if length <= 0:
        raise ValueError("length must be greater than 0")

    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_resident_code() -> str:
    code = make_resident_code(8)

    for _ in range(15):
        exists = db_fetchone(
            """
            SELECT id
            FROM residents
            WHERE resident_code = %s
            LIMIT 1
            """,
            (code,),
        )
        if exists is None:
            return code
        code = make_resident_code(8)

    return code


def generate_resident_identifier() -> str:
    return secrets.token_urlsafe(12)


def has_active_pass(resident_id: int, shelter: str) -> bool:
    normalized_shelter = _normalize_shelter_name(shelter)
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    row = db_fetchone(
        """
        SELECT id
        FROM resident_passes
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = %s
          AND status = %s
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= %s AND end_at >= %s)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= %s AND end_date >= %s)
          )
        LIMIT 1
        """,
        (
            resident_id,
            normalized_shelter,
            "approved",
            now_iso,
            now_iso,
            today_iso,
            today_iso,
        ),
    )

    return row is not None


def resident_session_start(resident_row: Any, shelter: str, resident_code: str) -> None:
    session.permanent = True

    normalized_shelter = _normalize_shelter_name(shelter)
    source_row = _require_row_mapping(resident_row, label="resident_row")

    resident_id_value = source_row.get("id")
    resident_id = resident_id_value if isinstance(resident_id_value, int) else None

    fresh_row: DbRow | None = None
    if resident_id is not None:
        fresh_row = _resident_identity_row_by_id(resident_id)

    if fresh_row is None:
        fresh_row = _resident_identity_row_by_code(
            resident_code=resident_code,
            shelter=normalized_shelter,
        )

    identity_row = fresh_row or source_row

    session["resident_id"] = identity_row.get("id")
    session["resident_identifier"] = _clean_text(identity_row.get("resident_identifier"))
    session["resident_first"] = _clean_text(identity_row.get("first_name"))
    session["resident_last"] = _clean_text(identity_row.get("last_name"))
    session["resident_phone"] = _clean_text(identity_row.get("phone"))
    session["resident_shelter"] = _normalize_shelter_name(
        str(identity_row.get("shelter") or normalized_shelter)
    )
    session["resident_code"] = resident_code


def record_resident_transfer(
    resident_id: int,
    from_shelter: str,
    to_shelter: str,
    note: str = "",
) -> None:
    actor = _clean_text(session.get("username")) or "unknown"
    normalized_from_shelter = _normalize_shelter_name(from_shelter)
    normalized_to_shelter = _normalize_shelter_name(to_shelter)
    cleaned_note = _clean_text(note)

    db_execute(
        """
        INSERT INTO resident_transfers
          (resident_id, from_shelter, to_shelter, transferred_by, transferred_at, note)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            normalized_from_shelter,
            normalized_to_shelter,
            actor,
            utcnow_iso(),
            cleaned_note or None,
        ),
    )

    log_action(
        "resident",
        resident_id,
        normalized_from_shelter,
        _session_staff_user_id(),
        "resident_transfer",
        (
            f"from={normalized_from_shelter} "
            f"to={normalized_to_shelter} "
            f"note={cleaned_note}"
        ).strip(),
    )
