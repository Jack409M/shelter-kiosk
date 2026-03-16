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

    if not _require_transfer_role():
        flash("Admin, shelter director, or case manager only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    _normalize_all_shelter_values()

    all_shelters = [_normalize_shelter_name(s) for s in get_all_shelters()]
    current_shelter = _normalize_shelter_name(session.get("shelter"))

    resident = db_fetchone(
        f"SELECT * FROM residents WHERE id = {('%s' if g.get('db_kind') == 'pg' else '?')} AND {_shelter_equals_sql('shelter')}",
        (resident_id, current_shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    from_shelter = _normalize_shelter_name(resident["shelter"] if isinstance(resident, dict) else resident[1])

    if request.method == "POST":
        to_shelter = _normalize_shelter_name(request.form.get("to_shelter"))
        note = (request.form.get("note") or "").strip()

        if to_shelter not in all_shelters:
            flash("Select a valid shelter.", "error")
            return redirect(url_for("residents.staff_resident_transfer", resident_id=resident_id))

        if to_shelter == from_shelter:
            flash("Resident is already at that shelter.", "error")
            return redirect(url_for("residents.staff_resident_transfer", resident_id=resident_id))

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

        log_action(
            "resident",
            resident_id,
            to_shelter,
            session.get("staff_user_id"),
            "transfer",
            f"from={from_shelter} to={to_shelter} note={note}",
        )

        flash(f"Resident transferred from {from_shelter} to {to_shelter}.", "ok")
        return redirect(url_for("residents.staff_residents"))

    return render_template(
        "staff_resident_transfer.html",
        resident=resident,
        from_shelter=from_shelter,
        shelters=[s for s in all_shelters if s != from_shelter],
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
        return redirect(url_for("residents.staff_residents"))

    resident = db_fetchone(
        f"SELECT id FROM residents WHERE id = {('%s' if g.get('db_kind') == 'pg' else '?')} AND {_shelter_equals_sql('shelter')}",
        (resident_id, shelter),
    )
    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

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
    return redirect(url_for("residents.staff_residents"))
