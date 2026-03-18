from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login
from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from core.runtime import init_db


calendar_bp = Blueprint(
    "calendar",
    __name__,
    url_prefix="/staff/calendar",
)


def _require_calendar_access() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager", "staff"}


@calendar_bp.route("/", methods=["GET"])
@require_login
def calendar_view():
    if not _require_calendar_access():
        flash("Not allowed.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    # month filter (YYYY-MM)
    month = request.args.get("month")
    if not month:
        today = date.today()
        month = f"{today.year}-{str(today.month).zfill(2)}"

    events = db_fetchall(
        """
        SELECT
            e.*,
            u.first_name,
            u.last_name,
            u.calendar_color
        FROM case_manager_calendar_events e
        LEFT JOIN staff_users u ON u.id = e.staff_user_id
        WHERE e.event_date LIKE ?
        ORDER BY e.event_date ASC, e.start_time ASC
        """,
        (f"{month}%",),
    )

    return render_template(
        "calendar.html",
        events=events,
        month=month,
    )


@calendar_bp.route("/add", methods=["POST"])
@require_login
def add_event():
    if not _require_calendar_access():
        flash("Not allowed.", "error")
        return redirect(url_for("calendar.calendar_view"))

    init_db()

    title = (request.form.get("title") or "").strip()
    event_date = (request.form.get("event_date") or "").strip()
    start_time = (request.form.get("start_time") or "").strip()
    end_time = (request.form.get("end_time") or "").strip()
    shelter = (request.form.get("shelter") or "").strip().lower()
    notes = (request.form.get("notes") or "").strip()

    staff_user_id = session.get("staff_user_id")

    if not title or not event_date:
        flash("Title and date required.", "error")
        return redirect(url_for("calendar.calendar_view"))

    now = utcnow_iso()

    db_execute(
        """
        INSERT INTO case_manager_calendar_events (
            title,
            event_date,
            start_time,
            end_time,
            shelter,
            staff_user_id,
            notes,
            created_by,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            title,
            event_date,
            start_time or None,
            end_time or None,
            shelter or None,
            staff_user_id,
            notes or None,
            staff_user_id,
            now,
            now,
        ),
    )

    flash("Event added.", "ok")
    return redirect(url_for("calendar.calendar_view"))
