from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone, db_execute
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

    assigned_date = (request.values.get("assigned_date") or "").strip()
    if not assigned_date:
        from datetime import date
        assigned_date = str(date.today())

    if request.method == "POST":
        resident_id = (request.form.get("resident_id") or "").strip()
        chore_id = (request.form.get("chore_id") or "").strip()
        assign_mode = (request.form.get("assign_mode") or "day").strip()

        if not resident_id or not chore_id:
            flash("Resident and chore are required.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))

        from datetime import datetime, timedelta

        base_date = datetime.strptime(assigned_date, "%Y-%m-%d")
        weekday = base_date.weekday()
        days_to_tuesday = (weekday - 1) % 7
        tuesday = base_date - timedelta(days=days_to_tuesday)

        dates_to_insert = []

        if assign_mode == "week":
            for i in range(7):
                d = tuesday + timedelta(days=i)
                dates_to_insert.append(d.strftime("%Y-%m-%d"))
        else:
            dates_to_insert.append(assigned_date)

        now = utcnow_iso()
        inserted_count = 0
        skipped_count = 0

        for d in dates_to_insert:
            existing = db_fetchone(
                """
                SELECT id
                FROM chore_assignments
                WHERE resident_id = %s
                  AND chore_id = %s
                  AND assigned_date = %s
                LIMIT 1
                """,
                (resident_id, chore_id, d),
            )

            if existing:
                skipped_count += 1
                continue

            db_execute(
                """
                INSERT INTO chore_assignments
                (resident_id, chore_id, assigned_date, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'assigned', %s, %s)
                """,
                (resident_id, chore_id, d, now, now),
            )
            inserted_count += 1

        if inserted_count and skipped_count:
            flash(
                f"Added {inserted_count} assignment(s). Skipped {skipped_count} duplicate assignment(s).",
                "success",
            )
        elif inserted_count:
            if assign_mode == "week":
                flash("Chore assigned for full week.", "success")
            else:
                flash("Chore assigned for selected day.", "success")
        else:
            flash("No new assignments were added because matching assignments already exist.", "error")

        return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))

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
            ca.id,
            ca.resident_id,
            ca.chore_id,
            ca.status,
            r.first_name,
            r.last_name,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE r.shelter = %s
          AND ca.assigned_date = %s
        ORDER BY
            CASE WHEN ca.status = 'completed' THEN 1 ELSE 0 END,
            r.last_name,
            r.first_name,
            ct.name
        """,
        (shelter, assigned_date),
    )

    return render_template(
        "shelter_operations/chore_board.html",
        residents=residents,
        chores=chores,
        assignments=assignments,
        assigned_date=assigned_date,
    )


@shelter_operations.route("/chore-board/<int:assignment_id>/edit", methods=["POST"])
@require_login
@require_shelter
def edit_assignment(assignment_id: int):
    shelter = session.get("shelter")

    resident_id = (request.form.get("resident_id") or "").strip()
    chore_id = (request.form.get("chore_id") or "").strip()
    assigned_date = (request.form.get("assigned_date") or "").strip()

    if not resident_id or not chore_id:
        flash("Resident and chore are required.", "error")
        return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))

    existing = db_fetchone(
        """
        SELECT id
        FROM chore_assignments
        WHERE resident_id = %s
          AND chore_id = %s
          AND assigned_date = %s
          AND id != %s
        LIMIT 1
        """,
        (resident_id, chore_id, assigned_date, assignment_id),
    )

    if existing:
        flash("That assignment already exists.", "error")
        return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))

    db_execute(
        """
        UPDATE chore_assignments ca
        SET
            resident_id = %s,
            chore_id = %s,
            updated_at = %s
        FROM residents r
        WHERE ca.id = %s
          AND r.id = ca.resident_id
          AND r.shelter = %s
        """,
        (resident_id, chore_id, utcnow_iso(), assignment_id, shelter),
    )

    flash("Assignment updated.", "success")
    return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))


@shelter_operations.route("/chore-board/<int:assignment_id>/toggle-status", methods=["POST"])
@require_login
@require_shelter
def toggle_assignment_status(assignment_id: int):
    shelter = session.get("shelter")
    assigned_date = (request.form.get("assigned_date") or "").strip()

    db_execute(
        """
        UPDATE chore_assignments ca
        SET
            status = CASE
                WHEN ca.status = 'completed' THEN 'assigned'
                ELSE 'completed'
            END,
            updated_at = %s
        FROM residents r
        WHERE ca.id = %s
          AND r.id = ca.resident_id
          AND r.shelter = %s
        """,
        (utcnow_iso(), assignment_id, shelter),
    )

    flash("Chore status updated.", "success")
    return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))


@shelter_operations.route("/chore-board/<int:assignment_id>/delete", methods=["POST"])
@require_login
@require_shelter
def delete_assignment(assignment_id: int):
    shelter = session.get("shelter")
    assigned_date = (request.form.get("assigned_date") or "").strip()

    db_execute(
        """
        DELETE FROM chore_assignments ca
        USING residents r
        WHERE ca.id = %s
          AND r.id = ca.resident_id
          AND r.shelter = %s
        """,
        (assignment_id, shelter),
    )

    flash("Assignment deleted.", "success")
    return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))
