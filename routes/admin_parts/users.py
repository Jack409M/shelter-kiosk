from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt, utcnow_iso
from core.runtime import MIN_STAFF_PASSWORD_LEN, ROLE_LABELS, init_db
from core.admin_rbac import (
    all_roles as _all_roles,
    allowed_roles_to_create as _allowed_roles_to_create,
    current_role as _current_role,
    ordered_roles as _ordered_roles,
    require_admin_or_shelter_director_role as _require_admin_or_shelter_director,
    require_admin_role as _require_admin,
    can_manage_target_role as _can_manage_target_role,
)

VALID_SHELTERS = {"abba", "haven", "gratitude"}
VALID_CALENDAR_COLORS = {
    "#D9534F",
    "#337AB7",
    "#5CB85C",
    "#8E44AD",
    "#F0AD4E",
    "#20B2AA",
    "#E83E8C",
    "#C9A227",
}


def _db_kind() -> str:
    return "pg" if current_app.config.get("DATABASE_URL") else "sqlite"


def _ph() -> str:
    return "%s" if _db_kind() == "pg" else "?"


def _form_context(**extra):
    context = {
        "roles": _ordered_roles(_allowed_roles_to_create()),
        "all_roles": _ordered_roles(_all_roles()),
        "ROLE_LABELS": ROLE_LABELS,
        "current_role": _current_role(),
    }
    context.update(extra)
    return context


def _normalize_selected_shelters(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    for value in values:
        shelter = (value or "").strip().lower()
        if shelter in VALID_SHELTERS and shelter not in seen:
            cleaned.append(shelter)
            seen.add(shelter)

    return cleaned


def _normalize_calendar_color(value: str | None) -> str | None:
    cleaned = (value or "").strip().upper()
    if not cleaned:
        return None
    if cleaned in VALID_CALENDAR_COLORS:
        return cleaned
    return None


def _load_staff_shelter_assignments(staff_user_id: int) -> set[str]:
    rows = db_fetchall(
        f"SELECT shelter FROM staff_shelter_assignments WHERE staff_user_id = {_ph()} ORDER BY shelter",
        (staff_user_id,),
    )

    shelters: set[str] = set()

    for row in rows:
        shelter = (row["shelter"] or "").strip().lower()
        if shelter:
            shelters.add(shelter)

    return shelters


def _save_staff_shelter_assignments(staff_user_id: int, shelters: list[str]) -> None:
    db_execute(
        f"DELETE FROM staff_shelter_assignments WHERE staff_user_id = {_ph()}",
        (staff_user_id,),
    )

    cleaned = _normalize_selected_shelters(shelters)

    for shelter in cleaned:
        db_execute(
            f"""
            INSERT INTO staff_shelter_assignments (staff_user_id, shelter, created_at)
            VALUES ({_ph()}, {_ph()}, CURRENT_TIMESTAMP)
            """,
            (staff_user_id, shelter),
        )


# rest of file unchanged