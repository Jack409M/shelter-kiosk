from __future__ import annotations

import secrets
from typing import Any

from flask import current_app, g, session

from core.audit import log_action
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def make_resident_code(length: int = 8) -> str:
    return "".join(secrets.choice("0123456789") for _ in range(length))


def generate_resident_code() -> str:
    code = make_resident_code(8)

    for _ in range(15):
        exists = db_fetchone(
            "SELECT id FROM residents WHERE resident_code = %s"
            if g.get("db_kind") == "pg"
            else "SELECT id FROM residents WHERE resident_code = ?",
            (code,),
        )
        if not exists:
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
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id
        FROM resident_passes
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = ?
          AND status = ?
          AND (
                (start_at IS NOT NULL AND end_at IS NOT NULL AND start_at <= ? AND end_at >= ?)
             OR (start_date IS NOT NULL AND end_date IS NOT NULL AND start_date <= ? AND end_date >= ?)
          )
        LIMIT 1
        """,
        (resident_id, normalized_shelter, "approved", now_iso, now_iso, today_iso, today_iso),
    )

    return bool(row)


def resident_session_start(resident_row: Any, shelter: str, resident_code: str) -> None:
    session.permanent = True

    session["resident_id"] = resident_row["id"] if isinstance(resident_row, dict) else resident_row[0]
    session["resident_identifier"] = (
        resident_row["resident_identifier"] if isinstance(resident_row, dict) else resident_row[2]
    )
    session["resident_first"] = (
        resident_row["first_name"] if isinstance(resident_row, dict) else resident_row[4]
    )
    session["resident_last"] = (
        resident_row["last_name"] if isinstance(resident_row, dict) else resident_row[5]
    )
    session["resident_phone"] = (
        (resident_row["phone"] if isinstance(resident_row, dict) else resident_row[6]) or ""
    )
    session["resident_shelter"] = _normalize_shelter_name(shelter)
    session["resident_code"] = resident_code


def record_resident_transfer(resident_id: int, from_shelter: str, to_shelter: str, note: str = ""):
    actor = session.get("username") or "unknown"
    normalized_from_shelter = _normalize_shelter_name(from_shelter)
    normalized_to_shelter = _normalize_shelter_name(to_shelter)

    if current_app.config.get("DATABASE_URL"):
        db_execute(
            """
            INSERT INTO resident_transfers
              (resident_id, from_shelter, to_shelter, transferred_by, note)
            VALUES (%s, %s, %s, %s, %s)
            """,
            (resident_id, normalized_from_shelter, normalized_to_shelter, actor, note or None),
        )
    else:
        db_execute(
            """
            INSERT INTO resident_transfers
              (resident_id, from_shelter, to_shelter, transferred_by, transferred_at, note)
            VALUES (?, ?, ?, ?, datetime('now'), ?)
            """,
            (resident_id, normalized_from_shelter, normalized_to_shelter, actor, note or None),
        )

    staff_id = session.get("staff_user_id")
    log_action(
        "resident",
        resident_id,
        normalized_from_shelter,
        staff_id,
        "resident_transfer",
        f"from={normalized_from_shelter} to={normalized_to_shelter} note={note}".strip(),
    )
