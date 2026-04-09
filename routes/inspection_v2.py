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


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + delta
    shifted_year = month_index // 12
    shifted_month = (month_index % 12) + 1
    return shifted_year, shifted_month


def _month_label(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B %Y")


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
                inspection_scoring_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                inspection_lookback_months INTEGER NOT NULL DEFAULT 9,
                inspection_include_current_open_month BOOLEAN NOT NULL DEFAULT FALSE,
                inspection_score_passed INTEGER NOT NULL DEFAULT 100,
                inspection_needs_attention_enabled BOOLEAN NOT NULL DEFAULT FALSE,
                inspection_score_needs_attention INTEGER NOT NULL DEFAULT 70,
                inspection_score_failed INTEGER NOT NULL DEFAULT 0,
                inspection_passing_threshold INTEGER NOT NULL DEFAULT 83,
                inspection_band_green_min INTEGER NOT NULL DEFAULT 83,
                inspection_band_yellow_min INTEGER NOT NULL DEFAULT 78,
                inspection_band_orange_min INTEGER NOT NULL DEFAULT 56,
                inspection_band_red_max INTEGER NOT NULL DEFAULT 55,
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
                inspection_scoring_enabled INTEGER NOT NULL DEFAULT 1,
                inspection_lookback_months INTEGER NOT NULL DEFAULT 9,
                inspection_include_current_open_month INTEGER NOT NULL DEFAULT 0,
                inspection_score_passed INTEGER NOT NULL DEFAULT 100,
                inspection_needs_attention_enabled INTEGER NOT NULL DEFAULT 0,
                inspection_score_needs_attention INTEGER NOT NULL DEFAULT 70,
                inspection_score_failed INTEGER NOT NULL DEFAULT 0,
                inspection_passing_threshold INTEGER NOT NULL DEFAULT 83,
                inspection_band_green_min INTEGER NOT NULL DEFAULT 83,
                inspection_band_yellow_min INTEGER NOT NULL DEFAULT 78,
                inspection_band_orange_min INTEGER NOT NULL DEFAULT 56,
                inspection_band_red_max INTEGER NOT NULL DEFAULT 55,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )

    statements = [
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_scoring_enabled BOOLEAN DEFAULT TRUE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_lookback_months INTEGER DEFAULT 9",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_include_current_open_month BOOLEAN DEFAULT FALSE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_passed INTEGER DEFAULT 100",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_needs_attention_enabled BOOLEAN DEFAULT FALSE",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_needs_attention INTEGER DEFAULT 70",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_score_failed INTEGER DEFAULT 0",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_passing_threshold INTEGER DEFAULT 83",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_green_min INTEGER DEFAULT 83",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_yellow_min INTEGER DEFAULT 78",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_orange_min INTEGER DEFAULT 56",
        "ALTER TABLE shelter_operation_settings ADD COLUMN IF NOT EXISTS inspection_band_red_max INTEGER DEFAULT 55",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def _load_settings(shelter: str) -> dict:
    _ensure_settings_table()
    ph = _placeholder()
    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    return dict(row) if row else {}


def _ensure_tables() -> None:
    _ensure_settings_table()

    statements = [
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS overall_status TEXT DEFAULT 'passed'",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS shelter_snapshot TEXT",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS inspection_year INTEGER",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS inspection_month INTEGER",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS apartment_number_snapshot TEXT",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS apartment_size_snapshot TEXT",
        "ALTER TABLE resident_living_area_inspections ADD COLUMN IF NOT EXISTS resident_name_snapshot TEXT",
    ]
    for statement in statements:
        try:
            db_execute(statement)
        except Exception:
            pass


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


def _active_inspection_targets_for_shelter(shelter: str) -> list[dict]:
    from routes.rent_tracking_parts.calculations import (
        _apartment_options_for_shelter,
        _derive_apartment_size_from_assignment,
        _normalize_apartment_number,
    )

    shelter_key = _normalize_shelter_name(shelter)
    residents = _active_residents_for_shelter(shelter_key)

    if shelter_key not in {"abba", "gratitude"}:
        targets = []
        for resident in residents:
            targets.append(
                {
                    "resident_id": resident["id"],
                    "resident_name": f"{resident['first_name']} {resident['last_name']}".strip(),
                    "apartment_number_snapshot": None,
                    "apartment_size_snapshot": "Bed" if shelter_key == "haven" else None,
                    "display_title": f"{resident['first_name']} {resident['last_name']}".strip(),
                    "display_subtitle": "Resident",
                }
            )
        return targets

    ph = _placeholder()
    assigned_rows = db_fetchall(
        f"""
        SELECT
            r.id AS resident_id,
            r.first_name,
            r.last_name,
            c.apartment_number_snapshot,
            c.apartment_size_snapshot
        FROM residents r
        JOIN resident_rent_configs c
          ON c.resident_id = r.id
        WHERE LOWER(COALESCE(r.shelter, '')) = {ph}
          AND r.is_active = {('TRUE' if g.get('db_kind') == 'pg' else '1')}
          AND LOWER(COALESCE(c.shelter, '')) = {ph}
          AND COALESCE(c.effective_end_date, '') = ''
        ORDER BY r.last_name ASC, r.first_name ASC, c.id DESC
        """,
        (shelter_key, shelter_key),
    )

    by_apartment: dict[str, dict] = {}
    for row in assigned_rows:
        apartment_number = _normalize_apartment_number(shelter_key, row.get("apartment_number_snapshot"))
        if not apartment_number:
            continue
        if apartment_number in by_apartment:
            continue

        resident_name = f"{row.get('first_name', '')} {row.get('last_name', '')}".strip()
        apartment_size = _derive_apartment_size_from_assignment(shelter_key, apartment_number) or row.get("apartment_size_snapshot")

        by_apartment[apartment_number] = {
            "resident_id": row["resident_id"],
            "resident_name": resident_name,
            "apartment_number_snapshot": apartment_number,
            "apartment_size_snapshot": apartment_size,
            "display_title": f"Apartment {apartment_number}",
            "display_subtitle": resident_name,
        }

    apartment_order = _apartment_options_for_shelter(shelter_key)
    targets: list[dict] = []

    for apartment_number in apartment_order:
        target = by_apartment.get(apartment_number)
        if target:
            targets.append(target)

    return targets


def _inspection_status_score(settings: dict, overall_status: str | None, passed_value) -> int:
    status = (overall_status or "").strip().lower()

    if status == "passed":
        return int(settings.get("inspection_score_passed", 100) or 100)

    if status == "needs_attention":
        if bool(settings.get("inspection_needs_attention_enabled", False)):
            return int(settings.get("inspection_score_needs_attention", 70) or 70)
        return int(settings.get("inspection_score_failed", 0) or 0)

    if status == "failed":
        return int(settings.get("inspection_score_failed", 0) or 0)

    return int(settings.get("inspection_score_passed", 100) or 100) if passed_value else int(
        settings.get("inspection_score_failed", 0) or 0
    )


def _inspection_band_for_score(settings: dict, score: float | int | None) -> dict:
    numeric_score = float(score or 0)
    green_min = int(settings.get("inspection_band_green_min", 83) or 83)
    yellow_min = int(settings.get("inspection_band_yellow_min", 78) or 78)
    orange_min = int(settings.get("inspection_band_orange_min", 56) or 56)

    if numeric_score >= green_min:
        return {
            "band_key": "green",
            "band_label": "Green",
            "card_style": "background:#eef8f0; border:1px solid #9bc8a6;",
            "value_style": "color:#1f6b33; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#dcefe1; border:1px solid #9bc8a6; color:#1f6b33; font-weight:700;",
        }

    if numeric_score >= yellow_min:
        return {
            "band_key": "yellow",
            "band_label": "Yellow",
            "card_style": "background:#fff8df; border:1px solid #e0cd7a;",
            "value_style": "color:#7a6500; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#fff1b8; border:1px solid #e0cd7a; color:#7a6500; font-weight:700;",
        }

    if numeric_score >= orange_min:
        return {
            "band_key": "orange",
            "band_label": "Orange",
            "card_style": "background:#fff0e4; border:1px solid #e2b27d;",
            "value_style": "color:#9a4f00; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd8b0; border:1px solid #e2b27d; color:#9a4f00; font-weight:700;",
        }

    return {
        "band_key": "red",
        "band_label": "Red",
        "card_style": "background:#fff0f0; border:1px solid #e2a0a0;",
        "value_style": "color:#9a1f1f; font-weight:700;",
        "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd6d6; border:1px solid #e2a0a0; color:#9a1f1f; font-weight:700;",
    }


def build_inspection_stability_snapshot(resident_id: int, shelter: str | None = None) -> dict:
    _ensure_tables()
    effective_shelter = _normalize_shelter_name(shelter or session.get("shelter"))
    settings = _load_settings(effective_shelter)

    lookback_months = max(int(settings.get("inspection_lookback_months", 9) or 9), 1)
    include_current_open_month = bool(settings.get("inspection_include_current_open_month", False))
    passing_threshold = int(settings.get("inspection_passing_threshold", 83) or 83)

    current_year, current_month = _current_year_month()
    if include_current_open_month:
        month_keys = [_shift_month(current_year, current_month, -offset) for offset in range(0, lookback_months)]
    else:
        month_keys = [_shift_month(current_year, current_month, -offset) for offset in range(1, lookback_months + 1)]

    allowed_keys = set(month_keys)
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            id,
            inspection_date,
            shelter_snapshot,
            apartment_number_snapshot,
            apartment_size_snapshot,
            resident_name_snapshot,
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

    filtered_rows = []
    score_values: list[int] = []

    for row in rows:
        year = row.get("inspection_year")
        month = row.get("inspection_month")

        if year is None or month is None:
            inspection_date = (row.get("inspection_date") or "").strip()
            try:
                dt = datetime.fromisoformat(inspection_date)
                year = dt.year
                month = dt.month
            except Exception:
                continue

        key = (int(year), int(month))
        if key not in allowed_keys:
            continue

        score = _inspection_status_score(settings, row.get("overall_status"), row.get("passed"))
        filtered_rows.append(dict(row))
        score_values.append(score)

    average_score = round(sum(score_values) / len(score_values), 1) if score_values else 0.0
    band = _inspection_band_for_score(settings, average_score)

    month_rows = [
        {
            "year": year,
            "month": month,
            "label": _month_label(year, month),
        }
        for year, month in month_keys
    ]

    return {
        "lookback_months": lookback_months,
        "include_current_open_month": include_current_open_month,
        "inspection_count": len(score_values),
        "average_score": average_score,
        "average_score_display": f"{average_score:.1f}",
        "passing_threshold": passing_threshold,
        "passes_goal": average_score >= passing_threshold,
        "band_key": band["band_key"],
        "band_label": band["band_label"],
        "card_style": band["card_style"],
        "value_style": band["value_style"],
        "pill_style": band["pill_style"],
        "month_rows": month_rows,
        "rows": filtered_rows,
        "settings": settings,
    }


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

    inspection_targets = _active_inspection_targets_for_shelter(shelter)

    if request.method == "POST":
        inspection_date = (request.form.get("inspection_date") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if not inspection_date:
            flash("Inspection date is required.", "error")
            return redirect(url_for("inspection_v2.inspection_sheet", year=inspection_year, month=inspection_month))

        try:
            inspection_dt = datetime.fromisoformat(inspection_date)
            submitted_inspection_year = inspection_dt.year
            submitted_inspection_month = inspection_dt.month
        except ValueError:
            flash("Inspection date is invalid.", "error")
            return redirect(url_for("inspection_v2.inspection_sheet", year=inspection_year, month=inspection_month))

        now = utcnow_iso()

        for target in inspection_targets:
            resident_id = target["resident_id"]
            status_raw = (request.form.get(f"status_{resident_id}") or "passed").strip().lower()
            if status_raw not in {"passed", "needs_attention", "failed"}:
                status_raw = "passed"

            passed = status_raw == "passed"
            overall_status = status_raw

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
                        apartment_number_snapshot,
                        apartment_size_snapshot,
                        resident_name_snapshot,
                        inspection_year,
                        inspection_month,
                        inspected_by_staff_user_id,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        apartment_number_snapshot,
                        apartment_size_snapshot,
                        resident_name_snapshot,
                        inspection_year,
                        inspection_month,
                        inspected_by_staff_user_id,
                        notes,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    resident_id,
                    None,
                    inspection_date,
                    passed if g.get("db_kind") == "pg" else (1 if passed else 0),
                    overall_status,
                    shelter,
                    target.get("apartment_number_snapshot"),
                    target.get("apartment_size_snapshot"),
                    target.get("resident_name"),
                    submitted_inspection_year,
                    submitted_inspection_month,
                    session.get("staff_user_id"),
                    notes,
                    now,
                    now,
                ),
            )

        flash("Inspection sheet saved.", "ok")
        return redirect(
            url_for(
                "inspection_v2.inspection_sheet",
                year=submitted_inspection_year,
                month=submitted_inspection_month,
            )
        )

    return render_template(
        "case_management/inspection_sheet.html",
        shelter=shelter,
        inspection_targets=inspection_targets,
        inspection_year=inspection_year,
        inspection_month=inspection_month,
        apartment_mode=shelter in {"abba", "gratitude"},
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
    shelter = _normalize_shelter_name(resident.get("shelter"))
    inspection_snapshot = build_inspection_stability_snapshot(resident_id, shelter=shelter)

    return render_template(
        "case_management/resident_inspection_history.html",
        resident=resident,
        rows=inspection_snapshot["rows"],
        inspection_snapshot=inspection_snapshot,
    )
