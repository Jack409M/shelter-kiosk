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


def _normalize_time_value(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw:
        return None

    try:
        parsed = datetime.strptime(raw, "%H:%M")
        return parsed.strftime("%H:%M")
    except ValueError:
        return None


def _normalize_default_day(value: str) -> str | None:
    raw = (value or "").strip().lower()
    if not raw:
        return None

    allowed = {
        "tue": "tue",
        "wed": "wed",
        "thu": "thu",
        "fri": "fri",
        "sat": "sat",
        "sun": "sun",
        "mon": "mon",
    }
    return allowed.get(raw)


def _clone_previous_week(
    shelter: str,
    target_week_start: str,
    target_week_end: str,
    randomize_residents: bool,
) -> tuple[bool, str, str]:
    existing = db_fetchone(
        """
        SELECT 1
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        WHERE r.shelter = %s
          AND ca.assigned_date BETWEEN %s AND %s
        LIMIT 1
        """,
        (shelter, target_week_start, target_week_end),
    )

    if existing:
        return False, "error", "This week already has assignments. Clear it before cloning."

    prev_start_date = datetime.strptime(target_week_start, "%Y-%m-%d").date() - timedelta(days=7)
    prev_start = prev_start_date.strftime("%Y-%m-%d")
    prev_end = (prev_start_date + timedelta(days=6)).strftime("%Y-%m-%d")

    prev_rows = db_fetchall(
        """
        SELECT
            ca.resident_id,
            ca.chore_id,
            ca.assigned_date,
            ca.status
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        WHERE r.shelter = %s
          AND ca.assigned_date BETWEEN %s AND %s
        ORDER BY ca.assigned_date, ca.chore_id, ca.resident_id
        """,
        (shelter, prev_start, prev_end),
    )

    if not prev_rows:
        return False, "error", "No previous week data to clone."

    now = utcnow_iso()

    if not randomize_residents:
        inserted_count = 0

        for row in prev_rows:
            target_date = (
                datetime.strptime(row["assigned_date"], "%Y-%m-%d").date() + timedelta(days=7)
            ).strftime("%Y-%m-%d")

            existing_assignment = db_fetchone(
                """
                SELECT id
                FROM chore_assignments
                WHERE resident_id = %s
                  AND chore_id = %s
                  AND assigned_date = %s
                LIMIT 1
                """,
                (row["resident_id"], row["chore_id"], target_date),
            )

            if existing_assignment:
                continue

            db_execute(
                """
                INSERT INTO chore_assignments
                (resident_id, chore_id, assigned_date, status, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    row["resident_id"],
                    row["chore_id"],
                    target_date,
                    row["status"] or "assigned",
                    now,
                    now,
                ),
            )
            inserted_count += 1

        if inserted_count:
            return True, "success", "Week cloned from last week."
        return False, "error", "No new assignments were cloned."

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
        return False, "error", "No active residents to assign."

    previous_week_rows = db_fetchall(
        """
        SELECT
            ca.resident_id,
            ca.chore_id,
            ca.assigned_date
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        WHERE r.shelter = %s
          AND ca.assigned_date BETWEEN %s AND %s
        ORDER BY r.last_name, r.first_name, ca.chore_id, ca.assigned_date
        """,
        (shelter, prev_start, prev_end),
    )

    if not previous_week_rows:
        return False, "error", "No previous week data to clone."

    weekly_rows_map: dict[tuple[int, str], dict] = {}

    for row in previous_week_rows:
        source_week_start = _week_start_tuesday(row["assigned_date"])
        row_key = (row["chore_id"], source_week_start)

        if row_key not in weekly_rows_map:
            weekly_rows_map[row_key] = {
                "chore_id": row["chore_id"],
                "dates": [],
            }

        weekly_rows_map[row_key]["dates"].append(row["assigned_date"])

    weekly_row_groups = list(weekly_rows_map.values())
    random.shuffle(resident_ids)

    inserted_count = 0

    for idx, weekly_row in enumerate(weekly_row_groups):
        resident_id = resident_ids[idx % len(resident_ids)]

        for source_date in weekly_row["dates"]:
            target_date = (
                datetime.strptime(source_date, "%Y-%m-%d").date() + timedelta(days=7)
            ).strftime("%Y-%m-%d")

            existing_assignment = db_fetchone(
                """
                SELECT id
                FROM chore_assignments
                WHERE resident_id = %s
                  AND chore_id = %s
                  AND assigned_date = %s
                LIMIT 1
                """,
                (resident_id, weekly_row["chore_id"], target_date),
            )

            if existing_assignment:
                continue

            db_execute(
                """
                INSERT INTO chore_assignments
                (resident_id, chore_id, assigned_date, status, created_at, updated_at)
                VALUES (%s, %s, %s, 'assigned', %s, %s)
                """,
                (resident_id, weekly_row["chore_id"], target_date, now, now),
            )
            inserted_count += 1

    if inserted_count:
        return True, "success", "Week cloned from last week and residents randomized."
    return False, "error", "No new assignments were cloned."


@shelter_operations.route("/chores/config", methods=["GET", "POST"])
@require_login
@require_shelter
def chore_management():
    shelter = session.get("shelter")

    if request.method == "POST":
        name = (request.form.get("name") or "").strip()
        when_time = _normalize_time_value(request.form.get("when_time") or "")
        default_day = _normalize_default_day(request.form.get("default_day") or "")
        description = (request.form.get("description") or "").strip()

        if not name:
            flash("Chore name is required.", "error")
            return redirect(url_for("shelter_operations.chore_management"))

        raw_when_time = (request.form.get("when_time") or "").strip()
        if raw_when_time and not when_time:
            flash("When time must be in HH:MM format.", "error")
            return redirect(url_for("shelter_operations.chore_management"))

        db_execute(
            """
            INSERT INTO chore_templates
            (shelter, name, when_time, default_day, description, active, created_at)
            VALUES (%s, %s, %s, %s, %s, 1, %s)
            """,
            (shelter, name, when_time, default_day, description or None, utcnow_iso()),
        )

        flash("Chore added.", "success")
        return redirect(url_for("shelter_operations.chore_management"))

    chores = db_fetchall(
        """
        SELECT id, name, when_time, default_day, description, active
        FROM chore_templates
        WHERE shelter = %s
        ORDER BY active DESC, sort_order ASC, name ASC
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

    if request.method == "POST":
        action = (request.form.get("action") or "").strip()

        if action in {"clone_week", "clone_week_random", "build_from_last_week"}:
            randomize_residents = action in {"clone_week_random", "build_from_last_week"}
            ok, category, message = _clone_previous_week(
                shelter=shelter,
                target_week_start=week_start,
                target_week_end=week_end,
                randomize_residents=randomize_residents,
            )
            flash(message, category)
            return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

        if not action:
            resident_id = (request.form.get("resident_id") or "").strip()
            chore_id = (request.form.get("chore_id") or "").strip()
            assign_mode = (request.form.get("assign_mode") or "day").strip()
            target_date = (request.form.get("target_date") or assigned_date).strip()

            if not resident_id or not chore_id:
                flash("Resident and chore are required.", "error")
                return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))

            if not target_date:
                target_date = assigned_date

            dates_to_insert = week_dates if assign_mode == "week" else [target_date]
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
        SELECT id, name, when_time, default_day
        FROM chore_templates
        WHERE shelter = %s AND active = 1
        ORDER BY sort_order ASC, name ASC
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
            ct.name AS chore_name,
            ct.when_time,
            ct.default_day
        FROM chore_assignments ca
        JOIN residents r ON r.id = ca.resident_id
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE r.shelter = %s
          AND ca.assigned_date BETWEEN %s AND %s
        ORDER BY
            r.last_name,
            r.first_name,
            ct.sort_order,
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
                "when_label": row["when_time"] or "",
                "default_day": row["default_day"] or "",
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

    week_start, week_end, _week_dates = _week_dates_from_anchor(assigned_date or target["assigned_date"])

    db_execute(
        """
        DELETE FROM chore_assignments ca
        USING residents r
        WHERE r.id = ca.resident_id
          AND r.shelter = %s
          AND ca.resident_id = %s
          AND ca.chore_id = %s
          AND ca.assigned_date BETWEEN %s AND %s
        """,
        (shelter, target["resident_id"], target["chore_id"], week_start, week_end),
    )

    flash("Weekly assignment deleted.", "success")
    return redirect(url_for("shelter_operations.chore_board", assigned_date=week_start))
