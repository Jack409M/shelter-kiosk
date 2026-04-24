from __future__ import annotations

from flask import Blueprint, render_template, request, redirect, url_for, session

from core.auth import require_login, require_shelter

payment_station_bp = Blueprint(
    "payment_station",
    __name__,
    url_prefix="/staff/rent",
)


@payment_station_bp.route("/payment-station", methods=["GET", "POST"])
@require_login
@require_shelter
def payment_station():
    shelter = (session.get("shelter") or "").strip().lower()

    from routes.rent_tracking_parts.data_access import (
        _active_residents_for_shelter,
        _resident_for_shelter,
        _ledger_summary_for_resident,
        _post_resident_payment,
    )
    from routes.rent_tracking_parts.utils import _float_value
    from routes.rent_tracking_parts.dates import _today_chicago

    residents = _active_residents_for_shelter(shelter)

    selected_resident_id = request.args.get("resident_id") or request.form.get("resident_id")
    selected_resident = None
    ledger_summary = None

    if selected_resident_id:
        selected_resident_id = int(selected_resident_id)

        selected_resident = _resident_for_shelter(selected_resident_id, shelter)
        ledger_summary = _ledger_summary_for_resident(selected_resident_id)

        if request.method == "POST":
            amount = _float_value(request.form.get("amount"))
            payment_method = (request.form.get("payment_method") or "").strip()
            instrument_number = (request.form.get("instrument_number") or "").strip()
            notes = (request.form.get("notes") or "").strip()

            payment_date = _today_chicago().date().isoformat()

            if amount > 0:
                _post_resident_payment(
                    resident_id=selected_resident_id,
                    shelter=shelter,
                    amount=amount,
                    payment_date=payment_date,
                    payment_method=payment_method,
                    instrument_number=instrument_number,
                    notes=notes,
                )

            return redirect(
                url_for("payment_station.payment_station", resident_id=selected_resident_id)
            )

    return render_template(
        "case_management/payment_station.html",
        residents=residents,
        selected_resident=selected_resident,
        ledger_summary=ledger_summary,
    )
