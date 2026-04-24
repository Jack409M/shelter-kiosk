from __future__ import annotations

from flask import flash, g, redirect, render_template, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_fetchone

from .access import _allowed, _normalize_shelter_name
from .calculations import (
    _derive_apartment_size_from_assignment,
    _derive_base_monthly_rent,
    _normalize_apartment_number,
)
from .data_access import (
    _active_residents_for_shelter,
    _ensure_default_rent_config,
    _ledger_summary_for_resident,
    _load_sheet_entries,
)
from .dates import _current_year_month, _month_label
from .schema import _ensure_tables
from .settings import _load_settings
from .utils import _bool_value, _float_value, _placeholder
from .views import _ensure_sheet_for_month, _post_monthly_charge_ledger_entries


def _monthly_rent_posted_for_shelter(shelter: str, rent_year: int, rent_month: int) -> bool:
    ph = _placeholder()
    false_value = "FALSE" if g.get("db_kind") == "pg" else "0"
    row = db_fetchone(
        f"""
        SELECT id
        FROM resident_rent_ledger_entries
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND related_month_year = {ph}
          AND related_month_month = {ph}
          AND source_code = {ph}
          AND COALESCE(voided, {false_value}) = {false_value}
        LIMIT 1
        """,
        (shelter, rent_year, rent_month, "monthly_rent_charge"),
    )
    return bool(row)


def register_rent_roll_routes(rent_tracking):
    @rent_tracking.get("/roll")
    @require_login
    @require_shelter
    def rent_roll():
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        shelter = _normalize_shelter_name(session.get("shelter"))
        _ensure_tables()
        settings = _load_settings(shelter)
        rent_year, rent_month = _current_year_month()
        rent_month_label = _month_label(rent_year, rent_month)
        monthly_rent_posted = _monthly_rent_posted_for_shelter(
            shelter,
            rent_year,
            rent_month,
        )

        rows = []
        for resident in _active_residents_for_shelter(shelter):
            config = _ensure_default_rent_config(resident["id"], shelter)
            apartment_number_snapshot = _normalize_apartment_number(
                shelter,
                config.get("apartment_number_snapshot"),
            )
            apartment_size_snapshot = (
                _derive_apartment_size_from_assignment(shelter, apartment_number_snapshot)
                or config.get("apartment_size_snapshot")
            )
            config["apartment_number_snapshot"] = apartment_number_snapshot
            config["apartment_size_snapshot"] = apartment_size_snapshot

            auto_rent, auto_note = _derive_base_monthly_rent(settings, shelter, config)
            manual_override = _float_value(config.get("monthly_rent"))
            ledger_summary = _ledger_summary_for_resident(resident["id"])

            rows.append(
                {
                    "resident_id": resident["id"],
                    "resident_name": f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip(),
                    "level_snapshot": config.get("level_snapshot"),
                    "apartment_number_snapshot": apartment_number_snapshot,
                    "apartment_size_snapshot": apartment_size_snapshot,
                    "monthly_rent": manual_override if manual_override > 0 else auto_rent,
                    "manual_monthly_rent": manual_override,
                    "auto_monthly_rent": auto_rent,
                    "rent_source_note": auto_note,
                    "is_exempt": _bool_value(config.get("is_exempt")),
                    "current_due": ledger_summary.get("current_due", 0.0),
                    "current_credit": ledger_summary.get("current_credit", 0.0),
                }
            )

        rows.sort(key=lambda row: row["resident_name"].lower())

        return render_template(
            "case_management/rent_roll.html",
            shelter=shelter,
            rows=rows,
            rent_month_label=rent_month_label,
            monthly_rent_posted=monthly_rent_posted,
        )

    @rent_tracking.post("/roll/generate-monthly-charges")
    @require_login
    @require_shelter
    def generate_monthly_rent_charges():
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        shelter = _normalize_shelter_name(session.get("shelter"))
        _ensure_tables()
        rent_year, rent_month = _current_year_month()
        sheet, settings = _ensure_sheet_for_month(shelter, rent_year, rent_month)
        entries = _load_sheet_entries(sheet["id"])

        already_posted = _monthly_rent_posted_for_shelter(shelter, rent_year, rent_month)
        _post_monthly_charge_ledger_entries(
            shelter=shelter,
            rent_year=rent_year,
            rent_month=rent_month,
            sheet=sheet,
            entries=entries,
            settings=settings,
        )

        rent_month_label = _month_label(rent_year, rent_month)
        if already_posted:
            flash(f"Rent was already posted for {rent_month_label}. Missing entries were checked.", "ok")
        else:
            flash(f"Rent posted for {rent_month_label}.", "ok")

        return redirect(url_for("rent_tracking.rent_roll"))
