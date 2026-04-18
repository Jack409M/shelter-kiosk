from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

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
    _ledger_balance_breakdown_for_resident,
    _ledger_entries_for_resident,
    _ledger_summary_for_resident,
    _load_sheet_entries,
    _post_resident_charge,
    _post_resident_credit,
    _post_resident_payment,
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


def _is_moved_out(resident: dict) -> bool:
    # Minimal, reliable signal using existing fields
    if not resident:
        return False
    if resident.get("is_active") is False:
        return True
    # If no shelter attached, treat as not currently housed here
    if not _normalize_shelter_name(resident.get("shelter")):
        return True
    return False


def _final_mode_flags(resident: dict, ledger_summary: dict) -> dict:
    moved_out = _is_moved_out(resident)
    bal = round(_float_value((ledger_summary or {}).get("current_balance")), 2)

    if not moved_out:
        return {
            "moved_out": False,
            "allow_charges": True,
            "allow_payments": True,
            "allow_credits": True,
            "status_label": None,
        }

    # Final mode
    if bal > 0:
        return {
            "moved_out": True,
            "allow_charges": False,
            "allow_payments": True,
            "allow_credits": False,
            "status_label": f"Final amount owed: ${bal:.2f}",
        }
    if bal < 0:
        return {
            "moved_out": True,
            "allow_charges": False,
            "allow_payments": False,
            "allow_credits": True,
            "status_label": f"Refund due: -${abs(bal):.2f}",
        }
    return {
        "moved_out": True,
        "allow_charges": False,
        "allow_payments": False,
        "allow_credits": False,
        "status_label": "Final balance settled",
    }


# ... keep existing code unchanged above routes ...


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
            apartment_number_snapshot = _normalize_apartment_number(shelter, config.get("apartment_number_snapshot"))
            apartment_size_snapshot = _derive_apartment_size_from_assignment(shelter, apartment_number_snapshot) or config.get("apartment_size_snapshot")
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

    @rent_tracking.route("/resident/<int:resident_id>/account", methods=["GET"])
    @require_login
    @require_shelter
    def resident_rent_account(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _resident_any_shelter(resident_id)
        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("rent_tracking.rent_roll"))

        shelter = _normalize_shelter_name(resident.get("shelter"))
        if shelter:
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

        ledger_entries = _ledger_entries_for_resident(resident_id)
        ledger_summary = _ledger_summary_for_resident(resident_id)
        balance_breakdown = _ledger_balance_breakdown_for_resident(resident_id)
        final_flags = _final_mode_flags(resident, ledger_summary)

        return render_template(
            "case_management/resident_rent_ledger.html",
            resident=resident,
            ledger_entries=ledger_entries,
            ledger_summary=ledger_summary,
            balance_breakdown=balance_breakdown,
            final_flags=final_flags,
            show_payment_form=True,
            payment_method_options=["Check", "Money Order"],
            charge_category_options=["cleaning_fee", "lost_key", "maintenance", "other"],
            credit_category_options=["refund", "proration_credit", "other_credit"],
        )

    @rent_tracking.route("/resident/<int:resident_id>/account/post-payment", methods=["POST"])
    @require_login
    @require_shelter
    def resident_rent_post_payment(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _resident_any_shelter(resident_id)
        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("rent_tracking.rent_roll"))

        shelter = _normalize_shelter_name(resident.get("shelter"))
        ledger_summary = _ledger_summary_for_resident(resident_id)
        flags = _final_mode_flags(resident, ledger_summary)

        amount = round(_float_value(request.form.get("amount")), 2)
        payment_date = (request.form.get("payment_date") or "").strip() or _today_chicago().date().isoformat()
        payment_method = (request.form.get("payment_method") or "").strip()
        instrument_number = (request.form.get("instrument_number") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if flags.get("moved_out") and not flags.get("allow_payments"):
            flash("No payment needed on this closed account.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if amount <= 0:
            flash("Payment amount must be greater than zero.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if payment_method not in {"Check", "Money Order"}:
            flash("Payment method must be Check or Money Order.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if not instrument_number:
            flash("Check or Money Order number is required.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        _post_resident_payment(
            resident_id=resident_id,
            shelter=shelter,
            amount=amount,
            payment_date=payment_date,
            payment_method=payment_method,
            instrument_number=instrument_number,
            notes=notes,
        )

        flash("Payment posted.", "ok")
        return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

    @rent_tracking.route("/resident/<int:resident_id>/account/post-charge", methods=["POST"])
    @require_login
    @require_shelter
    def resident_rent_post_charge(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _resident_any_shelter(resident_id)
        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("rent_tracking.rent_roll"))

        shelter = _normalize_shelter_name(resident.get("shelter"))
        ledger_summary = _ledger_summary_for_resident(resident_id)
        flags = _final_mode_flags(resident, ledger_summary)

        amount = round(_float_value(request.form.get("amount")), 2)
        charge_date = (request.form.get("charge_date") or "").strip() or _today_chicago().date().isoformat()
        charge_category = (request.form.get("charge_category") or "").strip()
        charge_reference = (request.form.get("charge_reference") or "").strip() or None
        description = (request.form.get("description") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if flags.get("moved_out"):
            flash("Do not add charges after move out. Resolve with payment or refund.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if amount <= 0:
            flash("Charge amount must be greater than zero.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if charge_category not in {"cleaning_fee", "lost_key", "maintenance", "other"}:
            flash("Select a valid charge category.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if not description:
            flash("Charge description is required.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        _post_resident_charge(
            resident_id=resident_id,
            shelter=shelter,
            amount=amount,
            charge_date=charge_date,
            charge_category=charge_category,
            description=description,
            charge_reference=charge_reference,
            notes=notes,
        )

        flash("Charge posted.", "ok")
        return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

    @rent_tracking.route("/resident/<int:resident_id>/account/post-credit", methods=["POST"])
    @require_login
    @require_shelter
    def resident_rent_post_credit(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _resident_any_shelter(resident_id)
        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("rent_tracking.rent_roll"))

        ledger_summary = _ledger_summary_for_resident(resident_id)
        flags = _final_mode_flags(resident, ledger_summary)
        shelter = _normalize_shelter_name(resident.get("shelter"))

        amount = round(_float_value(request.form.get("amount")), 2)
        credit_date = (request.form.get("credit_date") or "").strip() or _today_chicago().date().isoformat()
        credit_category = (request.form.get("credit_category") or "").strip()
        description = (request.form.get("description") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if amount <= 0:
            flash("Credit amount must be greater than zero.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if credit_category not in {"refund", "proration_credit", "other_credit"}:
            flash("Select a valid credit category.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if not description:
            flash("Credit description is required.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if credit_category == "refund" and (ledger_summary.get("current_balance") or 0) >= 0:
            flash("Refund can only be posted when the account is actually in credit.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if flags.get("moved_out") and credit_category == "refund" and not flags.get("allow_credits"):
            flash("No refund due on this account.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        _post_resident_credit(
            resident_id=resident_id,
            shelter=shelter,
            amount=amount,
            credit_date=credit_date,
            credit_category=credit_category,
            description=description,
            notes=notes,
        )

        flash("Credit posted.", "ok")
        return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

    # ... rest unchanged ...
