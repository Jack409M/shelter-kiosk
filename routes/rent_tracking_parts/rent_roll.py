from __future__ import annotations

from flask import flash, redirect, render_template, session, url_for

from core.auth import require_login, require_shelter

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
)
from .schema import _ensure_tables
from .settings import _load_settings
from .utils import _bool_value, _float_value


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

        return render_template("case_management/rent_roll.html", shelter=shelter, rows=rows)
