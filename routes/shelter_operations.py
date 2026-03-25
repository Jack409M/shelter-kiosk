from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_execute
from core.helpers import utcnow_iso


shelter_operations = Blueprint(
    "shelter_operations",
    __name__,
    url_prefix="/staff/shelter-operations",
)


@shelter_operations.route("/chores", methods=["GET", "POST"])
@require_login
@require_shelter
def chore_management():
    shelter = session.get("shelter")

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()

        if not name:
            flash("Chore name is required.", "error")
            return redirect(url_for("shelter_operations.chore_management"))

        db_execute(
            """
            INSERT INTO chore_templates (shelter, name, description, active, created_at)
            VALUES (%s, %s, %s, 1, %s)
            """,
            (shelter, name, description or None, utcnow_iso()),
        )

        flash("Chore added.", "success")
        return redirect(url_for("shelter_operations.chore_management"))

    chores = db_fetchall(
        """
        SELECT id, name, description, active
        FROM chore_templates
        WHERE shelter = %s
        ORDER BY active DESC, name ASC
        """,
        (shelter,),
    )

    return render_template(
        "shelter_operations/chore_management.html",
        chores=chores,
    )


@shelter_operations.route("/chores/<int:chore_id>/toggle", methods=["POST"])
@require_login
@require_shelter
def toggle_chore(chore_id: int):
    shelter = session.get("shelter")

    db_execute(
        """
        UPDATE chore_templates
        SET active = CASE WHEN active = 1 THEN 0 ELSE 1 END
        WHERE id = %s AND shelter = %s
        """,
        (chore_id, shelter),
    )

    flash("Chore updated.", "success")
    return redirect(url_for("shelter_operations.chore_management"))


@shelter_operations.route("/chore-board", methods=["GET", "POST"])
@require_login
@require_shelter
def chore_board():
    shelter = session.get("shelter")

    if request.method == "POST":
        resident_id = request.form.get("resident_id")
        chore_id = request.form.get("chore_id")

        if not resident_id or not chore_id:
            flash("Resident and chore are required.", "error")
            return redirect(url_for("shelter_operations.chore_board"))

        db_execute(
            """
            INSERT INTO chore_assignments
            (resident_id, chore_id, assigned_date, status, created_at, updated_at)
            VALUES (%s, %s, CURRENT_DATE::text, 'assigned', %s, %s)
            """,
            (resident_id, chore_id, utcnow_iso(), utcnow_iso()),
        )

        flash("Chore assigned.", "success")
        return redirect(url_for("shelter_operations.chore_board"))

    residents = db_fetchall(
        """
        SELECT id, first_name, last_name
        FROM residents
        WHERE shelter = %s AND is_active = TRUE
        ORDER BY last_name, first_name
        """,
        (shelter,),
    )

    chores = db_fetchall(
        """
        SELECT id, name
        FROM chore_templates
        WHERE shelter = %s AND active = 1
        ORDER BY name
        """,
        (shelter,),
    )

    assignments = db_fetchall(
        """
        SELECT
            r.first_name,
            r.last_name,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE r.shelter = %s
          AND ca.assigned_date = CURRENT_DATE::text
        ORDER BY r.last_name, r.first_name
        """,
        (shelter,),
    )

    return render_template(
        "shelter_operations/chore_board.html",
        residents=residents,
        chores=chores,
        assignments=assignments,
    )
