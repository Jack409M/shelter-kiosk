from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import get_all_shelters, init_db


residents = Blueprint("residents", __name__)


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _require_staff_or_admin() -> bool:
    return session.get("role") in {"admin", "shelter_director", "staff", "case_manager", "ra"}


def _require_transfer_role() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _require_resident_create_role() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _shelter_equals_sql(column_name: str) -> str:
    if g.get("db_kind") == "pg":
        return f"LOWER(COALESCE({column_name}, '')) = %s"
    return f"LOWER(COALESCE({column_name}, '')) = ?"


def _return_redirect(default_endpoint: str = "residents.staff_residents", **default_values):
    next_url = (request.form.get("next") or request.args.get("next") or "").strip()
    if next_url:
        return redirect(next_url)
    return redirect(url_for(default_endpoint, **default_values))


def _normalize_all_shelter_values() -> None:
    updates = [
        ("residents", "shelter"),
        ("program_enrollments", "shelter"),
        ("leave_requests", "shelter"),
        ("transport_requests", "shelter"),
        ("attendance_events", "shelter"),
        ("resident_transfers", "from_shelter"),
        ("resident_transfers", "to_shelter"),
        ("staff_shelter_assignments", "shelter"),
        ("audit_log", "shelter"),
    ]

    for table_name, column_name in updates:
        try:
            if g.get("db_kind") == "pg":
                db_execute(
                    f"""
                    UPDATE {table_name}
                    SET {column_name} = LOWER(BTRIM({column_name}))
                    WHERE {column_name} IS NOT NULL
                      AND {column_name} <> LOWER(BTRIM({column_name}))
                    """
                )
            else:
                db_execute(
                    f"""
                    UPDATE {table_name}
                    SET {column_name} = LOWER(TRIM({column_name}))
                    WHERE {column_name} IS NOT NULL
                      AND {column_name} <> LOWER(TRIM({column_name}))
                    """
                )
        except Exception:
            continue


def _parse_birth_year(value: str | None) -> int | None:
    text = (value or "").strip()
    if not text:
        return None

    if not text.isdigit():
        return None

    year = int(text)
    if year < 1900 or year > 2100:
        return None

    return year


def _move_supporting_shelters() -> set[str]:
    return {"abba", "gratitude", "haven"}


def _same_shelter_housing_update_allowed(shelter: str) -> bool:
    return shelter in {"abba", "gratitude"}


def _apartment_options_for_shelter_local(shelter: str) -> list[str]:
    from routes.rent_tracking_parts.calculations import _apartment_options_for_shelter

    return _apartment_options_for_shelter(shelter)


def _normalize_apartment_number_local(shelter: str, apartment_number: str | None) -> str | None:
    from routes.rent_tracking_parts.calculations import _normalize_apartment_number

    return _normalize_apartment_number(shelter, apartment_number)


def _derive_apartment_size_local(shelter: str, apartment_number: str | None) -> str | None:
    from routes.rent_tracking_parts.calculations import _derive_apartment_size_from_assignment

    return _derive_apartment_size_from_assignment(shelter, apartment_number)


def _active_rent_config_for_resident(resident_id: int, shelter: str):
    ph = "%s" if g.get("db_kind") == "pg" else "?"
    row = db_fetchone(
        f"""
        SELECT *
        FROM resident_rent_configs
        WHERE resident_id = {ph}
          AND LOWER(COALESCE(shelter, '')) = {ph}
          AND COALESCE(effective_end_date, '') = ''
        ORDER BY effective_start_date DESC, id DESC
        LIMIT 1
        """,
        (resident_id, shelter),
    )
    return dict(row) if row else None


