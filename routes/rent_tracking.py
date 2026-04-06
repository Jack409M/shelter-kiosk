from __future__ import annotations

from calendar import monthrange
from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


rent_tracking = Blueprint(
    "rent_tracking",
    __name__,
    url_prefix="/staff/rent",
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


def _month_label(year: int, month: int) -> str:
    return datetime(year, month, 1).strftime("%B %Y")


def _float_value(value) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return round(float(value), 2)
    except Exception:
        return 0.0


def _int_value(value, default: int = 0) -> int:
    try:
        if value in (None, ""):
            return default
        return int(value)
    except Exception:
        return default


def _bool_value(value) -> bool:
    if isinstance(value, bool):
        return value
    if value in (1, "1", "true", "True", "yes", "Yes", "on"):
        return True
    return False


def _parse_iso_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _month_start_end(year: int, month: int) -> tuple[date, date]:
    last_day = monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last_day)


def _days_in_month(year: int, month: int) -> int:
    return monthrange(year, month)[1]


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    month_index = (year * 12 + (month - 1)) + delta
    shifted_year = month_index // 12
    shifted_month = (month_index % 12) + 1
    return shifted_year, shifted_month


def _completed_month_keys(lookback_months: int = 9) -> list[tuple[int, int]]:
    current_year, current_month = _current_year_month()
    months: list[tuple[int, int]] = []
    for offset in range(1, lookback_months + 1):
        months.append(_shift_month(current_year, current_month, -offset))
    return months


def _rent_band_for_score(score: float | int | None) -> dict:
    numeric_score = float(score or 0)

    if numeric_score >= 95:
        return {
            "band_key": "green",
            "band_label": "Green",
            "card_style": "background:#eef8f0; border:1px solid #9bc8a6;",
            "value_style": "color:#1f6b33; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#dcefe1; border:1px solid #9bc8a6; color:#1f6b33; font-weight:700;",
        }

    if numeric_score >= 79:
        return {
            "band_key": "yellow",
            "band_label": "Yellow",
            "card_style": "background:#fff8df; border:1px solid #e0cd7a;",
            "value_style": "color:#7a6500; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#fff1b8; border:1px solid #e0cd7a; color:#7a6500; font-weight:700;",
        }

    if numeric_score >= 62:
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


def build_rent_stability_snapshot(resident_id: int, lookback_months: int = 9) -> dict:
    month_keys = _completed_month_keys(lookback_months)
    ph = _placeholder()

    rows = db_fetchall(
        f"""
        SELECT
            e.compliance_score,
            s.rent_year,
            s.rent_month
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE e.resident_id = {ph}
        ORDER BY s.rent_year DESC, s.rent_month DESC, e.id DESC
        """,
        (resident_id,),
    )

    score_by_month: dict[tuple[int, int], int] = {}
    for row in rows:
        year = int(row["rent_year"])
        month = int(row["rent_month"])
        key = (year, month)
        if key not in score_by_month:
            score_by_month[key] = int(row.get("compliance_score") or 0)

    month_rows = []
    month_scores: list[int] = []

    for year, month in month_keys:
        score = score_by_month.get((year, month), 0)
        month_scores.append(score)
        month_rows.append(
            {
                "year": year,
                "month": month,
                "label": _month_label(year, month),
                "score": score,
            }
        )

    average_score = round(sum(month_scores) / len(month_scores), 1) if month_scores else 0.0
    band = _rent_band_for_score(average_score)

    return {
        "lookback_months": lookback_months,
        "average_score": average_score,
        "average_score_display": f"{average_score:.1f}",
        "graduation_target": 95,
        "passes_graduation": average_score >= 95,
        "band_key": band["band_key"],
        "band_label": band["band_label"],
        "card_style": band["card_style"],
        "value_style": band["value_style"],
        "pill_style": band["pill_style"],
        "month_rows": month_rows,
    }


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
                hh_rent_amount DOUBLE PRECISION NOT NULL DEFAULT 150.00,
                hh_rent_due_day INTEGER NOT NULL DEFAULT 1,
                hh_rent_late_day INTEGER NOT NULL DEFAULT 5,
                hh_rent_late_fee_per_day DOUBLE PRECISION NOT NULL DEFAULT 1.00,
                hh_late_arrangement_required BOOLEAN NOT NULL DEFAULT TRUE,
                hh_payment_methods_text TEXT,
                hh_payment_accepted_by_roles_text TEXT,
                hh_work_off_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                hh_work_off_hourly_rate DOUBLE PRECISION NOT NULL DEFAULT 10.00,
                hh_work_off_required_hours INTEGER NOT NULL DEFAULT 15,
                hh_work_off_deadline_day INTEGER NOT NULL DEFAULT 10,
                hh_work_off_location_text TEXT,
                hh_work_off_notes_text TEXT,
                gh_rent_due_day INTEGER NOT NULL DEFAULT 1,
                gh_rent_late_fee_per_day DOUBLE PRECISION NOT NULL DEFAULT 1.00,
                gh_late_arrangement_required BOOLEAN NOT NULL DEFAULT TRUE,
                gh_level_5_one_bedroom_rent DOUBLE PRECISION NOT NULL DEFAULT 250.00,
                gh_level_5_two_bedroom_rent DOUBLE PRECISION NOT NULL DEFAULT 300.00,
                gh_level_5_townhome_rent DOUBLE PRECISION NOT NULL DEFAULT 300.00,
                gh_level_8_sliding_scale_enabled BOOLEAN NOT NULL DEFAULT TRUE,
                gh_level_8_sliding_scale_basis_text TEXT,
                gh_level_8_first_increase_amount DOUBLE PRECISION NOT NULL DEFAULT 50.00,
                gh_level_8_second_increase_amount DOUBLE PRECISION NOT NULL DEFAULT 50.00,
                gh_level_8_increase_schedule_text TEXT,
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
                hh_rent_amount REAL NOT NULL DEFAULT 150.00,
                hh_rent_due_day INTEGER NOT NULL DEFAULT 1,
                hh_rent_late_day INTEGER NOT NULL DEFAULT 5,
                hh_rent_late_fee_per_day REAL NOT NULL DEFAULT 1.00,
                hh_late_arrangement_required INTEGER NOT NULL DEFAULT 1,
                hh_payment_methods_text TEXT,
                hh_payment_accepted_by_roles_text TEXT,
                hh_work_off_enabled INTEGER NOT NULL DEFAULT 1,
                hh_work_off_hourly_rate REAL NOT NULL DEFAULT 10.00,
                hh_work_off_required_hours INTEGER NOT NULL DEFAULT 15,
                hh_work_off_deadline_day INTEGER NOT NULL DEFAULT 10,
                hh_work_off_location_text TEXT,
                hh_work_off_notes_text TEXT,
                gh_rent_due_day INTEGER NOT NULL DEFAULT 1,
                gh_rent_late_fee_per_day REAL NOT NULL DEFAULT 1.00,
                gh_late_arrangement_required INTEGER NOT NULL DEFAULT 1,
                gh_level_5_one_bedroom_rent REAL NOT NULL DEFAULT 250.00,
                gh_level_5_two_bedroom_rent REAL NOT NULL DEFAULT 300.00,
                gh_level_5_townhome_rent REAL NOT NULL DEFAULT 300.00,
                gh_level_8_sliding_scale_enabled INTEGER NOT NULL DEFAULT 1,
                gh_level_8_sliding_scale_basis_text TEXT,
                gh_level_8_first_increase_amount REAL NOT NULL DEFAULT 50.00,
                gh_level_8_second_increase_amount REAL NOT NULL DEFAULT 50.00,
                gh_level_8_increase_schedule_text TEXT,
                inspection_default_item_status TEXT NOT NULL DEFAULT 'passed',
                inspection_item_labels TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )


