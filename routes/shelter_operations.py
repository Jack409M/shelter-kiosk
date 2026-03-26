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

    # 🔥 BUILD FROM LAST WEEK
    if request.method == "POST" and request.form.get("action") == "build_from_last_week":

        # block if current week already has data
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

        # get previous week
        prev_start = (datetime.strptime(week_start, "%Y-%m-%d").date() - timedelta(days=7)).strftime("%Y-%m-%d")
        prev_end = (datetime.strptime(prev_start, "%Y-%m-%d").date() + timedelta(days=6)).strftime("%Y-%m-%d")

        prev_rows = db_fetchall(
            """
            SELECT chore_id, assigned_date
            FROM chore_assignments ca
            JOIN residents r ON r.id = ca.resident_id
            WHERE r.shelter = %s
              AND ca.assigned_date BETWEEN %s AND %s
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

    # EXISTING ASSIGN LOGIC (unchanged)
    if request.method == "POST" and not request.form.get("action"):
        resident_id = (request.form.get("resident_id") or "").strip()
        chore_id = (request.form.get("chore_id") or "").strip()
        assign_mode = (request.form.get("assign_mode") or "day").strip()

        if not resident_id or not chore_id:
            flash("Resident and chore are required.", "error")
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

        dates_to_insert = week_dates if assign_mode == "week" else [assigned_date]

        now = utcnow_iso()

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
                continue

            db_execute(
                """
                INSERT INTO chore_assignments
                (resident_id, chore_id, assigned_date, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'assigned', %s, %s)
                """,
                (resident_id, chore_id, d, now, now),
            )

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

    weekly_rows_map = {}

    for row in weekly_assignment_rows:
        key = (row["resident_id"], row["chore_id"])
        if key not in weekly_rows_map:
            weekly_rows_map[key] = {
                "assignment_id": row["id"],
                "resident_id": row["resident_id"],
                "chore_id": row["chore_id"],
                "first_name": row["first_name"],
                "last_name": row["last_name"],
                "chore_name": row["chore_name"],
                "when_label": "",
                "days": {d: None for d in week_dates},
            }

        weekly_rows_map[key]["days"][row["assigned_date"]] = {
            "id": row["id"],
            "status": row["status"],
        }

    weekly_rows = list(weekly_rows_map.values())

    return render_template(
        "shelter_operations/chore_board.html",
        residents=residents,
        chores=chores,
        assigned_date=assigned_date,
        week_start=week_start,
        week_end=week_end,
        week_dates=week_dates,
        weekly_rows=weekly_rows,
    )
