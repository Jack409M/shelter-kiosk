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
    _available_rent_setup_apartment_options,
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


def _normalized_level_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    return digits or text


def _ensure_sheet_for_month(shelter: str, rent_year: int, rent_month: int):
    _ensure_tables()
    settings = _load_settings(shelter)

    sheet = _sheet_for_month(shelter, rent_year, rent_month)
    if not sheet:
        _insert_sheet(shelter, rent_year, rent_month)
        sheet = _sheet_for_month(shelter, rent_year, rent_month)

    for resident in _active_residents_for_shelter(shelter):
        resident_id = resident["id"]
        ph = _placeholder()

        existing = db_fetchone(
            f"SELECT * FROM resident_rent_sheet_entries WHERE sheet_id = {ph} AND resident_id = {ph} LIMIT 1",
            (sheet["id"], resident_id),
        )
        existing = dict(existing) if existing else None

        config = _ensure_default_rent_config(resident_id, shelter)
        config["apartment_number_snapshot"] = _normalize_apartment_number(
            shelter, config.get("apartment_number_snapshot")
        )
        config["apartment_size_snapshot"] = _derive_apartment_size_from_assignment(
            shelter,
            config.get("apartment_number_snapshot"),
        ) or config.get("apartment_size_snapshot")

        enrollment = _program_enrollment_for_month(resident_id, shelter, rent_year, rent_month)
        resolved_enrollment_id = enrollment["id"] if enrollment else None
        entry_enrollment_id = (existing.get("enrollment_id") if existing else None) or resolved_enrollment_id

        carry_forward_enabled = _bool_value(settings.get("rent_carry_forward_enabled", True))
        prior_balance = _latest_prior_balance(
            resident_id, shelter, carry_forward_enabled, rent_year, rent_month
        )
        is_exempt = _bool_value(config.get("is_exempt"))

        base_monthly_rent, base_note = _derive_base_monthly_rent(settings, shelter, config)
        proration = _calculate_proration(
            base_monthly_rent, config, enrollment, rent_year, rent_month
        )

        approved_late_arrangement = _bool_value(
            existing.get("approved_late_arrangement") if existing else False
        )
        manual_adjustment = _float_value(existing.get("manual_adjustment") if existing else 0)
        amount_paid = _float_value(existing.get("amount_paid")) if existing else 0
        paid_date = (existing.get("paid_date") if existing else None) or None
        notes = None

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
            today_date=_today_chicago().date(),
        )
        total_due = 0.0 if is_exempt else round(subtotal_due + late_fee_charge, 2)
        current_charge = (
            0.0 if is_exempt else round(proration["prorated_charge"] + manual_adjustment, 2)
        )
        remaining_balance = 0.0 if is_exempt else round(total_due - amount_paid, 2)
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
                    SET enrollment_id = %s,
                        shelter_snapshot = %s,
                        resident_name_snapshot = %s,
                        level_snapshot = %s,
                        apartment_number_snapshot = %s,
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
                    else """
                    UPDATE resident_rent_sheet_entries
                    SET enrollment_id = ?,
                        shelter_snapshot = ?,
                        resident_name_snapshot = ?,
                        level_snapshot = ?,
                        apartment_number_snapshot = ?,
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
                    entry_enrollment_id,
                    shelter,
                    resident_name,
                    config.get("level_snapshot"),
                    config.get("apartment_number_snapshot"),
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
                        enrollment_id,
                        shelter_snapshot,
                        resident_name_snapshot,
                        level_snapshot,
                        apartment_number_snapshot,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    INSERT INTO resident_rent_sheet_entries (
                        sheet_id,
                        resident_id,
                        enrollment_id,
                        shelter_snapshot,
                        resident_name_snapshot,
                        level_snapshot,
                        apartment_number_snapshot,
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    sheet["id"],
                    resident_id,
                    entry_enrollment_id,
                    shelter,
                    resident_name,
                    config.get("level_snapshot"),
                    config.get("apartment_number_snapshot"),
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


def _entry_sort_key(entry: dict):
    apartment_number = (entry.get("apartment_number_snapshot") or "").strip()
    resident_name = (entry.get("resident_name_snapshot") or "").strip().lower()

    if apartment_number.isdigit():
        return (0, int(apartment_number), resident_name)

    if apartment_number:
        return (1, apartment_number, resident_name)

    return (2, resident_name, "")


def _group_entries_for_payment_page(shelter: str, entries: list[dict]) -> list[dict]:
    shelter_key = (shelter or "").strip().lower()

    if shelter_key not in {"abba", "gratitude"}:
        return [
            {
                "group_label": "Residents",
                "entries": sorted(
                    entries, key=lambda entry: (entry.get("resident_name_snapshot") or "").lower()
                ),
            }
        ]

    apartment_order = _apartment_options_for_shelter(shelter_key)
    grouped_map: dict[str, list[dict]] = {apartment_number: [] for apartment_number in apartment_order}
    unassigned_entries: list[dict] = []

    for entry in entries:
        apartment_number = (entry.get("apartment_number_snapshot") or "").strip()
        if apartment_number in grouped_map:
            grouped_map[apartment_number].append(entry)
        else:
            unassigned_entries.append(entry)

    grouped_sections: list[dict] = []
    for apartment_number in apartment_order:
        apartment_entries = sorted(
            grouped_map.get(apartment_number, []),
            key=lambda entry: (entry.get("resident_name_snapshot") or "").lower(),
        )
        if apartment_entries:
            grouped_sections.append(
                {
                    "group_label": f"Apartment {apartment_number}",
                    "group_key": apartment_number,
                    "entries": apartment_entries,
                }
            )

    if unassigned_entries:
        grouped_sections.append(
            {
                "group_label": "Unassigned",
                "group_key": "unassigned",
                "entries": sorted(
                    unassigned_entries,
                    key=lambda entry: (entry.get("resident_name_snapshot") or "").lower(),
                ),
            }
        )

    return grouped_sections


def _post_monthly_charge_ledger_entries(
    shelter: str,
    rent_year: int,
    rent_month: int,
    sheet: dict,
    entries: list[dict],
    settings: dict,
) -> None:
    charge_date = f"{rent_year:04d}-{rent_month:02d}-01"
    today_date = _today_chicago().date()

    for entry in entries:
        resident_id = entry["resident_id"]
        entry_enrollment_id = entry.get("enrollment_id")
        sheet_entry_id = entry["id"]

        prior_balance = round(_float_value(entry.get("prior_balance")), 2)
        prorated_charge = round(_float_value(entry.get("prorated_charge")), 2)
        manual_adjustment = round(_float_value(entry.get("manual_adjustment")), 2)
        paid_date = (entry.get("paid_date") or "").strip() or None
        approved_late_arrangement = _bool_value(entry.get("approved_late_arrangement"))
        is_exempt = str(entry.get("status") or "").strip() == "Exempt"

        subtotal_due = round(prior_balance + prorated_charge + manual_adjustment, 2)

        late_fee_info = _calculate_late_fee_info(
            settings=settings,
            shelter=shelter,
            rent_year=rent_year,
            rent_month=rent_month,
            subtotal_due=subtotal_due,
            paid_date=paid_date,
            approved_late_arrangement=approved_late_arrangement,
            is_exempt=is_exempt,
            today_date=today_date,
        )

        if prior_balance > 0:
            existing_prior = db_fetchone(
                (
                    """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = %s
                      AND related_sheet_entry_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = ?
                      AND related_sheet_entry_id = ?
                      AND source_code = ?
                    LIMIT 1
                    """
                ),
                (resident_id, sheet_entry_id, "prior_balance_brought_forward"),
            )
            if not existing_prior:
                _insert_rent_ledger_entry(
                    resident_id=resident_id,
                    enrollment_id=entry_enrollment_id,
                    shelter=shelter,
                    entry_date=charge_date,
                    entry_type="charge",
                    description="Prior balance brought forward",
                    debit_amount=prior_balance,
                    credit_amount=0.0,
                    related_sheet_id=sheet["id"],
                    related_sheet_entry_id=sheet_entry_id,
                    related_month_year=rent_year,
                    related_month_month=rent_month,
                    source_code="prior_balance_brought_forward",
                    source_reference=f"{rent_year:04d}-{rent_month:02d}",
                    notes=None,
                )

        if prorated_charge > 0:
            existing_charge = db_fetchone(
                (
                    """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = %s
                      AND related_sheet_entry_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = ?
                      AND related_sheet_entry_id = ?
                      AND source_code = ?
                    LIMIT 1
                    """
                ),
                (resident_id, sheet_entry_id, "monthly_rent_charge"),
            )
            if not existing_charge:
                _insert_rent_ledger_entry(
                    resident_id=resident_id,
                    enrollment_id=entry_enrollment_id,
                    shelter=shelter,
                    entry_date=charge_date,
                    entry_type="charge",
                    description="Monthly rent charge",
                    debit_amount=prorated_charge,
                    credit_amount=0.0,
                    related_sheet_id=sheet["id"],
                    related_sheet_entry_id=sheet_entry_id,
                    related_month_year=rent_year,
                    related_month_month=rent_month,
                    source_code="monthly_rent_charge",
                    source_reference=f"{rent_year:04d}-{rent_month:02d}",
                    notes=entry.get("calculation_notes"),
                )

        if manual_adjustment > 0:
            existing_adjustment_charge = db_fetchone(
                (
                    """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = %s
                      AND related_sheet_entry_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = ?
                      AND related_sheet_entry_id = ?
                      AND source_code = ?
                    LIMIT 1
                    """
                ),
                (resident_id, sheet_entry_id, "manual_adjustment_charge"),
            )
            if not existing_adjustment_charge:
                _insert_rent_ledger_entry(
                    resident_id=resident_id,
                    enrollment_id=entry_enrollment_id,
                    shelter=shelter,
                    entry_date=charge_date,
                    entry_type="adjustment",
                    description="Manual rent adjustment charge",
                    debit_amount=manual_adjustment,
                    credit_amount=0.0,
                    related_sheet_id=sheet["id"],
                    related_sheet_entry_id=sheet_entry_id,
                    related_month_year=rent_year,
                    related_month_month=rent_month,
                    source_code="manual_adjustment_charge",
                    source_reference=f"{rent_year:04d}-{rent_month:02d}",
                    notes=None,
                )
        elif manual_adjustment < 0:
            existing_adjustment_credit = db_fetchone(
                (
                    """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = %s
                      AND related_sheet_entry_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = ?
                      AND related_sheet_entry_id = ?
                      AND source_code = ?
                    LIMIT 1
                    """
                ),
                (resident_id, sheet_entry_id, "manual_adjustment_credit"),
            )
            if not existing_adjustment_credit:
                _insert_rent_ledger_entry(
                    resident_id=resident_id,
                    enrollment_id=entry_enrollment_id,
                    shelter=shelter,
                    entry_date=charge_date,
                    entry_type="credit",
                    description="Manual rent adjustment credit",
                    debit_amount=0.0,
                    credit_amount=abs(manual_adjustment),
                    related_sheet_id=sheet["id"],
                    related_sheet_entry_id=sheet_entry_id,
                    related_month_year=rent_year,
                    related_month_month=rent_month,
                    source_code="manual_adjustment_credit",
                    source_reference=f"{rent_year:04d}-{rent_month:02d}",
                    notes=None,
                )

        if late_fee_info["is_postable"] and late_fee_info["amount"] > 0 and late_fee_info["posting_date"]:
            existing_late_fee = db_fetchone(
                (
                    """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = %s
                      AND related_sheet_entry_id = %s
                      AND source_code = %s
                    LIMIT 1
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    SELECT id
                    FROM resident_rent_ledger_entries
                    WHERE resident_id = ?
                      AND related_sheet_entry_id = ?
                      AND source_code = ?
                    LIMIT 1
                    """
                ),
                (resident_id, sheet_entry_id, "late_fee_charge"),
            )
            if not existing_late_fee:
                _insert_rent_ledger_entry(
                    resident_id=resident_id,
                    enrollment_id=entry_enrollment_id,
                    shelter=shelter,
                    entry_date=late_fee_info["posting_date"],
                    entry_type="late_fee",
                    description="Late fee posted",
                    debit_amount=late_fee_info["amount"],
                    credit_amount=0.0,
                    related_sheet_id=sheet["id"],
                    related_sheet_entry_id=sheet_entry_id,
                    related_month_year=rent_year,
                    related_month_month=rent_month,
                    source_code="late_fee_charge",
                    source_reference=f"{rent_year:04d}-{rent_month:02d}",
                    notes=late_fee_info["note"],
                )


def _ledger_payment_total_for_sheet_entry(resident_id: int, sheet_entry_id: int) -> float:
    row = db_fetchone(
        (
            """
            SELECT COALESCE(SUM(credit_amount), 0) AS total_paid
            FROM resident_rent_ledger_entries
            WHERE resident_id = %s
              AND related_sheet_entry_id = %s
              AND source_code IN (%s, %s)
            """
            if g.get("db_kind") == "pg"
            else """
            SELECT COALESCE(SUM(credit_amount), 0) AS total_paid
            FROM resident_rent_ledger_entries
            WHERE resident_id = ?
              AND related_sheet_entry_id = ?
              AND source_code IN (?, ?)
            """
        ),
        (resident_id, sheet_entry_id, "rent_payment", "rent_payment_reconcile"),
    )
    return round(_float_value(row.get("total_paid") if row else 0), 2)


def _reconcile_payment_ledger_entry(*, resident_id: int, shelter: str, sheet: dict, entry: dict, rent_year: int, rent_month: int) -> None:
    sheet_entry_id = entry["id"]
    entry_enrollment_id = entry.get("enrollment_id")
    amount_paid_total = round(_float_value(entry.get("amount_paid")), 2)
    already_posted = _ledger_payment_total_for_sheet_entry(resident_id, sheet_entry_id)
    missing_payment = round(amount_paid_total - already_posted, 2)

    if missing_payment <= 0:
        return

    payment_entry_date = (entry.get("paid_date") or "").strip() or _today_chicago().date().isoformat()
    stamp = utcnow_iso()

    _insert_rent_ledger_entry(
        resident_id=resident_id,
        enrollment_id=entry_enrollment_id,
        shelter=shelter,
        entry_date=payment_entry_date,
        entry_type="payment",
        description="Rent payment received",
        debit_amount=0.0,
        credit_amount=missing_payment,
        related_sheet_id=sheet["id"],
        related_sheet_entry_id=sheet_entry_id,
        related_month_year=rent_year,
        related_month_month=rent_month,
        source_code="rent_payment_reconcile",
        source_reference=f"{rent_year:04d}-{rent_month:02d}:{sheet_entry_id}:{stamp}",
        notes=None,
    )


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
            flash("Payments are now locked to Resident Account.", "error")
            return redirect(url_for("rent_tracking.payment_entry_sheet", year=rent_year, month=rent_month))

        repaired_entries = _load_sheet_entries(sheet["id"])
        with db_transaction():
            for entry in repaired_entries:
                if round(_float_value(entry.get("amount_paid")), 2) > 0:
                    _reconcile_payment_ledger_entry(
                        resident_id=entry["resident_id"],
                        shelter=shelter,
                        sheet=sheet,
                        entry=entry,
                        rent_year=rent_year,
                        rent_month=rent_month,
                    )

        sorted_entries = sorted(_load_sheet_entries(sheet["id"]), key=_entry_sort_key)
        grouped_entry_sections = _group_entries_for_payment_page(shelter, sorted_entries)

        return render_template(
            "case_management/rent_entry.html",
            shelter=shelter,
            sheet=sheet,
            entries=sorted_entries,
            grouped_entry_sections=grouped_entry_sections,
            month_label=_month_label(rent_year, rent_month),
        )

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

        return render_template(
            "case_management/resident_rent_ledger.html",
            resident=resident,
            ledger_entries=ledger_entries,
            ledger_summary=ledger_summary,
            balance_breakdown=balance_breakdown,
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
        amount = round(_float_value(request.form.get("amount")), 2)
        payment_date = (request.form.get("payment_date") or "").strip() or _today_chicago().date().isoformat()
        payment_method = (request.form.get("payment_method") or "").strip()
        instrument_number = (request.form.get("instrument_number") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

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
        amount = round(_float_value(request.form.get("amount")), 2)
        charge_date = (request.form.get("charge_date") or "").strip() or _today_chicago().date().isoformat()
        charge_category = (request.form.get("charge_category") or "").strip()
        charge_reference = (request.form.get("charge_reference") or "").strip() or None
        description = (request.form.get("description") or "").strip()
        notes = (request.form.get("notes") or "").strip() or None

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

        resident_level = _normalized_level_text(resident.get("program_level"))
        if resident_level == "9":
            flash("Level 9 residents cannot be assigned to DWC housing.", "error")
            return redirect(url_for("rent_tracking.rent_roll"))

        config = _ensure_default_rent_config(resident_id, shelter)
        config["apartment_number_snapshot"] = _normalize_apartment_number(shelter, config.get("apartment_number_snapshot"))
        config["apartment_size_snapshot"] = _derive_apartment_size_from_assignment(shelter, config.get("apartment_number_snapshot")) or config.get("apartment_size_snapshot")

        auto_monthly_rent, auto_rent_note = _derive_base_monthly_rent(settings, shelter, config)

        ph = _placeholder()
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

        apartment_options = _available_rent_setup_apartment_options(shelter, resident_id)

        if request.method == "POST":
            level_snapshot = _normalized_level_text(resident.get("program_level"))
            apartment_number_snapshot = _normalize_apartment_number(shelter, request.form.get("apartment_number_snapshot"))
            apartment_size_snapshot = _derive_apartment_size_from_assignment(shelter, apartment_number_snapshot)
            monthly_rent = _float_value(request.form.get("monthly_rent"))
            is_exempt = (request.form.get("is_exempt") or "no").strip().lower() == "yes"
            from .dates import _today_chicago as _today_local

            effective_start_date = (request.form.get("effective_start_date") or _today_local().date().isoformat()).strip()
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
                    else """
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
                        apartment_number_snapshot,
                        apartment_size_snapshot,
                        monthly_rent,
                        is_exempt,
                        effective_start_date,
                        effective_end_date,
                        created_by_staff_user_id,
                        created_at,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """
                    if g.get("db_kind") == "pg"
                    else """
                    INSERT INTO resident_rent_configs (
                        resident_id,
                        shelter,
                        level_snapshot,
                        apartment_number_snapshot,
                        apartment_size_snapshot,
                        monthly_rent,
                        is_exempt,
                        effective_start_date,
                        effective_end_date,
                        created_by_staff_user_id,
                        created_at,
                        updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    resident_id,
                    shelter,
                    level_snapshot,
                    apartment_number_snapshot,
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
            shelter=shelter,
            current_config=config,
            history=history,
            auto_monthly_rent=auto_monthly_rent,
            auto_rent_note=auto_rent_note,
            apartment_options=apartment_options,
            derived_apartment_size=config.get("apartment_size_snapshot"),
        )

    @rent_tracking.get("/resident/<int:resident_id>/history")
    @require_login
    @require_shelter
    def resident_rent_history(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _resident_any_shelter(resident_id)
        if not resident:
            flash("Resident not found.", "error")
            return redirect(url_for("case_management.index"))

        rows = _history_rows_for_resident(resident_id)
        rent_snapshot = build_rent_stability_snapshot(resident_id)

        return render_template("case_management/resident_rent_history.html", resident=resident, rows=rows, rent_snapshot=rent_snapshot)

    @rent_tracking.get("/resident/<int:resident_id>/ledger")
    @require_login
    @require_shelter
    def resident_rent_ledger(resident_id: int):
        if not _allowed(session):
            flash("Case manager, shelter director, or admin access required.", "error")
            return redirect(url_for("attendance.staff_attendance"))

        _ensure_tables()
        resident = _resident_any_shelter(resident_id)
        if not resident:
            flash("Resident not found.", "error")
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
            payment_method_options=["Check", "Money Order"],
            charge_category_options=["cleaning_fee", "lost_key", "maintenance", "other"],
            credit_category_options=["refund", "proration_credit", "other_credit"],
        )
