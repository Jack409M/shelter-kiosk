from __future__ import annotations

from flask import flash, g, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

from .access import _allowed, _normalize_shelter_name
from .calculations import (
    _apartment_options_for_shelter,
    _calculate_late_fee,
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
    _load_sheet_entries,
    _latest_prior_balance,
    _program_enrollment_for_month,
    _resident_any_shelter,
    _resident_for_shelter,
    _sheet_for_month,
    _insert_sheet,
)
from .dates import _current_year_month, _month_label, _today_chicago
from .schema import _ensure_tables
from .settings import _load_settings
from .snapshot import build_rent_stability_snapshot
from .utils import _bool_value, _float_value, _placeholder


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
        config["apartment_number_snapshot"] = _normalize_apartment_number(shelter, config.get("apartment_number_snapshot"))
        config["apartment_size_snapshot"] = _derive_apartment_size_from_assignment(
            shelter,
            config.get("apartment_number_snapshot"),
        ) or config.get("apartment_size_snapshot")

        enrollment = _program_enrollment_for_month(resident_id, shelter, rent_year, rent_month)

        carry_forward_enabled = _bool_value(settings.get("rent_carry_forward_enabled", True))
        prior_balance = _latest_prior_balance(resident_id, shelter, carry_forward_enabled, rent_year, rent_month)
        is_exempt = _bool_value(config.get("is_exempt"))

        base_monthly_rent, base_note = _derive_base_monthly_rent(settings, shelter, config)
        proration = _calculate_proration(base_monthly_rent, config, enrollment, rent_year, rent_month)

        approved_late_arrangement = _bool_value(existing.get("approved_late_arrangement") if existing else False)
        manual_adjustment = _float_value(existing.get("manual_adjustment") if existing else 0)
        amount_paid = _float_value(existing.get("amount_paid") if existing else 0)
        paid_date = (existing.get("paid_date") if existing else None) or None
        notes = (existing.get("notes") if existing else None) or None

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
        current_charge = 0.0 if is_exempt else round(proration["prorated_charge"] + manual_adjustment, 2)
        remaining_balance = 0.0 if is_exempt else round(max(total_due - amount_paid, 0.0), 2)
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
                    SET shelter_snapshot = %s,
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
                    else
                    """
                    UPDATE resident_rent_sheet_entries
                    SET shelter_snapshot = ?,
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
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """
                ),
                (
                    sheet["id"],
                    resident_id,
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

        if request.method == "POST":
            for entry in entries:
                entry_id = entry["id"]
                amount_paid = _float_value(request.form.get(f"amount_paid_{entry_id}"))
                paid_date = (request.form.get(f"paid_date_{entry_id}") or "").strip() or None
                notes = (request.form.get(f"notes_{entry_id}") or "").strip() or None
                manual_adjustment = _float_value(request.form.get(f"manual_adjustment_{entry_id}"))
                approved_late_arrangement = (request.form.get(f"approved_late_arrangement_{entry_id}") or "").strip().lower() == "yes"

                subtotal_due = round(
                    _float_value(entry.get("prior_balance"))
                    + _float_value(entry.get("prorated_charge"))
                    + manual_adjustment,
                    2,
                )
                is_exempt = str(entry.get("status") or "").strip() == "Exempt"
                late_fee_charge, _late_fee_note = _calculate_late_fee(
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
                current_charge = 0.0 if is_exempt else round(_float_value(entry.get("prorated_charge")) + manual_adjustment, 2)
                remaining_balance = 0.0 if is_exempt else round(max(total_due - amount_paid, 0.0), 2)
                status = _derive_status(total_due, amount_paid, paid_date, is_exempt, late_fee_charge)
                compliance_score = _score_for_status(settings, status)
                calculation_notes = (entry.get("calculation_notes") or "").strip()
                now = utcnow_iso()

                db_execute(
                    (
                        """
                        UPDATE resident_rent_sheet_entries
                        SET current_charge = %s,
                            total_due = %s,
                            amount_paid = %s,
                            remaining_balance = %s,
                            status = %s,
                            compliance_score = %s,
                            paid_date = %s,
                            notes = %s,
                            late_fee_charge = %s,
                            manual_adjustment = %s,
                            approved_late_arrangement = %s,
                            calculation_notes = %s,
                            updated_by_staff_user_id = %s,
                            updated_at = %s
                        WHERE id = %s
                        """
                        if g.get("db_kind") == "pg"
                        else
                        """
                        UPDATE resident_rent_sheet_entries
                        SET current_charge = ?,
                            total_due = ?,
                            amount_paid = ?,
                            remaining_balance = ?,
                            status = ?,
                            compliance_score = ?,
                            paid_date = ?,
                            notes = ?,
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
                        current_charge,
                        total_due,
                        amount_paid,
                        remaining_balance,
                        status,
                        compliance_score,
                        paid_date,
                        notes,
                        late_fee_charge,
                        manual_adjustment,
                        approved_late_arrangement if g.get("db_kind") == "pg" else (1 if approved_late_arrangement else 0),
                        calculation_notes,
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

        config = _ensure_default_rent_config(resident_id, shelter)
        config["apartment_number_snapshot"] = _normalize_apartment_number(shelter, config.get("apartment_number_snapshot"))
        config["apartment_size_snapshot"] = _derive_apartment_size_from_assignment(
            shelter,
            config.get("apartment_number_snapshot"),
        ) or config.get("apartment_size_snapshot")

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

        apartment_options = _apartment_options_for_shelter(shelter)

        if request.method == "POST":
            level_snapshot = (request.form.get("level_snapshot") or "").strip() or None
            apartment_number_snapshot = _normalize_apartment_number(
                shelter,
                request.form.get("apartment_number_snapshot"),
            )
            apartment_size_snapshot = _derive_apartment_size_from_assignment(
                shelter,
                apartment_number_snapshot,
            )
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
                    else
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

        return render_template(
            "case_management/resident_rent_history.html",
            resident=resident,
            rows=rows,
            rent_snapshot=rent_snapshot,
        )