def _ensure_tables() -> None:
    _ensure_operations_settings_table()

    if g.get("db_kind") == "pg":
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_configs (
                id SERIAL PRIMARY KEY,
                resident_id INTEGER NOT NULL REFERENCES residents(id),
                shelter TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                monthly_rent NUMERIC(10,2) NOT NULL DEFAULT 0,
                is_exempt BOOLEAN NOT NULL DEFAULT FALSE,
                effective_start_date TEXT NOT NULL,
                effective_end_date TEXT,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheets (
                id SERIAL PRIMARY KEY,
                shelter TEXT NOT NULL,
                rent_year INTEGER NOT NULL,
                rent_month INTEGER NOT NULL,
                generated_on TEXT NOT NULL,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (shelter, rent_year, rent_month)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheet_entries (
                id SERIAL PRIMARY KEY,
                sheet_id INTEGER NOT NULL REFERENCES resident_rent_sheets(id),
                resident_id INTEGER NOT NULL REFERENCES residents(id),
                shelter_snapshot TEXT NOT NULL,
                resident_name_snapshot TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                prior_balance NUMERIC(10,2) NOT NULL DEFAULT 0,
                current_charge NUMERIC(10,2) NOT NULL DEFAULT 0,
                total_due NUMERIC(10,2) NOT NULL DEFAULT 0,
                amount_paid NUMERIC(10,2) NOT NULL DEFAULT 0,
                remaining_balance NUMERIC(10,2) NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Not Paid',
                compliance_score INTEGER NOT NULL DEFAULT 0,
                paid_date TEXT,
                notes TEXT,
                updated_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (sheet_id, resident_id)
            )
            """
        )
    else:
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                resident_id INTEGER NOT NULL,
                shelter TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                monthly_rent REAL NOT NULL DEFAULT 0,
                is_exempt INTEGER NOT NULL DEFAULT 0,
                effective_start_date TEXT NOT NULL,
                effective_end_date TEXT,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (resident_id) REFERENCES residents(id)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelter TEXT NOT NULL,
                rent_year INTEGER NOT NULL,
                rent_month INTEGER NOT NULL,
                generated_on TEXT NOT NULL,
                created_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (shelter, rent_year, rent_month)
            )
            """
        )
        db_execute(
            """
            CREATE TABLE IF NOT EXISTS resident_rent_sheet_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sheet_id INTEGER NOT NULL,
                resident_id INTEGER NOT NULL,
                shelter_snapshot TEXT NOT NULL,
                resident_name_snapshot TEXT NOT NULL,
                level_snapshot TEXT,
                apartment_size_snapshot TEXT,
                prior_balance REAL NOT NULL DEFAULT 0,
                current_charge REAL NOT NULL DEFAULT 0,
                total_due REAL NOT NULL DEFAULT 0,
                amount_paid REAL NOT NULL DEFAULT 0,
                remaining_balance REAL NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'Not Paid',
                compliance_score INTEGER NOT NULL DEFAULT 0,
                paid_date TEXT,
                notes TEXT,
                updated_by_staff_user_id INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY (sheet_id) REFERENCES resident_rent_sheets(id),
                FOREIGN KEY (resident_id) REFERENCES residents(id),
                UNIQUE (sheet_id, resident_id)
            )
            """
        )

    alter_statements = [
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS occupancy_start_date TEXT",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS occupancy_end_date TEXT",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS occupied_days INTEGER DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS month_day_count INTEGER DEFAULT 30",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS base_monthly_rent DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS prorated_charge DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS late_fee_charge DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS manual_adjustment DOUBLE PRECISION DEFAULT 0",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS approved_late_arrangement BOOLEAN DEFAULT FALSE",
        "ALTER TABLE resident_rent_sheet_entries ADD COLUMN IF NOT EXISTS calculation_notes TEXT",
    ]
    for statement in alter_statements:
        try:
            db_execute(statement)
        except Exception:
            pass


def _load_settings(shelter: str) -> dict:
    _ensure_operations_settings_table()
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
                rent_late_day_of_month,
                rent_score_paid,
                rent_score_partially_paid,
                rent_score_paid_late,
                rent_score_not_paid,
                rent_score_exempt,
                rent_carry_forward_enabled,
                hh_rent_amount,
                hh_rent_due_day,
                hh_rent_late_day,
                hh_rent_late_fee_per_day,
                hh_late_arrangement_required,
                hh_payment_methods_text,
                hh_payment_accepted_by_roles_text,
                hh_work_off_enabled,
                hh_work_off_hourly_rate,
                hh_work_off_required_hours,
                hh_work_off_deadline_day,
                hh_work_off_location_text,
                hh_work_off_notes_text,
                gh_rent_due_day,
                gh_rent_late_fee_per_day,
                gh_late_arrangement_required,
                gh_level_5_one_bedroom_rent,
                gh_level_5_two_bedroom_rent,
                gh_level_5_townhome_rent,
                gh_level_8_sliding_scale_enabled,
                gh_level_8_sliding_scale_basis_text,
                gh_level_8_first_increase_amount,
                gh_level_8_second_increase_amount,
                gh_level_8_increase_schedule_text,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                hh_rent_amount,
                hh_rent_due_day,
                hh_rent_late_day,
                hh_rent_late_fee_per_day,
                hh_late_arrangement_required,
                hh_payment_methods_text,
                hh_payment_accepted_by_roles_text,
                hh_work_off_enabled,
                hh_work_off_hourly_rate,
                hh_work_off_required_hours,
                hh_work_off_deadline_day,
                hh_work_off_location_text,
                hh_work_off_notes_text,
                gh_rent_due_day,
                gh_rent_late_fee_per_day,
                gh_late_arrangement_required,
                gh_level_5_one_bedroom_rent,
                gh_level_5_two_bedroom_rent,
                gh_level_5_townhome_rent,
                gh_level_8_sliding_scale_enabled,
                gh_level_8_sliding_scale_basis_text,
                gh_level_8_first_increase_amount,
                gh_level_8_second_increase_amount,
                gh_level_8_increase_schedule_text,
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            150.00,
            1,
            5,
            1.00,
            True if g.get("db_kind") == "pg" else 1,
            "Money order\nCashier check",
            "Case managers only",
            True if g.get("db_kind") == "pg" else 1,
            10.00,
            15,
            10,
            "Thrift City",
            "If unemployed, resident may work off rent at 10 dollars per hour. Hours must be completed by the 10th unless arrangements are made in advance.",
            1,
            1.00,
            True if g.get("db_kind") == "pg" else 1,
            250.00,
            300.00,
            300.00,
            True if g.get("db_kind") == "pg" else 1,
            "Sliding scale based on income, household size, and accepted expenses.",
            50.00,
            50.00,
            "Increase a minimum of 50 the month after graduation, then another 50 one year later.",
            "passed",
            None,
            now,
            now,
        ),
    )

    row = db_fetchone(
        f"SELECT * FROM shelter_operation_settings WHERE LOWER(COALESCE(shelter, '')) = {ph} LIMIT 1",
        (shelter,),
    )
    return dict(row) if row else {}


