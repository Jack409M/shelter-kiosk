from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import utcnow_iso

from .access import _allowed, _normalize_shelter_name
from .calculations import (
    _apartment_options_for_shelter,
    _calculate_late_fee,
    _calculate_late_fee_info,
    _calculate_proration,
    _derive_apartment_size_from_assignment,
    _derive_base_monthly_rent,
    _derive_status,
    _normalize_apartment_number,
    _score_for_status,
)
from .data_access import (
    _active_residents_for_shelter,
    _ensure_default_rent_config,
    _history_rows_for_resident,
    _insert_rent_ledger_entry,
    _insert_sheet,
    _latest_prior_balance,
    _ledger_entries_for_resident,
    _ledger_summary_for_resident,
    _load_sheet_entries,
    _program_enrollment_for_month,
    _resident_any_shelter,
    _resident_for_shelter,
    _sheet_for_month,
)
from .dates import _current_year_month, _month_label, _today_chicago
from .schema import _ensure_tables
from .settings import _load_settings
from .snapshot import build_rent_stability_snapshot
from .utils import _bool_value, _float_value, _placeholder


def _audit_staff_user_id() -> int | None:
    raw_staff_user_id = session.get("staff_user_id")
    if raw_staff_user_id in (None, ""):
        return None
    try:
        return int(raw_staff_user_id)
    except Exception:
        return None


# (rest of file unchanged until POST handlers)


def register_routes(rent_tracking):
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
                shelter, config.get("apartment_number_snapshot")
            )
            apartment_size_snapshot = _derive_apartment_size_from_assignment(
                shelter, apartment_number_snapshot
            ) or config.get("apartment_size_snapshot")
            config["apartment_number_snapshot"] = apartment_number_snapshot
            config["apartment_size_snapshot"] = apartment_size_snapshot

            auto_rent, auto_note = _derive_base_monthly_rent(settings, shelter, config)
            manual_override = _float_value(config.get("monthly_rent"))
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
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        shelter = _normalize_shelter_name(session.get("shelter"))
        rent_year = request.args.get("year", type=int)
        rent_month = request.args.get("month", type=int)
        if not rent_year or not rent_month:
            rent_year, rent_month = _current_year_month()

        sheet, settings = _ensure_sheet_for_month(shelter, rent_year, rent_month)
        entries = _load_sheet_entries(sheet["id"])

        _post_monthly_charge_ledger_entries(
            shelter=shelter,
            rent_year=rent_year,
            rent_month=rent_month,
            sheet=sheet,
            entries=entries,
            settings=settings,
        )

        if request.method == "POST":
            total_payment_received = 0.0
            updated_rows = 0

            today_iso = _today_chicago().date().isoformat()

            with db_transaction():
                fresh_entries = _load_sheet_entries(sheet["id"])

                for entry in fresh_entries:
                    entry_id = entry["id"]
                    resident_id = entry["resident_id"]
                    entry_enrollment_id = entry.get("enrollment_id")

                    payment_received = round(
                        max(0.0, _float_value(request.form.get(f"payment_received_{entry_id}"))),
                        2,
                    )
                    if payment_received > 0:
                        total_payment_received += payment_received

                    existing_amount_paid = round(_float_value(entry.get("amount_paid")), 2)
                    amount_paid = round(existing_amount_paid + payment_received, 2)

                    # (rest unchanged update logic)

                    updated_rows += 1

                    if payment_received > 0:
                        log_action(
                            "rent_payment",
                            resident_id,
                            shelter,
                            _audit_staff_user_id(),
                            "payment_received",
                            {
                                "amount": payment_received,
                                "sheet_id": sheet["id"],
                                "entry_id": entry_id,
                            },
                        )

            log_action(
                "rent_sheet",
                sheet["id"],
                shelter,
                _audit_staff_user_id(),
                "payment_sheet_update",
                {
                    "updated_rows": updated_rows,
                    "total_payment_received": total_payment_received,
                    "month": f"{rent_year}-{rent_month}",
                },
            )

            flash("Rent payment sheet saved.", "ok")
            return redirect(
                url_for("rent_tracking.payment_entry_sheet", year=rent_year, month=rent_month)
            )

        # rest unchanged

    @rent_tracking.route("/resident/<int:resident_id>/config", methods=["GET", "POST"])
    @require_login
    @require_shelter
    def resident_rent_config(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        shelter = _normalize_shelter_name(session.get("shelter"))
        settings = _load_settings(shelter)

        resident = _resident_for_shelter(resident_id, shelter)
        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("rent_tracking.rent_roll"))

        if request.method == "POST":
            # existing logic

            log_action(
                "rent_config",
                resident_id,
                shelter,
                _audit_staff_user_id(),
                "update",
                {
                    "monthly_rent": monthly_rent,
                    "is_exempt": is_exempt,
                    "apartment": apartment_number_snapshot,
                },
            )

            flash("Resident rent setup updated.", "ok")
            return redirect(url_for("rent_tracking.resident_rent_config", resident_id=resident_id))

        # rest unchanged
