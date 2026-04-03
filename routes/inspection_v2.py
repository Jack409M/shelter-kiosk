from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

inspection_v2 = Blueprint(
    "inspection_v2",
    __name__,
    url_prefix="/staff/inspection",
)

VALID_ITEM_STATUSES = ["passed", "needs_attention", "failed"]
DEFAULT_ITEM_LABELS = [
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


def _allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _ensure_settings_table() -> None:
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


def _ensure_tables() -> None:
    _ensure_settings_table()

    statements = [
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS overall_status TEXT DEFAULT 'passed'",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS shelter_snapshot TEXT",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass

    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_living_area_inspection_items (
                id SERIAL PRIMARY KEY,
                inspection_id INTEGER NOT NULL REFERENCES resident_living_area_inspections(id),
                item_key TEXT NOT NULL,
                item_label TEXT NOT NULL,
                item_status TEXT NOT NULL DEFAULT 'passed',
                item_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_living_area_inspection_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspection_id INTEGER NOT NULL,
                item_key TEXT NOT NULL,
                item_label TEXT NOT NULL,
                item_status TEXT NOT NULL DEFAULT 'passed',
                item_note TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (inspection_id) REFERENCES resident_living_area_inspections(id)
            )
            """
        )


def _settings_for_shelter(shelter: str) -> dict:
    _ensure_settings_table()
    ph = _placeholder()
    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    if row:
        return dict(row)
    now = utcnow_iso()
    db_execute(
        (
            "INSERT INTO shelter_operation_settings (shelter, inspection_default_item_status, inspection_item_labels, created_at, updated_at) VALUES (%s, %s, %s, %s, %s)"
            if g.get("db_kind") == "pg"
            else
            "INSERT INTO shelter_operation_settings (shelter, inspection_default_item_status, inspection_item_labels, created_at, updated_at) VALUES (?, ?, ?, ?, ?)"
        ),
        (shelter, "passed", "\n".join(DEFAULT_ITEM_LABELS), now, now),
    )
    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    return dict(row) if row else {}


def _inspection_labels(settings: dict) -> list[str]:
    raw = (settings.get("inspection_item_labels") or "").strip()
    labels = [line.strip() for line in raw.splitlines() if line.strip()]
    return labels or list(DEFAULT_ITEM_LABELS)


def _overall_status(item_rows: list[dict]) -> str:
    statuses = [str(row.get("item_status") or "passed").strip().lower() for row in item_rows]
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status == "needs_attention" for status in statuses):
        return "needs_attention"
    return "passed"


def _resident_context(resident_id: int, shelter: str):
    ph = _placeholder()
    row = db_fetchone(
        f"SELECT id, first_name, last_name, shelter FROM residents WHERE id = {ph} AND LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (resident_id, shelter),
    )
    return dict(row) if row else None


def _inspection_history(resident_id: int):
    ph = _placeholder()
    rows = db_fetchall(
        f"SELECT * FROM resident_living_area_inspections WHERE resident_id = {ph} ORDER BY inspection_date DESC, id DESC",
        (resident_id,),
    )
    out = []
    for row in rows:
        item_rows = db_fetchall(
            f"SELECT * FROM resident_living_area_inspection_items WHERE inspection_id = {ph} ORDER BY id ASC",
            (row['id'],),
        )
        item_dicts = [dict(item) for item in item_rows]
        base = dict(row)
        base["items"] = item_dicts
        out.append(base)
    return out


@inspection_v2.route("/<int:resident_id>", methods=["GET", "POST"])
@require_login
@require_shelter
def inspection_form(resident_id: int):
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    _ensure_tables()
    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = _resident_context(resident_id, shelter)
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    settings = _settings_for_shelter(shelter)
    labels = _inspection_labels(settings)
    default_status = (settings.get("inspection_default_item_status") or "passed").strip().lower()
    if default_status not in VALID_ITEM_STATUSES:
        default_status = "passed"

    if request.method == "POST":
        inspection_date = (request.form.get("inspection_date") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None
        if not inspection_date:
            flash("Inspection date is required.", "error")
            return redirect(url_for("inspection_v2.inspection_form", resident_id=resident_id))

        item_rows = []
        for idx, label in enumerate(labels):
            item_status = (request.form.get(f"item_status_{idx}") or default_status).strip().lower()
            if item_status not in VALID_ITEM_STATUSES:
                item_status = default_status
            item_note = (request.form.get(f"item_note_{idx}") or "").strip() or None
            item_rows.append(
                {
                    "item_key": f"item_{idx + 1}",
                    "item_label": label,
                    "item_status": item_status,
                    "item_note": item_note,
                }
            )

        overall_status = _overall_status(item_rows)
        passed = overall_status == "passed"
        now = utcnow_iso()
        db_execute(
            (
                "INSERT INTO resident_living_area_inspections (resident_id, enrollment_id, inspection_date, passed, overall_status, shelter_snapshot, inspected_by_staff_user_id, notes, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
                if g.get("db_kind") == "pg"
                else
                "INSERT INTO resident_living_area_inspections (resident_id, enrollment_id, inspection_date, passed, overall_status, shelter_snapshot, inspected_by_staff_user_id, notes, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (resident_id, None, inspection_date, passed if g.get("db_kind") == "pg" else (1 if passed else 0), overall_status, shelter, session.get("staff_user_id"), notes, now, now),
        )
        ph = _placeholder()
        inspection_row = db_fetchone(
            f"SELECT id FROM resident_living_area_inspections WHERE resident_id = {ph} ORDER BY id DESC LIMIT 1",
            (resident_id,),
        )
        inspection_id = inspection_row["id"]
        for item in item_rows:
            db_execute(
                (
                    "INSERT INTO resident_living_area_inspection_items (inspection_id, item_key, item_label, item_status, item_note, created_at, updated_at) VALUES (%s, %s, %s, %s, %s, %s, %s)"
                    if g.get("db_kind") == "pg"
                    else
                    "INSERT INTO resident_living_area_inspection_items (inspection_id, item_key, item_label, item_status, item_note, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?)"
                ),
                (inspection_id, item['item_key'], item['item_label'], item['item_status'], item['item_note'], now, now),
            )

        flash("Inspection saved.", "ok")
        return redirect(url_for("inspection_v2.inspection_form", resident_id=resident_id))

    history = _inspection_history(resident_id)
    return render_template(
        "case_management/inspection_v2.html",
        resident=resident,
        item_labels=labels,
        default_status=default_status,
        valid_statuses=VALID_ITEM_STATUSES,
        history=history,
    )