def _score_for_status(settings: dict, status: str) -> int:
    mapping = {
        "Paid": int(settings.get("rent_score_paid", 100) or 100),
        "Partially Paid": int(settings.get("rent_score_partially_paid", 75) or 75),
        "Paid Late": int(settings.get("rent_score_paid_late", 75) or 75),
        "Not Paid": int(settings.get("rent_score_not_paid", 0) or 0),
        "Exempt": int(settings.get("rent_score_exempt", 100) or 100),
    }
    return mapping.get(status, 0)


def _derive_status(total_due: float, amount_paid: float, paid_date: str | None, is_exempt: bool, late_fee_charge: float) -> str:
    if is_exempt:
        return "Exempt"
    if amount_paid <= 0:
        return "Not Paid"
    if amount_paid < total_due:
        return "Partially Paid"
    if late_fee_charge > 0:
        return "Paid Late"
    if paid_date:
        return "Paid"
    return "Paid"


def _active_residents_for_shelter(shelter: str):
    ph = _placeholder()
    return db_fetchall(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND is_active = {('TRUE' if g.get('db_kind') == 'pg' else '1')}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )


def _active_rent_config_for_resident(resident_id: int, shelter: str):
    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT *
        FROM resident_rent_configs
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND COALESCE(effective_end_date, '') = ''
        ORDER BY effective_start_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None


