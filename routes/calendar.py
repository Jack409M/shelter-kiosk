from __future__ import annotations

from datetime import date

from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso
from core.runtime import init_db

calendar_bp = Blueprint(
    "calendar",
    __name__,
    url_prefix="/staff/calendar",
)


VALID_SHELTERS = {"abba", "haven", "gratitude"}


def _require_calendar_access() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager", "staff"}


def _ph() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _clean_shelter(value: str | None) -> str | None:
    cleaned = (value or "").strip().lower()
    if not cleaned:
        return None
    if cleaned in VALID_SHELTERS:
        return cleaned
    return None


@calendar_bp.route("/", methods=["GET"])
@require_login
def calendar_view():
    if not _require_calendar_access():
        flash("Not allowed.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    month = (request.args.get("month") or "").strip()
    if not month:
        today = date.today()
        month = f"{today.year}-{str(today.month).zfill(2)}"

    return render_template(
        "calendar.html",
        month=month,
    )


@calendar_bp.route("/events", methods=["GET"])
@require_login
def calendar_events():
    if not _require_calendar_access():
        return jsonify([])

    init_db()

    month = (request.args.get("month") or "").strip()
    shelter = _clean_shelter(request.args.get("shelter"))

    where_clauses: list[str] = []
    params: list[object] = []

    if month:
        where_clauses.append(f"e.event_date LIKE {_ph()}")
        params.append(f"{month}%")

    if shelter:
        where_clauses.append(f"LOWER(COALESCE(e.shelter, '')) = {_ph()}")
        params.append(shelter)

    where_sql = ""
    if where_clauses:
        where_sql = "WHERE " + " AND ".join(where_clauses)

    rows = db_fetchall(
        f"""
        SELECT
            e.id,
            e.title,
            e.event_date,
            e.start_time,
            e.end_time,
            e.shelter,
            e.staff_user_id,
            e.notes,
            e.created_by,
            e.created_at,
            e.updated_at,
            u.first_name,
            u.last_name,
            u.calendar_color
        FROM case_manager_calendar_events e
        LEFT JOIN staff_users u ON u.id = e.staff_user_id
        {where_sql}
        ORDER BY e.event_date ASC, e.start_time ASC, e.id ASC
        """,
        tuple(params),
    )

    events: list[dict[str, object]] = []

    for row in rows:
        event_date = str(row["event_date"])
        start_time = (row["start_time"] or "").strip() if row["start_time"] else ""
        end_time = (row["end_time"] or "").strip() if row["end_time"] else ""

        start_value = event_date
        end_value = None

        if start_time:
            start_value = f"{event_date}T{start_time}"

        if end_time:
            end_value = f"{event_date}T{end_time}"

        first_name = (row["first_name"] or "").strip()
        last_name = (row["last_name"] or "").strip()
        staff_name = f"{first_name} {last_name}".strip()

        event_payload: dict[str, object] = {
            "id": row["id"],
            "title": row["title"],
            "start": start_value,
            "color": row["calendar_color"] or "#3788d8",
            "extendedProps": {
                "event_id": row["id"],
                "shelter": row["shelter"],
                "staff_user_id": row["staff_user_id"],
                "staff_name": staff_name,
                "notes": row["notes"] or "",
            },
        }

        if end_value:
            event_payload["end"] = end_value
        else:
            event_payload["allDay"] = True

        events.append(event_payload)

    return jsonify(events)


@calendar_bp.route("/add", methods=["GET", "POST"])
@require_login
def add_event():
    if not _require_calendar_access():
        flash("Not allowed.", "error")
        return redirect(url_for("calendar.calendar_view"))

    init_db()

    if request.method == "GET":
        event_date = (request.args.get("event_date") or "").strip()
        return render_template(
            "calendar_add.html",
            event_date=event_date,
        )

    title = (request.form.get("title") or "").strip()
    event_date = (request.form.get("event_date") or "").strip()
    start_time = (request.form.get("start_time") or "").strip()
    end_time = (request.form.get("end_time") or "").strip()
    shelter = _clean_shelter(request.form.get("shelter"))
    notes = (request.form.get("notes") or "").strip()

    staff_user_id = session.get("staff_user_id")

    if not title or not event_date:
        flash("Title and date required.", "error")
        return redirect(url_for("calendar.add_event", event_date=event_date))

    now = utcnow_iso()

    db_execute(
        f"""
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
        VALUES ({_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()}, {_ph()})
        """,
        (
            title,
            event_date,
            start_time or None,
            end_time or None,
            shelter,
            staff_user_id,
            notes or None,
            staff_user_id,
            now,
            now,
        ),
    )

    log_action(
        "calendar_event",
        None,
        shelter,
        staff_user_id,
        "create",
        details={
            "event_date": event_date,
            "has_end_time": bool(end_time),
            "has_start_time": bool(start_time),
            "title": title,
        },
    )

    flash("Event added.", "ok")
    return redirect(url_for("calendar.calendar_view", month=event_date[:7]))


@calendar_bp.route("/edit/<int:event_id>", methods=["GET", "POST"])
@require_login
def edit_event(event_id: int):
    if not _require_calendar_access():
        flash("Not allowed.", "error")
        return redirect(url_for("calendar.calendar_view"))

    init_db()

    event = db_fetchone(
        f"""
        SELECT
            id,
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
        FROM case_manager_calendar_events
        WHERE id = {_ph()}
        """,
        (event_id,),
    )

    if not event:
        flash("Event not found.", "error")
        return redirect(url_for("calendar.calendar_view"))

    if request.method == "GET":
        return render_template(
            "calendar_edit.html",
            event=event,
        )

    title = (request.form.get("title") or "").strip()
    event_date = (request.form.get("event_date") or "").strip()
    start_time = (request.form.get("start_time") or "").strip()
    end_time = (request.form.get("end_time") or "").strip()
    shelter = _clean_shelter(request.form.get("shelter"))
    notes = (request.form.get("notes") or "").strip()

    if not title or not event_date:
        flash("Title and date required.", "error")
        return redirect(url_for("calendar.edit_event", event_id=event_id))

    now = utcnow_iso()

    db_execute(
        f"""
        UPDATE case_manager_calendar_events
        SET
            title = {_ph()},
            event_date = {_ph()},
            start_time = {_ph()},
            end_time = {_ph()},
            shelter = {_ph()},
            notes = {_ph()},
            updated_at = {_ph()}
        WHERE id = {_ph()}
        """,
        (
            title,
            event_date,
            start_time or None,
            end_time or None,
            shelter,
            notes or None,
            now,
            event_id,
        ),
    )

    log_action(
        "calendar_event",
        event_id,
        shelter,
        session.get("staff_user_id"),
        "update",
        details={
            "event_date": event_date,
            "has_end_time": bool(end_time),
            "has_start_time": bool(start_time),
            "title": title,
        },
    )

    flash("Event updated.", "ok")
    return redirect(url_for("calendar.calendar_view", month=event_date[:7]))
