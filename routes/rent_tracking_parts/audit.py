from __future__ import annotations

from datetime import datetime

from flask import flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone
from routes.rent_tracking_parts.access import _allowed, _normalize_shelter_name
from routes.rent_tracking_parts.dates import _current_year_month, _month_label
from routes.rent_tracking_parts.schema import _ensure_tables
from routes.rent_tracking_parts.utils import _float_value, _placeholder


def _parse_year_month() -> tuple[int, int]:
    current_year, current_month = _current_year_month()

    try:
        year = int(request.args.get("year") or current_year)
    except Exception:
        year = current_year

    try:
        month = int(request.args.get("month") or current_month)
    except Exception:
        month = current_month

    if month < 1 or month > 12:
        month = current_month

    if year < 2000 or year > 2100:
        year = current_year

    return year, month


def _monthly_charge_rows(*, shelter: str, rent_year: int, rent_month: int) -> list[dict]:
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT
            e.id AS sheet_entry_id,
            e.resident_id,
            e.enrollment_id,
            e.resident_name_snapshot,
            e.level_snapshot,
            e.apartment_number_snapshot,
            e.apartment_size_snapshot,
            e.prorated_charge,
            e.manual_adjustment,
            e.prior_balance,
            e.total_due,
            e.amount_paid,
            e.remaining_balance,
            e.status,
            e.calculation_notes,
            l.id AS ledger_entry_id,
            l.entry_date AS ledger_entry_date,
            l.debit_amount AS ledger_debit_amount,
            l.source_code AS ledger_source_code,
            l.created_at AS ledger_created_at
        FROM resident_rent_sheet_entries e
        JOIN resident_rent_sheets s ON s.id = e.sheet_id
        LEFT JOIN resident_rent_ledger_entries l
          ON l.related_sheet_entry_id = e.id
         AND l.source_code = {ph}
         AND COALESCE(l.voided, FALSE) = FALSE
        WHERE LOWER(COALESCE(s.shelter, '')) = {ph}
          AND s.rent_year = {ph}
          AND s.rent_month = {ph}
        ORDER BY
            COALESCE(e.apartment_number_snapshot, '') ASC,
            e.resident_name_snapshot ASC,
            e.id ASC
        """,
        ("monthly_rent_charge", shelter, rent_year, rent_month),
    )
    return [dict(row) for row in rows or []]


def _sheet_row(*, shelter: str, rent_year: int, rent_month: int) -> dict | None:
    ph = _placeholder()
    row = db_fetchone(
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
    return dict(row) if row else None


def _audit_summary(rows: list[dict]) -> dict:
    expected_count = 0
    posted_count = 0
    missing_count = 0
    exempt_or_zero_count = 0
    expected_total = 0.0
    posted_total = 0.0

    for row in rows:
        expected_charge = round(_float_value(row.get("prorated_charge")), 2)
        ledger_amount = round(_float_value(row.get("ledger_debit_amount")), 2)
        has_ledger = bool(row.get("ledger_entry_id"))

        if expected_charge > 0:
            expected_count += 1
            expected_total += expected_charge
            if has_ledger:
                posted_count += 1
                posted_total += ledger_amount
            else:
                missing_count += 1
        else:
            exempt_or_zero_count += 1

    return {
        "row_count": len(rows),
        "expected_count": expected_count,
        "posted_count": posted_count,
        "missing_count": missing_count,
        "exempt_or_zero_count": exempt_or_zero_count,
        "expected_total": round(expected_total, 2),
        "posted_total": round(posted_total, 2),
        "difference_total": round(expected_total - posted_total, 2),
    }


def _available_months(shelter: str) -> list[dict]:
    ph = _placeholder()
    rows = db_fetchall(
        f"""
        SELECT rent_year, rent_month
        FROM resident_rent_sheets
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
        ORDER BY rent_year DESC, rent_month DESC
        LIMIT 24
        """,
        (shelter,),
    )
    return [
        {
            "year": int(row["rent_year"]),
            "month": int(row["rent_month"]),
            "label": _month_label(int(row["rent_year"]), int(row["rent_month"])),
        }
        for row in rows or []
    ]


def register_audit_routes(rent_tracking):
    @rent_tracking.get("/posting-audit")
    @require_login
    @require_shelter
    def rent_posting_audit():
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        shelter = _normalize_shelter_name(session.get("shelter"))
        _ensure_tables()
        rent_year, rent_month = _parse_year_month()
        month_label = _month_label(rent_year, rent_month)
        sheet = _sheet_row(shelter=shelter, rent_year=rent_year, rent_month=rent_month)
        rows = _monthly_charge_rows(
            shelter=shelter,
            rent_year=rent_year,
            rent_month=rent_month,
        ) if sheet else []
        summary = _audit_summary(rows)
        available_months = _available_months(shelter)

        return render_template(
            "case_management/rent_posting_audit.html",
            shelter=shelter,
            rent_year=rent_year,
            rent_month=rent_month,
            month_label=month_label,
            sheet=sheet,
            rows=rows,
            summary=summary,
            available_months=available_months,
            checked_at=datetime.now().replace(microsecond=0).isoformat(),
        )