def _ensure_default_rent_config(resident_id: int, shelter: str) -> dict:
    config = _active_rent_config_for_resident(resident_id, shelter)
    if config:
        return config

    now = utcnow_iso()
    today = _today_chicago().date().isoformat()

    db_execute(
        (
            """
            INSERT INTO resident_rent_configs (
                resident_id,
                shelter,
                level_snapshot,
                apartment_size_snapshot,
                monthly_rent,
                is_exempt,
                effective_start_date,
                effective_end_date,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            INSERT INTO resident_rent_configs (
                resident_id,
                shelter,
                level_snapshot,
                apartment_size_snapshot,
                monthly_rent,
                is_exempt,
                effective_start_date,
                effective_end_date,
                created_by_staff_user_id,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        ),
        (
            resident_id,
            shelter,
            None,
            None,
            0.0,
            False if g.get("db_kind") == "pg" else 0,
            today,
            None,
            session.get("staff_user_id"),
            now,
            now,
        ),
    )

    return _active_rent_config_for_resident(resident_id, shelter) or {}


def _program_enrollment_for_month(resident_id: int, shelter: str, rent_year: int, rent_month: int) -> dict | None:
    month_start, month_end = _month_start_end(rent_year, rent_month)
    ph = _placeholder()

    row = db_fetchone(
        f"""
        SELECT *
        FROM program_enrollments
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND entry_date <= {ph}
          AND (
                COALESCE(exit_date, '') = ''
                OR exit_date >= {ph}
          )
        ORDER BY entry_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter, month_end.isoformat(), month_start.isoformat()),
    )
    return dict(row) if row else None


def _derive_base_monthly_rent(settings: dict, shelter: str, config: dict) -> tuple[float, str]:
    manual_rent = _float_value(config.get("monthly_rent"))
    if manual_rent > 0:
        return manual_rent, "Manual override from resident rent setup"

    if _bool_value(config.get("is_exempt")):
        return 0.0, "Resident marked exempt"

    level = str(config.get("level_snapshot") or "").strip()
    apartment_size = str(config.get("apartment_size_snapshot") or "").strip().lower()

    if shelter == "haven":
        return _float_value(settings.get("hh_rent_amount", 150.00)), "Haven base rent from admin settings"

    if shelter == "gratitude":
        if level == "5":
            if "one" in apartment_size:
                return _float_value(settings.get("gh_level_5_one_bedroom_rent", 250.00)), "Gratitude level 5 one bedroom rate"
            if "two" in apartment_size:
                return _float_value(settings.get("gh_level_5_two_bedroom_rent", 300.00)), "Gratitude level 5 two bedroom rate"
            if "town" in apartment_size:
                return _float_value(settings.get("gh_level_5_townhome_rent", 300.00)), "Gratitude level 5 townhome rate"
            return _float_value(settings.get("gh_level_5_one_bedroom_rent", 250.00)), "Gratitude level 5 defaulted to one bedroom rate"

        if level == "8":
            if manual_rent > 0:
                return manual_rent, "Manual level 8 override"
            return 0.0, "Level 8 sliding scale still needs a resident specific monthly override amount"

    return manual_rent, "No matching automatic rent rule"


def _calculate_proration(
    base_monthly_rent: float,
    config: dict,
    enrollment: dict | None,
    rent_year: int,
    rent_month: int,
) -> dict:
    month_start, month_end = _month_start_end(rent_year, rent_month)
    month_day_count = _days_in_month(rent_year, rent_month)

    occupancy_start = month_start
    occupancy_end = month_end
    notes: list[str] = []

    enrollment_entry = _parse_iso_date(enrollment.get("entry_date") if enrollment else None)
    enrollment_exit = _parse_iso_date(enrollment.get("exit_date") if enrollment else None)
    config_start = _parse_iso_date(config.get("effective_start_date"))

    if enrollment_entry and enrollment_entry > occupancy_start:
        occupancy_start = enrollment_entry
        notes.append("Move in proration applied from program entry date")
    elif config_start and config_start.year == rent_year and config_start.month == rent_month and config_start > occupancy_start:
        occupancy_start = config_start
        notes.append("Proration applied from rent setup effective start date")

    if enrollment_exit and enrollment_exit < occupancy_end:
        occupancy_end = enrollment_exit
        notes.append("Move out proration applied through program exit date")

    if occupancy_end < occupancy_start:
        occupied_days = 0
        prorated_charge = 0.0
    else:
        occupied_days = (occupancy_end - occupancy_start).days + 1
        prorated_charge = round((base_monthly_rent * occupied_days) / month_day_count, 2)

    if occupied_days == month_day_count and base_monthly_rent > 0:
        notes.append("Full month charge")
    elif occupied_days == 0:
        notes.append("No occupied days in this month")

    return {
        "occupancy_start_date": occupancy_start.isoformat() if occupied_days > 0 else "",
        "occupancy_end_date": occupancy_end.isoformat() if occupied_days > 0 else "",
        "occupied_days": occupied_days,
        "month_day_count": month_day_count,
        "prorated_charge": prorated_charge,
        "notes": notes,
    }


