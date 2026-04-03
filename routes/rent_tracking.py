from __future__ import annotations

from datetime import datetime
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
                inspection_default_item_status,
                inspection_item_labels,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def _derive_status(settings: dict, total_due: float, amount_paid: float, paid_date: str | None, is_exempt: bool) -> str:
    if is_exempt:
        return "Exempt"

    if amount_paid <= 0:
        return "Not Paid"

    if amount_paid < total_due:
        return "Partially Paid"

    late_day = int(settings.get("rent_late_day_of_month", 6) or 6)
    if paid_date:
        try:
            dt = datetime.fromisoformat(paid_date)
            if dt.day >= late_day:
                return "Paid Late"
        except Exception:
            pass

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


def _latest_prior_balance(resident_id: int, shelter: str, carry_forward_enabled: bool) -> float:
    if not carry_forward_enabled:
        return 0.0

    ph = _placeholder()
    row = db_fetchone(
        f"""
        SELECT remaining_balance
        FROM resident_rent_sheet_entries
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter_snapshot, '')) = {ph}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
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
            f"SELECT id FROM resident_rent_sheet_entries WHERE sheet_id = {ph} AND resident_id = {ph} LIMIT 1",
            (sheet["id"], resident_id),
        )
        if existing:
            continue

        config = _ensure_default_rent_config(resident_id, shelter)
        carry_forward_enabled = bool(settings.get("rent_carry_forward_enabled", True))
        prior_balance = _latest_prior_balance(resident_id, shelter, carry_forward_enabled)
        monthly_rent = _float_value(config.get("monthly_rent"))
        is_exempt = bool(config.get("is_exempt"))
        current_charge = 0.0 if is_exempt else monthly_rent
        total_due = round(prior_balance + current_charge, 2)
        paid_date = None
        amount_paid = 0.0
        remaining_balance = 0.0 if is_exempt else total_due
        status = "Exempt" if is_exempt else "Not Paid"
        compliance_score = _score_for_status(settings, status)
        resident_name = f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip()
        now = utcnow_iso()

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
                    updated_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    updated_by_staff_user_id,
                    created_at,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                None,
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


def _weighted_score_for_resident(resident_id: int) -> int | None:
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT compliance_score
        FROM resident_rent_sheet_entries
        WHERE resident_id = {ph}
        ORDER BY id DESC
        LIMIT 6
        """,
        (resident_id,),
    )
    values = [int(row["compliance_score"]) for row in rows if row.get("compliance_score") is not None]
    if not values:
        return None
    return round(sum(values) / len(values))


@rent_tracking.get("/roll")
@require_login
@require_shelter
def rent_roll():
    if not _allowed():
        flash("Case manager, shelter director, or admin access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    _ensure_tables()

    rows = []
    for resident in _active_residents_for_shelter(shelter):
        config = _ensure_default_rent_config(resident["id"], shelter)
        rows.append(
            {
                "resident_id": resident["id"],
                "resident_name": f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip(),
                "level_snapshot": config.get("level_snapshot"),
                "apartment_size_snapshot": config.get("apartment_size_snapshot"),
                "monthly_rent": _float_value(config.get("monthly_rent")),
                "is_exempt": bool(config.get("is_exempt")),
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

            total_due = _float_value(entry.get("total_due"))
            is_exempt = str(entry.get("status") or "").strip() == "Exempt"
            status = _derive_status(settings, total_due, amount_paid, paid_date, is_exempt)
            remaining_balance = 0.0 if is_exempt else round(max(total_due - amount_paid, 0.0), 2)
            compliance_score = _score_for_status(settings, status)
            now = utcnow_iso()

            db_execute(
                (
                    """
                    UPDATE resident_rent_sheet_entries
                    SET amount_paid = %s,
                        remaining_balance = %s,
                        status = %s,
                        compliance_score = %s,
                        paid_date = %s,
                        notes = %s,
                        updated_by_staff_user_id = %s,
                        updated_at = %s
                    WHERE id = %s
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    UPDATE resident_rent_sheet_entries
                    SET amount_paid = ?,
                        remaining_balance = ?,
                        status = ?,
                        compliance_score = ?,
                        paid_date = ?,
                        notes = ?,
                        updated_by_staff_user_id = ?,
                        updated_at = ?
                    WHERE id = ?
                    """
                ),
                (
                    amount_paid,
                    remaining_balance,
                    status,
                    compliance_score,
                    paid_date,
                    notes,
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

    weighted_score = _weighted_score_for_resident(resident_id)

    return render_template(
        "case_management/resident_rent_history.html",
        resident=resident,
        rows=rows,
        weighted_score=weighted_score,
    )
