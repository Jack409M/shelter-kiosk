from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.db import db_execute, db_fetchall
from core.helpers import utcnow_iso
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import pass_type_label
from core.runtime import init_db


resident_portal = Blueprint(
    "resident_portal",
    __name__,
    url_prefix="/resident",
)


def _to_local(dt_iso):
    if not dt_iso:
        return None
    try:
        dt = datetime.fromisoformat(dt_iso).replace(tzinfo=timezone.utc)
        return dt.astimezone(ZoneInfo("America/Chicago"))
    except Exception:
        return None


def _status_rank(status: str) -> int:
    order = {
        "approved": 0,
        "pending": 1,
        "denied": 2,
        "completed": 3,
    }
    return order.get((status or "").strip().lower(), 9)


@resident_portal.route("/home")
@require_resident
def home():
    init_db()

    resident_id = session.get("resident_id")
    shelter = (session.get("resident_shelter") or "").strip()
    resident_identifier = (session.get("resident_identifier") or "").strip()
    now_local = datetime.now(ZoneInfo("America/Chicago"))

    run_pass_retention_cleanup_for_shelter(shelter)

    pass_items = db_fetchall(
        """
        SELECT
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            created_at
        FROM resident_passes
        WHERE resident_id = %s
          AND shelter = %s
        ORDER BY created_at DESC
        LIMIT 10
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            pass_type,
            status,
            start_at,
            end_at,
            start_date,
            end_date,
            destination,
            created_at
        FROM resident_passes
        WHERE resident_id = ?
          AND shelter = ?
        ORDER BY created_at DESC
        LIMIT 10
        """,
        (resident_id, shelter),
    )

    notification_items = db_fetchall(
        """
        SELECT
            id,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        FROM resident_notifications
        WHERE resident_id = %s
          AND shelter = %s
        ORDER BY is_read ASC, created_at DESC
        LIMIT 10
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            id,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        FROM resident_notifications
        WHERE resident_id = ?
          AND shelter = ?
        ORDER BY is_read ASC, created_at DESC
        LIMIT 10
        """,
        (resident_id, shelter),
    )

    transport_items = db_fetchall(
        """
        SELECT
            status,
            needed_at,
            destination,
            submitted_at
        FROM transport_requests
        WHERE resident_identifier = %s
          AND shelter = %s
        ORDER BY submitted_at DESC
        LIMIT 10
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            status,
            needed_at,
            destination,
            submitted_at
        FROM transport_requests
        WHERE resident_identifier = ?
          AND shelter = ?
        ORDER BY submitted_at DESC
        LIMIT 10
        """,
        (resident_identifier, shelter),
    )

    processed_pass_items = []
    active_pass = None

    for r in pass_items:
        row = dict(r) if isinstance(r, dict) else {
            "pass_type": r[0],
            "status": r[1],
            "start_at": r[2],
            "end_at": r[3],
            "start_date": r[4],
            "end_date": r[5],
            "destination": r[6],
            "created_at": r[7],
        }

        row["start_at_local"] = _to_local(row.get("start_at"))
        row["end_at_local"] = _to_local(row.get("end_at"))
        row["created_at_local"] = _to_local(row.get("created_at"))
        row["pass_type_label"] = pass_type_label(row.get("pass_type"))

        status = (row.get("status") or "").strip().lower()
        pass_type = (row.get("pass_type") or "").strip().lower()

        is_active = False

        if status == "approved":
            if pass_type in {"pass", "overnight"} and row["start_at_local"] and row["end_at_local"]:
                is_active = row["start_at_local"] <= now_local <= row["end_at_local"]
            elif pass_type == "special" and row.get("start_date") and row.get("end_date"):
                try:
                    start_date = datetime.strptime(row["start_date"], "%Y-%m-%d").date()
                    end_date = datetime.strptime(row["end_date"], "%Y-%m-%d").date()
                    today = now_local.date()
                    is_active = start_date <= today <= end_date
                except Exception:
                    is_active = False

        row["is_active"] = is_active

        if is_active and active_pass is None:
            active_pass = row

        processed_pass_items.append(row)

    processed_pass_items.sort(
        key=lambda item: (
            0 if item.get("is_active") else 1,
            _status_rank(item.get("status", "")),
            -item["created_at_local"].timestamp() if item.get("created_at_local") else float("inf"),
        )
    )

    processed_notification_items = []
    unread_notification_ids: list[int] = []

    for r in notification_items:
        row = dict(r) if isinstance(r, dict) else {
            "id": r[0],
            "notification_type": r[1],
            "title": r[2],
            "message": r[3],
            "related_pass_id": r[4],
            "is_read": r[5],
            "created_at": r[6],
            "read_at": r[7],
        }

        row["created_at_local"] = _to_local(row.get("created_at"))
        row["read_at_local"] = _to_local(row.get("read_at"))
        row["is_unread"] = not bool(row.get("is_read"))

        if row["is_unread"]:
            unread_notification_ids.append(int(row["id"]))

        processed_notification_items.append(row)

    if unread_notification_ids:
        db_execute(
            """
            UPDATE resident_notifications
            SET is_read = 1,
                read_at = %s
            WHERE resident_id = %s
              AND shelter = %s
              AND id = ANY(%s)
            """
            if g.get("db_kind") == "pg"
            else
            """
            UPDATE resident_notifications
            SET is_read = 1,
                read_at = ?
            WHERE resident_id = ?
              AND shelter = ?
              AND id IN ({})
            """.format(",".join("?" for _ in unread_notification_ids)),
            (
                (utcnow_iso(), resident_id, shelter, unread_notification_ids)
                if g.get("db_kind") == "pg"
                else (utcnow_iso(), resident_id, shelter, *unread_notification_ids)
            ),
        )

    processed_transport_items = []
    for r in transport_items:
        row = dict(r) if isinstance(r, dict) else {
            "status": r[0],
            "needed_at": r[1],
            "destination": r[2],
            "submitted_at": r[3],
        }

        row["needed_at_local"] = _to_local(row.get("needed_at"))
        row["submitted_at_local"] = _to_local(row.get("submitted_at"))

        processed_transport_items.append(row)

    today = str(now_local.date())

    chores = db_fetchall(
        """
        SELECT
            ca.id,
            ca.status,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE ca.resident_id = %s
          AND ca.assigned_date = %s
        ORDER BY ct.name
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            ca.id,
            ca.status,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE ca.resident_id = ?
          AND ca.assigned_date = ?
        ORDER BY ct.name
        """,
        (resident_id, today),
    )

    return render_template(
        "resident_home.html",
        pass_items=processed_pass_items,
        notification_items=processed_notification_items,
        transport_items=processed_transport_items,
        active_pass=active_pass,
        chores=chores,
    )


