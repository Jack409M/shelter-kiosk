from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


inspection_v2 = Blueprint(
    "inspection_v2",
    __name__,
    url_prefix="/staff/inspection",
)


CHICAGO_TZ = ZoneInfo("America/Chicago")


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _today_chicago() -> datetime:
    return datetime.now(CHICAGO_TZ)


def _current_year_month() -> tuple[int, int]:
    now = _today_chicago()
    return now.year, now.month


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
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS inspection_year INTEGER",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS inspection_month INTEGER",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


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
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO shelter_operation_settings (
                shelter,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?)
            """
        ),
        (shelter, "passed", None, now, now),
    )

    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    return dict(row) if row else {}


def _active_residents_for_shelter(shelter: str):
    ph = _placeholder()
    return db_fetchall(
        f"""
        SELECT id, first_name, last_name
        FROM residents
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND is_active = {('TRUE' if g.get('db_kind') == 'pg' else '1')}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )


def _overall_score_from_passed(passed: bool) -> int:
    return 100 if passed else 0


def _weighted_score_for_resident(resident_id: int) -> int | None:
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT passed
        FROM resident_living_area_inspections
        WHERE resident_id = {ph}
        ORDER BY inspection_date DESC, id DESC
        LIMIT 6
        """,
        (resident_id,),
    )
    values = []
    for row in rows:
        passed = row.get("passed")
        values.append(100 if passed else 0)
    if not values:
        return None
    return round(sum(values) / len(values))


@inspection_v2.route("/sheet", methods=["GET", "POST"])
@require_login
@require_shelter
def inspection_sheet():
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    _ensure_tables()

    shelter = _normalize_shelter_name(session.get("shelter"))
    inspection_year = request.args.get("year", type=int)
    inspection_month = request.args.get("month", type=int)
    if not inspection_year or not inspection_month:
        inspection_year, inspection_month = _current_year_month()

    residents = _active_residents_for_shelter(shelter)

    if request.method == "POST":
        inspection_date = (request.form.get("inspection_date") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if not inspection_date:
            flash("Inspection date is required.", "error")
            return redirect(url_for("inspection_v2.inspection_sheet", year=inspection_year, month=inspection_month))

        now = utcnow_iso()

        for resident in residents:
            resident_id = resident["id"]
            status_raw = (request.form.get(f"status_{resident_id}") or "passed").strip().lower()
            passed = status_raw != "failed"
            overall_status = "passed" if passed else "failed"

            db_execute(
                (
                    """
                    INSERT INTO resident_living_area_inspections (
                        resident_id,
                        enrollment_id,
                        inspection_date,
                        passed,
                        overall_status,
                        shelter_snapshot,
                        inspection_year,
                        inspection_month,
                        inspected_by_staff_user_id,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    INSERT INTO resident_living_area_inspections (
                        resident_id,
                        enrollment_id,
                        inspection_date,
                        passed,
                        overall_status,
                        shelter_snapshot,
                        inspection_year,
                        inspection_month,
                        inspected_by_staff_user_id,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    resident_id,
                    None,
                    inspection_date,
                    passed if g.get("db_kind") == "pg" else (1 if passed else 0),
                    overall_status,
                    shelter,
                    inspection_year,
                    inspection_month,
                    session.get("staff_user_id"),
                    notes,
                    now,
                    now,
                ),
            )

        flash("Inspection sheet saved.", "ok")
        return redirect(url_for("inspection_v2.inspection_sheet", year=inspection_year, month=inspection_month))

    return render_template(
        "case_management/inspection_sheet.html",
        shelter=shelter,
        residents=residents,
        inspection_year=inspection_year,
        inspection_month=inspection_month,
    )


@inspection_v2.get("/resident/<int:resident_id>/history")
@require_login
@require_shelter
def resident_inspection_history(resident_id: int):
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    _ensure_tables()
    ph = _placeholder()

    resident = db_fetchone(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE id = {ph}
        LIMIT 1
        """,
        (resident_id,),
    )
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    resident = dict(resident)

    rows = db_fetchall(
        f"""
        SELECT
            id,
            inspection_date,
            shelter_snapshot,
            overall_status,
            passed,
            inspection_year,
            inspection_month,
            notes
        FROM resident_living_area_inspections
        WHERE resident_id = {ph}
        ORDER BY inspection_date DESC, id DESC
        """,
        (resident_id,),
    )

    weighted_score = _weighted_score_for_resident(resident_id)

    return render_template(
        "case_management/resident_inspection_history.html",
        resident=resident,
        rows=rows,
        weighted_score=weighted_score,
    )
