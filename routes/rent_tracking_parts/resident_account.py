from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter

from .access import _allowed, _normalize_shelter_name
from .data_access import (
    _ledger_balance_breakdown_for_resident,
    _ledger_entries_for_resident,
    _ledger_summary_for_resident,
    _load_sheet_entries,
    _post_resident_charge,
    _post_resident_credit,
    _post_resident_payment,
    _resident_any_shelter,
)
from .dates import _current_year_month, _today_chicago
from .schema import _ensure_tables
from .snapshot import build_rent_stability_snapshot
from .utils import _float_value
from .views import _ensure_sheet_for_month, _post_monthly_charge_ledger_entries


PAYMENT_METHOD_OPTIONS = ["Check", "Money Order"]
CHARGE_CATEGORY_OPTIONS = ["cleaning_fee", "lost_key", "maintenance", "other"]
CREDIT_CATEGORY_OPTIONS = ["refund", "proration_credit", "other_credit"]


def _load_resident_or_redirect(resident_id: int):
    resident = _resident_any_shelter(resident_id)
    if not resident:
        flash("Resident not found.", "error")
        return None
    return resident


def _ensure_current_month_charges_for_resident(resident: dict) -> None:
    shelter = _normalize_shelter_name(resident.get("shelter"))
    if not shelter:
        return

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


def register_resident_account_routes(rent_tracking):
    @rent_tracking.route("/resident/<int:resident_id>/account", methods=["GET"])
    @require_login
    @require_shelter
    def resident_rent_account(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _load_resident_or_redirect(resident_id)
        if not resident:
            return redirect(url_for("rent_tracking.rent_roll"))

        ledger_entries = _ledger_entries_for_resident(resident_id)
        ledger_summary = _ledger_summary_for_resident(resident_id)
        balance_breakdown = _ledger_balance_breakdown_for_resident(resident_id)

        return render_template(
            "case_management/resident_rent_ledger.html",
            resident=resident,
            ledger_entries=ledger_entries,
            ledger_summary=ledger_summary,
            balance_breakdown=balance_breakdown,
            show_payment_form=True,
            payment_method_options=PAYMENT_METHOD_OPTIONS,
            charge_category_options=CHARGE_CATEGORY_OPTIONS,
            credit_category_options=CREDIT_CATEGORY_OPTIONS,
        )

    @rent_tracking.route("/resident/<int:resident_id>/account/post-payment", methods=["POST"])
    @require_login
    @require_shelter
    def resident_rent_post_payment(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _load_resident_or_redirect(resident_id)
        if not resident:
            return redirect(url_for("rent_tracking.rent_roll"))

        shelter = _normalize_shelter_name(resident.get("shelter"))
        amount = round(_float_value(request.form.get("amount")), 2)
        payment_date = (request.form.get("payment_date") or "").strip() or _today_chicago().date().isoformat()
        payment_method = (request.form.get("payment_method") or "").strip()
        instrument_number = (request.form.get("instrument_number") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if amount <= 0:
            flash("Payment amount must be greater than zero.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if payment_method not in set(PAYMENT_METHOD_OPTIONS):
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
        resident = _load_resident_or_redirect(resident_id)
        if not resident:
            return redirect(url_for("rent_tracking.rent_roll"))

        shelter = _normalize_shelter_name(resident.get("shelter"))
        amount = round(_float_value(request.form.get("amount")), 2)
        charge_date = (request.form.get("charge_date") or "").strip() or _today_chicago().date().isoformat()
        charge_category = (request.form.get("charge_category") or "").strip()
        charge_reference = (request.form.get("charge_reference") or "").strip() or None
        description = (request.form.get("description") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if amount <= 0:
            flash("Charge amount must be greater than zero.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if charge_category not in set(CHARGE_CATEGORY_OPTIONS):
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
        resident = _load_resident_or_redirect(resident_id)
        if not resident:
            return redirect(url_for("rent_tracking.rent_roll"))

        ledger_summary = _ledger_summary_for_resident(resident_id)
        shelter = _normalize_shelter_name(resident.get("shelter"))
        amount = round(_float_value(request.form.get("amount")), 2)
        credit_date = (request.form.get("credit_date") or "").strip() or _today_chicago().date().isoformat()
        credit_category = (request.form.get("credit_category") or "").strip()
        description = (request.form.get("description") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

        if amount <= 0:
            flash("Credit amount must be greater than zero.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if credit_category not in set(CREDIT_CATEGORY_OPTIONS):
            flash("Select a valid credit category.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if not description:
            flash("Credit description is required.", "error")
            return redirect(url_for("rent_tracking.resident_rent_account", resident_id=resident_id))

        if credit_category == "refund" and (ledger_summary.get("current_balance") or 0) >= 0:
            flash("Refund can only be posted when the account is actually in credit.", "error")
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

    @rent_tracking.get("/resident/<int:resident_id>/ledger")
    @require_login
    @require_shelter
    def resident_rent_ledger(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _load_resident_or_redirect(resident_id)
        if not resident:
            return redirect(url_for("case_management.index"))

        ledger_entries = _ledger_entries_for_resident(resident_id)
        ledger_summary = _ledger_summary_for_resident(resident_id)
        balance_breakdown = _ledger_balance_breakdown_for_resident(resident_id)

        return render_template(
            "case_management/resident_rent_ledger.html",
            resident=resident,
            ledger_entries=ledger_entries,
            ledger_summary=ledger_summary,
            balance_breakdown=balance_breakdown,
            show_payment_form=False,
            payment_method_options=PAYMENT_METHOD_OPTIONS,
            charge_category_options=CHARGE_CATEGORY_OPTIONS,
            credit_category_options=CREDIT_CATEGORY_OPTIONS,
        )

    @rent_tracking.get("/resident/<int:resident_id>/history")
    @require_login
    @require_shelter
    def resident_rent_history(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _load_resident_or_redirect(resident_id)
        if not resident:
            return redirect(url_for("case_management.index"))

        rows = []
        from .data_access import _history_rows_for_resident

        rows = _history_rows_for_resident(resident_id)
        rent_snapshot = build_rent_stability_snapshot(resident_id)

        return render_template(
            "case_management/resident_rent_history.html",
            resident=resident,
            rows=rows,
            rent_snapshot=rent_snapshot,
        )