def _upsert_resident_housing_assignment(
    resident_id: int,
    destination_shelter: str,
    apartment_number: str | None,
) -> None:
    destination_shelter = _normalize_shelter_name(destination_shelter)
    apartment_number = _normalize_apartment_number_local(destination_shelter, apartment_number)
    apartment_size = _derive_apartment_size_local(destination_shelter, apartment_number)

    if destination_shelter == "haven":
        apartment_number = None
        apartment_size = "Bed"

    now = utcnow_iso()
    effective_start_date = now[:10]
    active_config = _active_rent_config_for_resident(resident_id, destination_shelter)

    if active_config:
        current_apartment = (active_config.get("apartment_number_snapshot") or "").strip() or None
        current_size = (active_config.get("apartment_size_snapshot") or "").strip() or None

        if current_apartment == apartment_number and current_size == apartment_size:
            return

        db_execute(
            """
            UPDATE resident_rent_configs
            SET effective_end_date = %s,
                updated_at = %s
            WHERE id = %s
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE resident_rent_configs
            SET effective_end_date = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (effective_start_date, now, active_config["id"]),
        )

        level_snapshot = active_config.get("level_snapshot")
        monthly_rent = active_config.get("monthly_rent") or 0
        is_exempt = active_config.get("is_exempt") or (False if g.get("db_kind") == "pg" else 0)
    else:
        level_snapshot = None
        monthly_rent = 0
        is_exempt = False if g.get("db_kind") == "pg" else 0

    db_execute(
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
        """,
        (
            resident_id,
            destination_shelter,
            level_snapshot,
            apartment_number,
            apartment_size,
            monthly_rent,
            is_exempt if g.get("db_kind") == "pg" else (1 if is_exempt else 0),
            effective_start_date,
            None,
            session.get("staff_user_id"),
            now,
            now,
        ),
    )


