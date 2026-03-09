from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


residents = Blueprint("residents", __name__)


def _require_staff_or_admin() -> bool:
    return session.get("role") in {"admin", "staff", "case_manager", "ra"}


def _require_transfer_role() -> bool:
    return session.get("role") in {"admin", "case_manager"}


def _require_resident_create_role() -> bool:
    return session.get("role") in {"admin", "case_manager"}


@residents.get("/staff/residents")
@require_login
@require_shelter
def staff_residents():
    from app import init_db

    if not _require_staff_or_admin():
        flash("Staff only.", "error")
        return redirect(url_for("staff_home"))

    init_db()
    shelter = session["shelter"]

    show = (request.args.get("show") or "active").strip().lower()

    if show == "all":
        rows = db_fetchall(
            """
            SELECT *
            FROM residents
            WHERE shelter = %s
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """
            if g.get("db_kind") == "pg"
            else """
            SELECT *
            FROM residents
            WHERE shelter = ?
            ORDER BY is_active DESC, last_name ASC, first_name ASC
            """,
            (shelter,),
        )
    else:
        rows = db_fetchall(
            """
            SELECT *
            FROM residents
            WHERE shelter = %s AND is_active = TRUE
            ORDER BY last_name ASC, first_name ASC
            """
            if g.get("db_kind") == "pg"
            else """
            SELECT *
            FROM residents
            WHERE shelter = ? AND is_active = 1
            ORDER BY last_name ASC, first_name ASC
            """,
            (shelter,),
        )

    return render_template("staff_residents.html", residents=rows, shelter=shelter, show=show)


@residents.post("/staff/residents")
@require_login
@require_shelter
def staff_residents_post():
    from app import init_db
    from core.residents import generate_resident_code, generate_resident_identifier

    if not _require_resident_create_role():
        flash("Admin or case manager only.", "error")
        return redirect(url_for("residents.staff_residents"))

    init_db()
    shelter = session["shelter"]

    first = (request.form.get("first_name") or "").strip()
    last = (request.form.get("last_name") or "").strip()

    if not first or not last:
        flash("First and last name required.", "error")
        return redirect(url_for("residents.staff_residents"))

    resident_code = generate_resident_code()
    resident_identifier = generate_resident_identifier()

    db_execute(
        "INSERT INTO residents (resident_identifier, resident_code, first_name, last_name, shelter, is_active, created_at) "
        + ("VALUES (%s, %s, %s, %s, %s, %s, %s)" if g.get("db_kind") == "pg" else "VALUES (?, ?, ?, ?, ?, ?, ?)"),
        (resident_identifier, resident_code, first, last, shelter, True, utcnow_iso()),
    )

    log_action("resident", None, shelter, session.get("staff_user_id"), "create", f"code={resident_code} {first} {last}")
    flash("Resident created.", "ok")
    return redirect(url_for("residents.staff_residents"))


@residents.route("/staff/residents/<int:resident_id>/transfer", methods=["GET", "POST"])
@require_login
@require_shelter
def staff_resident_transfer(resident_id: int):
    from app import get_all_shelters, init_db
    from core.residents import record_resident_transfer

    if not _require_transfer_role():
        flash("Admin or case manager only.", "error")
        return redirect(url_for("staff_home"))

    init_db()
    all_shelters = get_all_shelters()

    resident = db_fetchone(
        "SELECT * FROM residents WHERE id = %s AND shelter = %s"
        if g.get("db_kind") == "pg"
        else "SELECT * FROM residents WHERE id = ? AND shelter = ?",
        (resident_id, session["shelter"]),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("residents.staff_residents"))

    from_shelter = resident["shelter"] if isinstance(resident, dict) else resident[1]

    if request.method == "POST":
        to_shelter = (request.form.get("to_shelter") or "").strip()
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
            """
            UPDATE leave_requests
            SET shelter = %s
            WHERE shelter = %s AND resident_identifier = %s AND status = 'pending'
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE leave_requests
            SET shelter = ?
            WHERE shelter = ? AND resident_identifier = ? AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            """
            UPDATE transport_requests
            SET shelter = %s
            WHERE shelter = %s AND resident_identifier = %s AND status = 'pending'
            """
            if g.get("db_kind") == "pg"
            else """
            UPDATE transport_requests
            SET shelter = ?
            WHERE shelter = ? AND resident_identifier = ? AND status = 'pending'
            """,
            (to_shelter, from_shelter, resident_identifier),
        )

        db_execute(
            "UPDATE residents SET shelter = %s WHERE id = %s"
            if g.get("db_kind") == "pg"
            else "UPDATE residents SET shelter = ? WHERE id = ?",
            (to_shelter, resident_id),
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
    from app import init_db

    if not _require_staff_or_admin():
        flash("Staff only.", "error")
        return redirect(url_for("staff_home"))

    init_db()
    shelter = session["shelter"]
    staff_id = session["staff_user_id"]
    active = (request.form.get("active") or "").strip()

    if active not in ["0", "1"]:
        flash("Invalid action.", "error")
        return redirect(url_for("residents.staff_residents"))

    if g.get("db_kind") == "pg":
        db_execute(
            "UPDATE residents SET is_active = %s WHERE id = %s AND shelter = %s",
            (active == "1", resident_id, shelter),
        )
    else:
        db_execute(
            "UPDATE residents SET is_active = ? WHERE id = ? AND shelter = ?",
            (1 if active == "1" else 0, resident_id, shelter),
        )

    log_action("resident", resident_id, shelter, staff_id, "set_active", f"active={active}")
    flash("Updated.", "ok")
    return redirect(url_for("residents.staff_residents"))