@resident_portal.route("/chores", methods=["GET", "POST"])
@require_resident
def resident_chores():
    init_db()

    resident_id = session.get("resident_id")
    today = str(date.today())

    if request.method == "POST":
        assignment_id = (request.form.get("assignment_id") or "").strip()

        if assignment_id:
            existing = db_fetchall(
                """
                SELECT status
                FROM chore_assignments
                WHERE id = %s AND resident_id = %s
                """
                if g.get("db_kind") == "pg"
                else
                """
                SELECT status
                FROM chore_assignments
                WHERE id = ? AND resident_id = ?
                """,
                (assignment_id, resident_id),
            )

            current_status = None
            if existing:
                current_status = existing[0]["status"] if isinstance(existing[0], dict) else existing[0][0]

            if current_status != "completed":
                db_execute(
                    """
                    UPDATE chore_assignments
                    SET status = 'completed', updated_at = %s
                    WHERE id = %s AND resident_id = %s
                    """
                    if g.get("db_kind") == "pg"
                    else
                    """
                    UPDATE chore_assignments
                    SET status = 'completed', updated_at = ?
                    WHERE id = ? AND resident_id = ?
                    """,
                    (utcnow_iso(), assignment_id, resident_id),
                )

                flash("Chore marked complete.", "success")
            else:
                flash("Chore already completed.", "info")

        return redirect(url_for("resident_portal.resident_chores"))

    chores = db_fetchall(
        """
        SELECT
            ca.id,
            ca.status,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE ca.resident_id = %s
          AND ca.assigned_date = %s
        ORDER BY ct.name
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            ca.id,
            ca.status,
            ct.name AS chore_name
        FROM chore_assignments ca
        JOIN chore_templates ct ON ct.id = ca.chore_id
        WHERE ca.resident_id = ?
          AND ca.assigned_date = ?
        ORDER BY ct.name
        """,
        (resident_id, today),
    )

    return render_template(
        "resident/chores.html",
        chores=chores,
        today=today,
    )
