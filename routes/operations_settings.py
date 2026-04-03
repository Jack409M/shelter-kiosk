from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for, g

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchone
from core.helpers import utcnow_iso

operations_settings = Blueprint(
    "operations_settings",
    __name__,
    url_prefix="/staff/admin/operations-settings",
)


DEFAULT_INSPECTION_ITEMS = [
    "Floors clean",
    "Bed made",
    "Trash removed",
    "Bathroom clean",
    "No prohibited items visible",
    "General room condition acceptable",
]


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _director_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director"}


def _ensure_operations_settings_table() -> None:
    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS shelter_operation_settings (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL UNIQUE,
                rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
                rent_score_paid INTEGER NOT NULL DEFAULT 100,
                rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
                rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
                rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
                rent_score_exempt INTEGER NOT NULL DEFAULT 100,
                rent_carry_forward_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS shelter_operation_settings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL UNIQUE,
                rent_late_day_of_month INTEGER NOT NULL DEFAULT 6,
                rent_score_paid INTEGER NOT NULL DEFAULT 100,
                rent_score_partially_paid INTEGER NOT NULL DEFAULT 75,
                rent_score_paid_late INTEGER NOT NULL DEFAULT 75,
                rent_score_not_paid INTEGER NOT NULL DEFAULT 0,
                rent_score_exempt INTEGER NOT NULL DEFAULT 100,
                rent_carry_forward_enabled INTEGER NOT NULL DEFAULT 1,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    statements = [
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_late_day_of_month INTEGER DEFAULT 6",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_paid INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_partially_paid INTEGER DEFAULT 75",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_paid_late INTEGER DEFAULT 75",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_not_paid INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_score_exempt INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS rent_carry_forward_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_default_item_status TEXT DEFAULT 'passed'",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_item_labels TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS created_at TEXT",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS updated_at TEXT",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def _default_labels_text() -> str:
    return "\n".join(DEFAULT_INSPECTION_ITEMS)


def _settings_row_for_shelter(shelter: str):
    _ensure_operations_settings_table()
    ph = _placeholder()
    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    if row:
        return row

    now = utcnow_iso()
    db_execute(
        (
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            shelter,
            6,
            100,
            75,
            75,
            0,
            100,
            True if g.get("db_kind") == "pg" else 1,
            "passed",
            _default_labels_text(),
            now,
            now,
        ),
    )
    return db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )


@operations_settings.route("", methods=["GET", "POST"])
@require_login
@require_shelter
def settings_page():
    if not _director_allowed():
        flash("Admin or shelter director access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    row = _settings_row_for_shelter(shelter)

    if request.method == "POST":
        now = utcnow_iso()
        late_day_raw = (request.form.get("rent_late_day_of_month") or "6").strip()
        inspection_default_item_status = (request.form.get("inspection_default_item_status") or "passed").strip().lower()
        inspection_item_labels = (request.form.get("inspection_item_labels") or "").strip() or _default_labels_text()
        carry_forward_enabled = (request.form.get("rent_carry_forward_enabled") or "yes").strip().lower() == "yes"

        try:
            late_day = int(late_day_raw)
        except ValueError:
            late_day = 6

        late_day = min(max(late_day, 1), 28)
        if inspection_default_item_status not in {"passed", "needs_attention", "failed"}:
            inspection_default_item_status = "passed"

        rent_score_paid = int((request.form.get("rent_score_paid") or "100").strip() or "100")
        rent_score_partially_paid = int((request.form.get("rent_score_partially_paid") or "75").strip() or "75")
        rent_score_paid_late = int((request.form.get("rent_score_paid_late") or "75").strip() or "75")
        rent_score_not_paid = int((request.form.get("rent_score_not_paid") or "0").strip() or "0")
        rent_score_exempt = int((request.form.get("rent_score_exempt") or "100").strip() or "100")

        db_execute(
            (
                """
                UPDATE shelter_operation_settings
                SET rent_late_day_of_month = %s,
                    rent_score_paid = %s,
                    rent_score_partially_paid = %s,
                    rent_score_paid_late = %s,
                    rent_score_not_paid = %s,
                    rent_score_exempt = %s,
                    rent_carry_forward_enabled = %s,
                    inspection_default_item_status = %s,
                    inspection_item_labels = %s,
                    updated_at = %s
                WHERE LOWER(COALESCE(shelter, '')) = %s
                """
                if g.get("db_kind") == "pg"
                else
                """
                UPDATE shelter_operation_settings
                SET rent_late_day_of_month = ?,
                    rent_score_paid = ?,
                    rent_score_partially_paid = ?,
                    rent_score_paid_late = ?,
                    rent_score_not_paid = ?,
                    rent_score_exempt = ?,
                    rent_carry_forward_enabled = ?,
                    inspection_default_item_status = ?,
                    inspection_item_labels = ?,
                    updated_at = ?
                WHERE LOWER(COALESCE(shelter, '')) = ?
                """
            ),
            (
                late_day,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                carry_forward_enabled if g.get("db_kind") == "pg" else (1 if carry_forward_enabled else 0),
                inspection_default_item_status,
                inspection_item_labels,
                now,
                shelter,
            ),
        )

        flash("Operations settings updated.", "ok")
        return redirect(url_for("operations_settings.settings_page"))

    return render_template(
        "admin_operations_settings.html",
        shelter=shelter,
        settings=row,
        default_inspection_items=_default_labels_text(),
    )