def _late_start_day(settings: dict, shelter: str) -> int:
    if shelter == "haven":
        return _int_value(settings.get("hh_rent_late_day"), 5)
    return _int_value(settings.get("rent_late_day_of_month"), 6)


def _late_fee_per_day(settings: dict, shelter: str) -> float:
    if shelter == "haven":
        return _float_value(settings.get("hh_rent_late_fee_per_day"))
    if shelter == "gratitude":
        return _float_value(settings.get("gh_rent_late_fee_per_day"))
    return 0.0


def _calculate_late_fee(
    settings: dict,
    shelter: str,
    rent_year: int,
    rent_month: int,
    subtotal_due: float,
    paid_date: str | None,
    approved_late_arrangement: bool,
    is_exempt: bool,
) -> tuple[float, str]:
    if is_exempt or approved_late_arrangement or subtotal_due <= 0:
        if approved_late_arrangement:
            return 0.0, "Late fee waived by approved arrangement"
        return 0.0, ""

    month_start, month_end = _month_start_end(rent_year, rent_month)
    late_start_day = _late_start_day(settings, shelter)
    fee_per_day = _late_fee_per_day(settings, shelter)

    if fee_per_day <= 0:
        return 0.0, ""

    if late_start_day < 1:
        late_start_day = 1
    if late_start_day > month_end.day:
        late_start_day = month_end.day

    late_start_date = date(rent_year, rent_month, late_start_day)
    parsed_paid_date = _parse_iso_date(paid_date)

    if parsed_paid_date:
        window_end = min(parsed_paid_date, month_end)
    else:
        today = _today_chicago().date()
        if today.year == rent_year and today.month == rent_month:
            window_end = min(today, month_end)
        elif (today.year, today.month) > (rent_year, rent_month):
            window_end = month_end
        else:
            return 0.0, ""

    if window_end < late_start_date:
        return 0.0, ""

    late_days = (window_end - late_start_date).days + 1
    if late_days <= 0:
        return 0.0, ""

    return round(late_days * fee_per_day, 2), f"Late fee applied for {late_days} day(s)"


