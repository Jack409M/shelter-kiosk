from __future__ import annotations

from flask import flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter

from .access import _allowed, _normalize_shelter_name
from .data_access import (
    _active_residents_for_shelter,
    _ledger_summary_for_resident,
    _post_resident_payment,
    _resident_for_shelter,
)
from .dates import _today_chicago
from .utils import _float_value

PAYMENT_METHOD_OPTIONS = ("Check", "Money Order")


def _resident_sort_key(resident: dict):
    apartment = str(resident.get("apartment_number_snapshot") or "").strip()
    last_name = str(resident.get("last_name") or "").strip().lower()
    first_name = str(resident.get("first_name") or "").strip().lower()

    if apartment.isdigit():
        return (0, int(apartment), last_name, first_name)
    if apartment:
        return (1, apartment, last_name, first_name)
    return (2, last_name, first_name)


def _resident_display_name(resident: dict) -> str:
    return f"{resident.get('first_name', '')} {resident.get('last_name', '')}".strip()


def register_payment_station_routes(rent_tracking):
    @rent_tracking.route("/payment-station", methods=["GET", "POST"])
    @require_login
    @require_shelter
    def payment_station():
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        shelter = _normalize_shelter_name(session.get("shelter"))
        residents = sorted(_active_residents_for_shelter(shelter), key=_resident_sort_key)

        selected_resident_id_raw = request.form.get("resident_id") or request.args.get("resident_id")
        selected_resident_id = None
        selected_resident = None
        ledger_summary = None

        if selected_resident_id_raw:
            try:
                selected_resident_id = int(selected_resident_id_raw)
            except (TypeError, ValueError):
                selected_resident_id = None

        if selected_resident_id:
            selected_resident = _resident_for_shelter(selected_resident_id, shelter)
            if not selected_resident:
                flash("Resident not found for this shelter.", "error")
                return redirect(url_for("rent_tracking.payment_station"))

            ledger_summary = _ledger_summary_for_resident(selected_resident_id)

        if request.method == "POST":
            if not selected_resident:
                flash("Choose a resident before posting a payment.", "error")
                return redirect(url_for("rent_tracking.payment_station"))

            amount = round(_float_value(request.form.get("amount")), 2)
            payment_method = (request.form.get("payment_method") or "").strip()
            instrument_number = (request.form.get("instrument_number") or "").strip()
            notes = (request.form.get("notes") or "").strip() or None
            payment_date = (request.form.get("payment_date") or "").strip() or _today_chicago().date().isoformat()

            if amount <= 0:
                flash("Payment amount must be greater than zero.", "error")
                return redirect(url_for("rent_tracking.payment_station", resident_id=selected_resident_id))

            if payment_method not in PAYMENT_METHOD_OPTIONS:
                flash("Choose Check or Money Order as the payment method.", "error")
                return redirect(url_for("rent_tracking.payment_station", resident_id=selected_resident_id))

            _post_resident_payment(
                resident_id=selected_resident_id,
                shelter=shelter,
                amount=amount,
                payment_date=payment_date,
                payment_method=payment_method,
                instrument_number=instrument_number,
                notes=notes,
            )

            flash(f"Payment posted for {_resident_display_name(selected_resident)}.", "ok")
            return redirect(url_for("rent_tracking.payment_station"))

        return render_template(
            "case_management/payment_station.html",
            shelter=shelter,
            residents=residents,
            selected_resident=selected_resident,
            ledger_summary=ledger_summary,
            payment_method_options=PAYMENT_METHOD_OPTIONS,
            today=_today_chicago().date().isoformat(),
        )