@residents.get("/staff/residents")
@require_login
@require_shelter
def staff_residents():
    if not _require_staff_or_admin():
        flash("Staff only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    shelter = _normalize_shelter_name(session.get("shelter"))
    show = (request.args.get("show") or "active").strip().lower()

    if show == "all":
        rows = db_fetchall(
            f"""
            SELECT *
            FROM residents
            WHERE {_shelter_equals_sql("shelter")}
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """,
            (shelter,),
        )
    else:
        rows = db_fetchall(
            f"""
            SELECT *
            FROM residents
            WHERE {_shelter_equals_sql("shelter")} AND is_active = {("TRUE" if g.get("db_kind") == "pg" else "1")}
            ORDER BY last_name ASC, first_name ASC
            """,
            (shelter,),
        )

    return render_template("staff_residents.html", residents=rows, shelter=shelter, show=show)


@residents.post("/staff/residents")
@require_login
@require_shelter
def staff_residents_post():
    from core.residents import generate_resident_code, generate_resident_identifier

    if not _require_resident_create_role():
        flash("Admin, shelter director, or case manager only.", "error")
        return redirect(url_for("residents.staff_residents"))

    init_db()
    _normalize_all_shelter_values()

    shelter = _normalize_shelter_name(session.get("shelter"))
    first = (request.form.get("first_name") or "").strip()
    last = (request.form.get("last_name") or "").strip()
    birth_year_raw = request.form.get("birth_year")
    phone = (request.form.get("phone") or "").strip()
    email = (request.form.get("email") or "").strip()
    emergency_contact_name = (request.form.get("emergency_contact_name") or "").strip()
    emergency_contact_relationship = (request.form.get("emergency_contact_relationship") or "").strip()
    emergency_contact_phone = (request.form.get("emergency_contact_phone") or "").strip()
    medical_alerts = (request.form.get("medical_alerts") or "").strip()
    medical_notes = (request.form.get("medical_notes") or "").strip()

    if not first or not last:
        flash("First and last name required.", "error")
        return redirect(url_for("residents.staff_residents"))

    birth_year = _parse_birth_year(birth_year_raw)
    if birth_year_raw and birth_year is None:
        flash("Birth year must be a valid 4 digit year.", "error")
        return redirect(url_for("residents.staff_residents"))

    resident_code = generate_resident_code()
    resident_identifier = generate_resident_identifier()

    db_execute(
        (
            "INSERT INTO residents ("
            "resident_identifier, resident_code, first_name, last_name, birth_year, phone, email, "
            "emergency_contact_name, emergency_contact_relationship, emergency_contact_phone, "
            "medical_alerts, medical_notes, shelter, is_active, created_at"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        if g.get("db_kind") == "pg"
        else
        (
            "INSERT INTO residents ("
            "resident_identifier, resident_code, first_name, last_name, birth_year, phone, email, "
            "emergency_contact_name, emergency_contact_relationship, emergency_contact_phone, "
            "medical_alerts, medical_notes, shelter, is_active, created_at"
            ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        ),
        (
            resident_identifier,
            resident_code,
            first,
            last,
            birth_year,
            phone or None,
            email or None,
            emergency_contact_name or None,
            emergency_contact_relationship or None,
            emergency_contact_phone or None,
            medical_alerts or None,
            medical_notes or None,
            shelter,
            True if g.get("db_kind") == "pg" else 1,
            utcnow_iso(),
        ),
    )

    log_action(
        "resident",
        None,
        shelter,
        session.get("staff_user_id"),
        "create",
        (
            f"code={resident_code} "
            f"name={first} {last} "
            f"birth_year={birth_year or ''} "
            f"emergency_contact={emergency_contact_name or ''}"
        ).strip(),
    )
    flash("Resident created.", "ok")
    return redirect(url_for("residents.staff_residents"))


@residents.route("/staff/residents/<int:resident_id>/transfer", methods=["GET", "POST"])
@require_login
@require_shelter
def staff_resident_transfer(resident_id: int):
    from core.residents import record_resident_transfer
    from routes.rent_tracking_parts.dates import _current_year_month
    from routes.rent_tracking_parts.views import _ensure_sheet_for_month

    if not _require_transfer_role():
        flash("Admin, shelter director, or case manager only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    all_shelters = [_normalize_shelter_name(s) for s in get_all_shelters()]
    current_shelter = _normalize_shelter_name(session.get("shelter"))
    next_url = (request.form.get("next") or request.args.get("next") or "").strip()

    resident = db_fetchone(
        f"SELECT * FROM residents WHERE id = {('%s' if g.get('db_kind') == 'pg' else '?')} AND {_shelter_equals_sql('shelter')}",
        (resident_id, current_shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    from_shelter = _normalize_shelter_name(resident["shelter"] if isinstance(resident, dict) else resident[1])
    shelter_choices = [s for s in all_shelters if s in _move_supporting_shelters()]

    if _same_shelter_housing_update_allowed(from_shelter) and from_shelter not in shelter_choices:
        shelter_choices.append(from_shelter)

    shelter_choices = sorted(set(shelter_choices))
    active_config = _active_rent_config_for_resident(resident_id, from_shelter)
    current_apartment_number = (active_config or {}).get("apartment_number_snapshot")
    current_apartment_size = _derive_apartment_size_local(from_shelter, current_apartment_number) or (active_config or {}).get("apartment_size_snapshot")
    destination_shelter_prefill = (request.form.get("to_shelter") or request.args.get("to_shelter") or "").strip().lower() or from_shelter
    apartment_options = _apartment_options_for_shelter_local(destination_shelter_prefill)

    if request.method == "POST":
        to_shelter = _normalize_shelter_name(request.form.get("to_shelter"))
        note = (request.form.get("note") or "").strip()
        apartment_number = _normalize_apartment_number_local(to_shelter, request.form.get("apartment_number"))
        apartment_size = _derive_apartment_size_local(to_shelter, apartment_number)

        if to_shelter not in shelter_choices:
            flash("Select a valid shelter.", "error")
            return redirect(url_for("residents.staff_resident_transfer", resident_id=resident_id, next=next_url))

        same_shelter_move = to_shelter == from_shelter

        if to_shelter in {"abba", "gratitude"} and not apartment_number:
            flash("Apartment number is required for Abba and Gratitude moves.", "error")
            return redirect(url_for("residents.staff_resident_transfer", resident_id=resident_id, next=next_url, to_shelter=to_shelter))

        if to_shelter == "haven":
            apartment_number = None
            apartment_size = "Bed"

        if same_shelter_move and not _same_shelter_housing_update_allowed(from_shelter):
            flash("This shelter does not use same shelter apartment reassignment here.", "error")
            return redirect(url_for("residents.staff_resident_transfer", resident_id=resident_id, next=next_url))

        if same_shelter_move:
            current_normalized_apartment = _normalize_apartment_number_local(from_shelter, current_apartment_number)
            if current_normalized_apartment == apartment_number:
                flash("No housing change detected.", "error")
                return redirect(url_for("residents.staff_resident_transfer", resident_id=resident_id, next=next_url))

            _upsert_resident_housing_assignment(
                resident_id=resident_id,
                destination_shelter=to_shelter,
                apartment_number=apartment_number,
            )

            try:
                rent_year, rent_month = _current_year_month()
                _ensure_sheet_for_month(to_shelter, rent_year, rent_month)
            except Exception:
                pass

            log_action(
                "resident",
                resident_id,
                to_shelter,
                session.get("staff_user_id"),
                "housing_move",
                f"shelter={to_shelter} apartment={apartment_number or ''} unit_type={apartment_size or ''} note={note}".strip(),
            )

            flash(
                f"Housing updated for {to_shelter}. Apartment {apartment_number or 'cleared'} saved.",
                "ok",
            )
            return _return_redirect()

        record_resident_transfer(
            resident_id=resident_id,
            from_shelter=from_shelter,
            to_shelter=to_shelter,
            note=note,
        )

        db_execute(
            """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (%s, %s, %s, %s, %s, %s)
            """
            if g.get("db_kind") == "pg"
            else """
            INSERT INTO attendance_events (resident_id, shelter, event_type, event_time, staff_user_id, note)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                resident_id,
                from_shelter,
                "check_out",
                utcnow_iso(),
                session.get("staff_user_id"),
                f"Transferred to {to_shelter}. {note}".strip(),
            ),
        )

        resident_identifier = resident["resident_identifier"] if isinstance(resident, dict) else resident[2]

        db_execute(
            f"""
            UPDATE leave_requests
            SET shelter = {('%s' if g.get('db_kind') == 'pg' else '?')}
            WHERE {_shelter_equals_sql('shelter')} AND resident_identifier = {('%s' if g.get('db_kind') == 'pg' else '?')} AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            f"""
            UPDATE transport_requests
            SET shelter = {('%s' if g.get('db_kind') == 'pg' else '?')}
            WHERE {_shelter_equals_sql('shelter')} AND resident_identifier = {('%s' if g.get('db_kind') == 'pg' else '?')} AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            "UPDATE residents SET shelter = %s WHERE id = %s"
            if g.get("db_kind") == "pg"
            else "UPDATE residents SET shelter = ? WHERE id = ?",
            (to_shelter, resident_id),
        )

        _upsert_resident_housing_assignment(
            resident_id=resident_id,
            destination_shelter=to_shelter,
            apartment_number=apartment_number,
        )

        try:
            rent_year, rent_month = _current_year_month()
            _ensure_sheet_for_month(to_shelter, rent_year, rent_month)
        except Exception:
            pass

        log_action(
            "resident",
            resident_id,
            to_shelter,
            session.get("staff_user_id"),
            "transfer",
            f"from={from_shelter} to={to_shelter} apartment={apartment_number or ''} unit_type={apartment_size or ''} note={note}",
        )

        if to_shelter in {"abba", "gratitude"}:
            flash(f"Resident transferred from {from_shelter} to {to_shelter} and assigned to apartment {apartment_number}.", "ok")
        elif to_shelter == "haven":
            flash(f"Resident transferred from {from_shelter} to {to_shelter}. Apartment assignment cleared for dorm style housing.", "ok")
        else:
            flash(f"Resident transferred from {from_shelter} to {to_shelter}.", "ok")

        return _return_redirect()

    return render_template(
        "staff_resident_transfer.html",
        resident=resident,
        from_shelter=from_shelter,
        shelters=shelter_choices,
        next=next_url,
        current_apartment_number=current_apartment_number,
        current_apartment_size=current_apartment_size,
        apartment_options=apartment_options,
    )


@residents.post("/staff/residents/<int:resident_id>/set-active")
@require_login
@require_shelter
def staff_resident_set_active(resident_id: int):
    if not _require_staff_or_admin():
        flash("Staff only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    shelter = _normalize_shelter_name(session.get("shelter"))
    staff_id = session.get("staff_user_id")
    active = (request.form.get("active") or "").strip()

    if active not in ["0", "1"]:
        flash("Invalid action.", "error")
        return _return_redirect()

    resident = db_fetchone(
        f"SELECT id FROM residents WHERE id = {('%s' if g.get('db_kind') == 'pg' else '?')} AND {_shelter_equals_sql('shelter')}",
        (resident_id, shelter),
    )
    if not resident:
        flash("Resident not found.", "error")
        return _return_redirect()

    if g.get("db_kind") == "pg":
        db_execute(
            f"UPDATE residents SET is_active = %s WHERE id = %s AND {_shelter_equals_sql('shelter')}",
            (active == "1", resident_id, shelter),
        )
    else:
        db_execute(
            f"UPDATE residents SET is_active = ? WHERE id = ? AND {_shelter_equals_sql('shelter')}",
            (1 if active == "1" else 0, resident_id, shelter),
        )

    log_action("resident", resident_id, shelter, staff_id, "set_active", f"active={active}")
    flash("Updated.", "ok")
    return _return_redirect()