def _latest_prior_balance(resident_id: int, shelter: str, carry_forward_enabled: bool, rent_year: int, rent_month: int) -> float:
    if not carry_forward_enabled:
        return 0.0

    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT e.remaining_balance
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE e.resident_id = {ph}
          AND LOWER(COALESCE(e.shelter_snapshot, '')) = {ph}
          AND (
                s.rent_year < {ph}
                OR (s.rent_year = {ph} AND s.rent_month < {ph})
          )
        ORDER BY s.rent_year DESC, s.rent_month DESC, e.id DESC
        LIMIT 1
        """,
        (resident_id, shelter, rent_year, rent_year, rent_month),
    )
    return _float_value(row.get("remaining_balance") if row else 0)


def _ensure_sheet_for_month(shelter: str, rent_year: int, rent_month: int):
    _ensure_tables()
    settings = _load_settings(shelter)
    ph = _placeholder()

    sheet = db_fetchone(
        f"""
        SELECT *
        FROM resident_rent_sheets
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND rent_year = {ph}
          AND rent_month = {ph}
        LIMIT 1
        """,
        (shelter, rent_year, rent_month),
    )

    if not sheet:
        now = utcnow_iso()
        generated_on = _today_chicago().date().isoformat()
        db_execute(
            (
                """
                INSERT INTO resident_rent_sheets (
                    shelter,
                    rent_year,
                    rent_month,
                    generated_on,
                    created_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """
                if g.get("db_kind") == "pg"
                else
                """
                INSERT INTO resident_rent_sheets (
                    shelter,
                    rent_year,
                    rent_month,
                    generated_on,
                    created_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (shelter, rent_year, rent_month, generated_on, session.get("staff_user_id"), now, now),
        )

        sheet = db_fetchone(
            f"""
            SELECT *
            FROM resident_rent_sheets
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
              AND rent_year = {ph}
              AND rent_month = {ph}
            LIMIT 1
            """,
            (shelter, rent_year, rent_month),
        )

    sheet = dict(sheet)

    for resident in _active_residents_for_shelter(shelter):
        resident_id = resident["id"]

        existing = db_fetchone(
            f"SELECT * FROM resident_rent_sheet_entries WHERE sheet_id = {ph} AND resident_id = {ph} LIMIT 1",
            (sheet["id"], resident_id),
        )
        existing = dict(existing) if existing else None

        config = _ensure_default_rent_config(resident_id, shelter)
        enrollment = _program_enrollment_for_month(resident_id, shelter, rent_year, rent_month)

        carry_forward_enabled = _bool_value(settings.get("rent_carry_forward_enabled", True))
        prior_balance = _latest_prior_balance(resident_id, shelter, carry_forward_enabled, rent_year, rent_month)
        is_exempt = _bool_value(config.get("is_exempt"))

        base_monthly_rent, base_note = _derive_base_monthly_rent(settings, shelter, config)
        proration = _calculate_proration(base_monthly_rent, config, enrollment, rent_year, rent_month)

        approved_late_arrangement = _bool_value(existing.get("approved_late_arrangement") if existing else False)
        manual_adjustment = _float_value(existing.get("manual_adjustment") if existing else 0)
        amount_paid = _float_value(existing.get("amount_paid") if existing else 0)
        paid_date = (existing.get("paid_date") if existing else None) or None
        notes = (existing.get("notes") if existing else None) or None

        subtotal_due = round(prior_balance + proration["prorated_charge"] + manual_adjustment, 2)
        late_fee_charge, late_fee_note = _calculate_late_fee(
            settings=settings,
            shelter=shelter,
            rent_year=rent_year,
            rent_month=rent_month,
            subtotal_due=subtotal_due,
            paid_date=paid_date,
            approved_late_arrangement=approved_late_arrangement,
            is_exempt=is_exempt,
        )
        total_due = 0.0 if is_exempt else round(subtotal_due + late_fee_charge, 2)
        current_charge = 0.0 if is_exempt else round(proration["prorated_charge"] + manual_adjustment, 2)
        remaining_balance = 0.0 if is_exempt else round(max(total_due - amount_paid, 0.0), 2)
        status = _derive_status(total_due, amount_paid, paid_date, is_exempt, late_fee_charge)
        compliance_score = _score_for_status(settings, status)
        resident_name = f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip()
        calculation_notes = [base_note] + proration["notes"]
        if late_fee_note:
            calculation_notes.append(late_fee_note)
        now = utcnow_iso()

        if existing:
            db_execute(
                (
                    """
                    UPDATE resident_rent_sheet_entries
                    SET shelter_snapshot = %s,
                        resident_name_snapshot = %s,
                        level_snapshot = %s,
                        apartment_size_snapshot = %s,
                        prior_balance = %s,
                        current_charge = %s,
                        total_due = %s,
                        amount_paid = %s,
                        remaining_balance = %s,
                        status = %s,
                        compliance_score = %s,
                        paid_date = %s,
                        notes = %s,
                        occupancy_start_date = %s,
                        occupancy_end_date = %s,
                        occupied_days = %s,
                        month_day_count = %s,
                        base_monthly_rent = %s,
                        prorated_charge = %s,
                        late_fee_charge = %s,
                        manual_adjustment = %s,
                        approved_late_arrangement = %s,
                        calculation_notes = %s,
                        updated_by_staff_user_id = %s,
                        updated_at = %s
                    WHERE id = %s
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    UPDATE resident_rent_sheet_entries
                    SET shelter_snapshot = ?,
                        resident_name_snapshot = ?,
                        level_snapshot = ?,
                        apartment_size_snapshot = ?,
                        prior_balance = ?,
                        current_charge = ?,
                        total_due = ?,
                        amount_paid = ?,
                        remaining_balance = ?,
                        status = ?,
                        compliance_score = ?,
                        paid_date = ?,
                        notes = ?,
                        occupancy_start_date = ?,
                        occupancy_end_date = ?,
                        occupied_days = ?,
                        month_day_count = ?,
                        base_monthly_rent = ?,
                        prorated_charge = ?,
                        late_fee_charge = ?,
                        manual_adjustment = ?,
                        approved_late_arrangement = ?,
                        calculation_notes = ?,
                        updated_by_staff_user_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """
                ),
                (
                    shelter,
                    resident_name,
                    config.get("level_snapshot"),
                    config.get("apartment_size_snapshot"),
                    prior_balance,
                    current_charge,
                    total_due,
                    amount_paid,
                    remaining_balance,
                    status,
                    compliance_score,
                    paid_date,
                    notes,
                    proration["occupancy_start_date"],
                    proration["occupancy_end_date"],
                    proration["occupied_days"],
                    proration["month_day_count"],
                    base_monthly_rent,
                    proration["prorated_charge"],
                    late_fee_charge,
                    manual_adjustment,
                    approved_late_arrangement if g.get("db_kind") == "pg" else (1 if approved_late_arrangement else 0),
                    "\n".join([note for note in calculation_notes if note]),
                    session.get("staff_user_id"),
                    now,
                    existing["id"],
                ),
            )
        else:
            db_execute(
                (
                    """
                    INSERT INTO resident_rent_sheet_entries (
                        sheet_id,
                        resident_id,
                        shelter_snapshot,
                        resident_name_snapshot,
                        level_snapshot,
                        apartment_size_snapshot,
                        prior_balance,
                        current_charge,
                        total_due,
                        amount_paid,
                        remaining_balance,
                        status,
                        compliance_score,
                        paid_date,
                        notes,
                        occupancy_start_date,
                        occupancy_end_date,
                        occupied_days,
                        month_day_count,
                        base_monthly_rent,
                        prorated_charge,
                        late_fee_charge,
                        manual_adjustment,
                        approved_late_arrangement,
                        calculation_notes,
                        updated_by_staff_user_id,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    INSERT INTO resident_rent_sheet_entries (
                        sheet_id,
                        resident_id,
                        shelter_snapshot,
                        resident_name_snapshot,
                        level_snapshot,
                        apartment_size_snapshot,
                        prior_balance,
                        current_charge,
                        total_due,
                        amount_paid,
                        remaining_balance,
                        status,
                        compliance_score,
                        paid_date,
                        notes,
                        occupancy_start_date,
                        occupancy_end_date,
                        occupied_days,
                        month_day_count,
                        base_monthly_rent,
                        prorated_charge,
                        late_fee_charge,
                        manual_adjustment,
                        approved_late_arrangement,
                        calculation_notes,
                        updated_by_staff_user_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    sheet["id"],
                    resident_id,
                    shelter,
                    resident_name,
                    config.get("level_snapshot"),
                    config.get("apartment_size_snapshot"),
                    prior_balance,
                    current_charge,
                    total_due,
                    amount_paid,
                    remaining_balance,
                    status,
                    compliance_score,
                    paid_date,
                    notes,
                    proration["occupancy_start_date"],
                    proration["occupancy_end_date"],
                    proration["occupied_days"],
                    proration["month_day_count"],
                    base_monthly_rent,
                    proration["prorated_charge"],
                    late_fee_charge,
                    manual_adjustment,
                    approved_late_arrangement if g.get("db_kind") == "pg" else (1 if approved_late_arrangement else 0),
                    "\n".join([note for note in calculation_notes if note]),
                    session.get("staff_user_id"),
                    now,
                    now,
                ),
            )

    return sheet, settings


def _load_sheet_entries(sheet_id: int):
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT *
        FROM resident_rent_sheet_entries
        WHERE sheet_id = {ph}
        ORDER BY resident_name_snapshot ASC, id ASC
        """,
        (sheet_id,),
    )
    return [dict(row) for row in rows]


@rent_tracking.get("/roll")
@require_login
@require_shelter
def rent_roll():
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    _ensure_tables()
    settings = _load_settings(shelter)

    rows = []
    for resident in _active_residents_for_shelter(shelter):
        config = _ensure_default_rent_config(resident["id"], shelter)
        auto_rent, auto_note = _derive_base_monthly_rent(settings, shelter, config)
        manual_override = _float_value(config.get("monthly_rent"))
        rows.append(
            {
                "resident_id": resident["id"],
                "resident_name": f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip(),
                "level_snapshot": config.get("level_snapshot"),
                "apartment_size_snapshot": config.get("apartment_size_snapshot"),
                "monthly_rent": manual_override if manual_override > 0 else auto_rent,
                "manual_monthly_rent": manual_override,
                "auto_monthly_rent": auto_rent,
                "rent_source_note": auto_note,
                "is_exempt": _bool_value(config.get("is_exempt")),
            }
        )

    rows.sort(key=lambda row: row["resident_name"].lower())

    return render_template(
        "case_management/rent_roll.html",
        shelter=shelter,
        rows=rows,
    )


@rent_tracking.route("/entry", methods=["GET", "POST"])
@require_login
@require_shelter
def payment_entry_sheet():
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    rent_year = request.args.get("year", type=int)
    rent_month = request.args.get("month", type=int)
    if not rent_year or not rent_month:
        rent_year, rent_month = _current_year_month()

    sheet, settings = _ensure_sheet_for_month(shelter, rent_year, rent_month)
    entries = _load_sheet_entries(sheet["id"])

    if request.method == "POST":
        for entry in entries:
            entry_id = entry["id"]
            amount_paid = _float_value(request.form.get(f"amount_paid_{entry_id}"))
            paid_date = (request.form.get(f"paid_date_{entry_id}") or "").strip() or None
            notes = (request.form.get(f"notes_{entry_id}") or "").strip() or None
            manual_adjustment = _float_value(request.form.get(f"manual_adjustment_{entry_id}"))
            approved_late_arrangement = (request.form.get(f"approved_late_arrangement_{entry_id}") or "").strip().lower() == "yes"

            subtotal_due = round(
                _float_value(entry.get("prior_balance"))
                + _float_value(entry.get("prorated_charge"))
                + manual_adjustment,
                2,
            )
            is_exempt = str(entry.get("status") or "").strip() == "Exempt"
            late_fee_charge, _late_fee_note = _calculate_late_fee(
                settings=settings,
                shelter=shelter,
                rent_year=rent_year,
                rent_month=rent_month,
                subtotal_due=subtotal_due,
                paid_date=paid_date,
                approved_late_arrangement=approved_late_arrangement,
                is_exempt=is_exempt,
            )
            total_due = 0.0 if is_exempt else round(subtotal_due + late_fee_charge, 2)
            current_charge = 0.0 if is_exempt else round(_float_value(entry.get("prorated_charge")) + manual_adjustment, 2)
            remaining_balance = 0.0 if is_exempt else round(max(total_due - amount_paid, 0.0), 2)
            status = _derive_status(total_due, amount_paid, paid_date, is_exempt, late_fee_charge)
            compliance_score = _score_for_status(settings, status)
            calculation_notes = (entry.get("calculation_notes") or "").strip()
            now = utcnow_iso()

            db_execute(
                (
                    """
                    UPDATE resident_rent_sheet_entries
                    SET current_charge = %s,
                        total_due = %s,
                        amount_paid = %s,
                        remaining_balance = %s,
                        status = %s,
                        compliance_score = %s,
                        paid_date = %s,
                        notes = %s,
                        late_fee_charge = %s,
                        manual_adjustment = %s,
                        approved_late_arrangement = %s,
                        calculation_notes = %s,
                        updated_by_staff_user_id = %s,
                        updated_at = %s
                    WHERE id = %s
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    UPDATE resident_rent_sheet_entries
                    SET current_charge = ?,
                        total_due = ?,
                        amount_paid = ?,
                        remaining_balance = ?,
                        status = ?,
                        compliance_score = ?,
                        paid_date = ?,
                        notes = ?,
                        late_fee_charge = ?,
                        manual_adjustment = ?,
                        approved_late_arrangement = ?,
                        calculation_notes = ?,
                        updated_by_staff_user_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """
                ),
                (
                    current_charge,
                    total_due,
                    amount_paid,
                    remaining_balance,
                    status,
                    compliance_score,
                    paid_date,
                    notes,
                    late_fee_charge,
                    manual_adjustment,
                    approved_late_arrangement if g.get("db_kind") == "pg" else (1 if approved_late_arrangement else 0),
                    calculation_notes,
                    session.get("staff_user_id"),
                    now,
                    entry_id,
                ),
            )

        flash("Rent payment sheet saved.", "ok")
        return redirect(url_for("rent_tracking.payment_entry_sheet", year=rent_year, month=rent_month))

    return render_template(
        "case_management/rent_entry.html",
        shelter=shelter,
        sheet=sheet,
        entries=entries,
        month_label=_month_label(rent_year, rent_month),
    )


@rent_tracking.route("/resident/<int:resident_id>/config", methods=["GET", "POST"])
@require_login
@require_shelter
def resident_rent_config(resident_id: int):
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    _ensure_tables()
    shelter = _normalize_shelter_name(session.get("shelter"))
    settings = _load_settings(shelter)
    ph = _placeholder()

    resident = db_fetchone(
        f"""
        SELECT id, first_name, last_name, shelter
        FROM residents
        WHERE id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("rent_tracking.rent_roll"))

    resident = dict(resident)
    current_config = _ensure_default_rent_config(resident_id, shelter)
    auto_monthly_rent, auto_rent_note = _derive_base_monthly_rent(settings, shelter, current_config)
    history = db_fetchall(
        f"""
        SELECT *
        FROM resident_rent_configs
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
        ORDER BY effective_start_date DESC, id DESC
        """,
        (resident_id, shelter),
    )

    if request.method == "POST":
        level_snapshot = (request.form.get("level_snapshot") or "").strip() or None
        apartment_size_snapshot = (request.form.get("apartment_size_snapshot") or "").strip() or None
        monthly_rent = _float_value(request.form.get("monthly_rent"))
        is_exempt = (request.form.get("is_exempt") or "no").strip().lower() == "yes"
        effective_start_date = (request.form.get("effective_start_date") or _today_chicago().date().isoformat()).strip()
        now = utcnow_iso()

        db_execute(
            (
                """
                UPDATE resident_rent_configs
                SET effective_end_date = %s,
                    updated_at = %s
                WHERE resident_id = %s
                  AND LOWER(COALESCE(shelter, '')) = %s
                  AND COALESCE(effective_end_date, '') = ''
                """
                if g.get("db_kind") == "pg"
                else
                """
                UPDATE resident_rent_configs
                SET effective_end_date = ?,
                    updated_at = ?
                WHERE resident_id = ?
                  AND LOWER(COALESCE(shelter, '')) = ?
                  AND COALESCE(effective_end_date, '') = ''
                """
            ),
            (effective_start_date, now, resident_id, shelter),
        )

        db_execute(
            (
                """
                INSERT INTO resident_rent_configs (
                    resident_id,
                    shelter,
                    level_snapshot,
                    apartment_size_snapshot,
                    monthly_rent,
                    is_exempt,
                    effective_start_date,
                    effective_end_date,
                    created_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """
                if g.get("db_kind") == "pg"
                else
                """
                INSERT INTO resident_rent_configs (
                    resident_id,
                    shelter,
                    level_snapshot,
                    apartment_size_snapshot,
                    monthly_rent,
                    is_exempt,
                    effective_start_date,
                    effective_end_date,
                    created_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
            ),
            (
                resident_id,
                shelter,
                level_snapshot,
                apartment_size_snapshot,
                monthly_rent,
                is_exempt if g.get("db_kind") == "pg" else (1 if is_exempt else 0),
                effective_start_date,
                None,
                session.get("staff_user_id"),
                now,
                now,
            ),
        )

        flash("Resident rent setup updated.", "ok")
        return redirect(url_for("rent_tracking.resident_rent_config", resident_id=resident_id))

    return render_template(
        "case_management/resident_rent_config.html",
        resident=resident,
        current_config=current_config,
        history=history,
        auto_monthly_rent=auto_monthly_rent,
        auto_rent_note=auto_rent_note,
    )


@rent_tracking.get("/resident/<int:resident_id>/history")
@require_login
@require_shelter
def resident_rent_history(resident_id: int):
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
            e.*,
            s.rent_year,
            s.rent_month
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        WHERE e.resident_id = {ph}
        ORDER BY s.rent_year DESC, s.rent_month DESC, e.id DESC
        """,
        (resident_id,),
    )

    rent_snapshot = build_rent_stability_snapshot(resident_id)

    return render_template(
        "case_management/resident_rent_history.html",
        resident=resident,
        rows=rows,
        rent_snapshot=rent_snapshot,
    )
