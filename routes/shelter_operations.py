from datetime import date, datetime, timedelta
import random

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso


shelter_operations = Blueprint(
    "shelter_operations",
    __name__,
    url_prefix="/staff/shelter-operations",
)


def _week_start_tuesday(date_text: str) -> str:
    base_date = datetime.strptime(date_text, "%Y-%m-%d").date()
    weekday = base_date.weekday()
    days_to_tuesday = (weekday - 1) % 7
    tuesday = base_date - timedelta(days=days_to_tuesday)
    return tuesday.strftime("%Y-%m-%d")


def _week_dates_from_anchor(date_text: str) -> tuple[str, str, list[str]]:
    week_start = _week_start_tuesday(date_text)
    start_date = datetime.strptime(week_start, "%Y-%m-%d").date()
    week_dates = [
        (start_date + timedelta(days=i)).strftime("%Y-%m-%d")
        for i in range(7)
    ]
    week_end = week_dates[-1]
    return week_start, week_end, week_dates


@shelter_operations.route("/chores/config", methods=["GET", "POST"])
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


@shelter_operations.route("/chores", methods=["GET", "POST"])
@shelter_operations.route("/chore-board", methods=["GET", "POST"])
@require_login
@require_shelter
def chore_board():
    shelter = session.get("shelter")

    assigned_date = (request.values.get("assigned_date") or "").strip()
    if not assigned_date:
        assigned_date = str(date.today())

    week_start, week_end, week_dates = _week_dates_from_anchor(assigned_date)

    if request.method == "POST" and request.form.get("action") == "build_from_last_week":
        existing = db_fetchone(
            """
            SELECT 1
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            WHERE r.shelter = %s
              AND ca.assigned_date BETWEEN %s AND %s
            LIMIT 1
            """,
            (shelter, week_start, week_end),
        )

        if existing:
            flash("This week already has assignments. Clear it before rebuilding.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

        prev_start_date = datetime.strptime(week_start, "%Y-%m-%d").date() - timedelta(days=7)
        prev_start = prev_start_date.strftime("%Y-%m-%d")
        prev_end = (prev_start_date + timedelta(days=6)).strftime("%Y-%m-%d")

        prev_rows = db_fetchall(
            """
            SELECT chore_id, assigned_date
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            WHERE r.shelter = %s
              AND ca.assigned_date BETWEEN %s AND %s
            ORDER BY ca.assigned_date, chore_id
            """,
            (shelter, prev_start, prev_end),
        )

        if not prev_rows:
            flash("No previous week data to build from.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

        residents = db_fetchall(
            """
            SELECT id
            FROM residents
            WHERE shelter = %s AND is_active = TRUE
            ORDER BY last_name, first_name, id
            """,
            (shelter,),
        )

        resident_ids = [r["id"] for r in residents]

        if not resident_ids:
            flash("No active residents to assign.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

        random.shuffle(resident_ids)

        now = utcnow_iso()
        idx = 0

        for row in prev_rows:
            target_date = (
                datetime.strptime(row["assigned_date"], "%Y-%m-%d").date() + timedelta(days=7)
            ).strftime("%Y-%m-%d")

            resident_id = resident_ids[idx % len(resident_ids)]
            idx += 1

            existing = db_fetchone(
                """
                SELECT id
                FROM chore_assignments
                WHERE resident_id = %s
                  AND chore_id = %s
                  AND assigned_date = %s
                LIMIT 1
                """,
                (resident_id, row["chore_id"], target_date),
            )

            if existing:
                continue

            db_execute(
                """
                INSERT INTO chore_assignments
                (resident_id, chore_id, assigned_date, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'assigned', %s, %s)
                """,
                (resident_id, row["chore_id"], target_date, now, now),
            )

        flash("New week built from last week with randomized residents.", "success")
        return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

    if request.method == "POST" and not request.form.get("action"):
        resident_id = (request.form.get("resident_id") or "").strip()
        chore_id = (request.form.get("chore_id") or "").strip()
        assign_mode = (request.form.get("assign_mode") or "day").strip()

        if not resident_id or not chore_id:
            flash("Resident and chore are required.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

        dates_to_insert = week_dates if assign_mode == "week" else [assigned_date]
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

        return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

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
            ca.assigned_date,
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

    weekly_assignment_rows = db_fetchall(
        """
        SELECT
            ca.id,
            ca.resident_id,
            ca.chore_id,
            ca.assigned_date,
            ca.status,
            r.first_name,
            r.last_name,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE r.shelter = %s
          AND ca.assigned_date BETWEEN %s AND %s
        ORDER BY
            r.last_name,
            r.first_name,
            ct.name,
            ca.assigned_date
        """,
        (shelter, week_start, week_end),
    )

    weekly_rows_map: dict[tuple[int, int], dict] = {}

    for row in weekly_assignment_rows:
        row_key = (row["resident_id"], row["chore_id"])
        if row_key not in weekly_rows_map:
            weekly_rows_map[row_key] = {
                "assignment_id": row["id"],
                "resident_id": row["resident_id"],
                "chore_id": row["chore_id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "chore_name": row["chore_name"],
                "when_label": "",
                "days": {d: None for d in week_dates},
            }

        weekly_rows_map[row_key]["days"][row["assigned_date"]] = {
            "id": row["id"],
            "status": row["status"],
        }

    weekly_rows = list(weekly_rows_map.values())

    return render_template(
        "shelter_operations/chore_board.html",
        residents=residents,
        chores=chores,
        assignments=assignments,
        assigned_date=assigned_date,
        week_start=week_start,
        week_end=week_end,
        week_dates=week_dates,
        weekly_rows=weekly_rows,
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

    target = db_fetchone(
        """
        SELECT
            ca.id,
            ca.resident_id,
            ca.chore_id,
            ca.assigned_date
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        WHERE ca.id = %s
          AND r.shelter = %s
        LIMIT 1
        """,
        (assignment_id, shelter),
    )

    if not target:
        flash("Assignment not found.", "error")
        return redirect(url_for("shelter_operations.chore_board", assigned_date=assigned_date))

    week_start, week_end, week_dates = _week_dates_from_anchor(assigned_date or target["assigned_date"])

    target_rows = db_fetchall(
        """
        SELECT ca.id, ca.assigned_date
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        WHERE r.shelter = %s
          AND ca.resident_id = %s
          AND ca.chore_id = %s
          AND ca.assigned_date BETWEEN %s AND %s
        ORDER BY ca.assigned_date
        """,
        (shelter, target["resident_id"], target["chore_id"], week_start, week_end),
    )

    target_ids = {row["id"] for row in target_rows}

    for d in week_dates:
        target_has_date = any(row["assigned_date"] == d for row in target_rows)
        if not target_has_date:
            continue

        existing = db_fetchone(
            """
            SELECT ca.id
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            WHERE r.shelter = %s
              AND ca.resident_id = %s
              AND ca.chore_id = %s
              AND ca.assigned_date = %s
            LIMIT 1
            """,
            (shelter, resident_id, chore_id, d),
        )

        if existing and existing["id"] not in target_ids:
            flash("That weekly edit would create a duplicate assignment.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

    for row in target_rows:
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
            (resident_id, chore_id, utcnow_iso(), row["id"], shelter),
        )

    flash("Weekly assignment updated.", "success")
    return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))


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
