from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import Blueprint, g, redirect, render_template, session, url_for

from core.db import db_fetchall
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
def home():
    if not session.get("resident_id"):
        return redirect(url_for("resident_requests.resident_signin"))

    init_db()

    resident_id = session.get("resident_id")
    shelter = (session.get("resident_shelter") or "").strip()
    resident_identifier = (session.get("resident_identifier") or "").strip()
    now_local = datetime.now(ZoneInfo("America/Chicago"))

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
        else """
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
        else """
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

        status = (row.get("status") or "").strip().lower()
        pass_type = (row.get("pass_type") or "").strip().lower()

        is_active = False

        if status == "approved":
            if pass_type == "ordinary" and row["start_at_local"] and row["end_at_local"]:
                is_active = row["start_at_local"] <= now_local <= row["end_at_local"]
            elif pass_type == "extended_special" and row.get("start_date") and row.get("end_date"):
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
            item.get("created_at") or "",
        )
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

    return render_template(
        "resident_home.html",
        pass_items=processed_pass_items,
        transport_items=processed_transport_items,
        active_pass=active_pass,
    )
