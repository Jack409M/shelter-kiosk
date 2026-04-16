from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask import (
    Blueprint,
    current_app,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core.audit import log_action
from core.auth import can_manage_requests, require_login, require_shelter
from core.db import db_execute, db_fetchall
from core.helpers import fmt_dt, utcnow_iso

transport = Blueprint("transport", __name__)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def parse_dt(dt_str: str) -> datetime:
    return datetime.fromisoformat(dt_str)


def _can_manage_transport() -> bool:
    return can_manage_requests()


def _row_value(row: Any, key: str, index: int, default=None):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def _to_chicago(dt_str: str | None):
    if not dt_str:
        return None

    try:
        dt = datetime.fromisoformat(dt_str)
    except Exception:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)

    return dt.astimezone(CHICAGO_TZ)


def _local_day(dt_str: str | None) -> str | None:
    local_dt = _to_chicago(dt_str)
    if not local_dt:
        return None
    return local_dt.strftime("%Y-%m-%d")


def _cleanup_transport_requests(shelter: str) -> None:
    cutoff_iso = (datetime.utcnow() - timedelta(hours=48)).replace(microsecond=0).isoformat()

    db_execute(
        """
        DELETE FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND status = %s
          AND needed_at < %s
        """
        if g.get("db_kind") == "pg"
        else """
        DELETE FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND status = ?
          AND needed_at < ?
        """,
        (shelter, "pending", cutoff_iso),
    )

    db_execute(
        """
        DELETE FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND status = %s
          AND needed_at < %s
        """
        if g.get("db_kind") == "pg"
        else """
        DELETE FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND status = ?
          AND needed_at < ?
        """,
        (shelter, "scheduled", cutoff_iso),
    )


@transport.route("/staff/transport/pending")
@require_login
@require_shelter
def staff_transport_pending():
    if not _can_manage_transport():
        flash("You do not have permission to access that page.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = session["shelter"]
    _cleanup_transport_requests(shelter)

    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE status = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
        ORDER BY needed_at ASC, id ASC
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT *
        FROM transport_requests
        WHERE status = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
        ORDER BY needed_at ASC, id ASC
        """,
        ("pending", shelter),
    )

    return render_template(
        "staff_transport_pending.html",
        rows=rows,
        fmt_dt=fmt_dt,
    )


@transport.route("/staff/transport/board")
@require_login
@require_shelter
def staff_transport_board():
    shelter = session["shelter"]
    _cleanup_transport_requests(shelter)

    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND status IN (%s, %s)
        ORDER BY needed_at ASC, id ASC
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT *
        FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND status IN (?, ?)
        ORDER BY needed_at ASC, id ASC
        """,
        (shelter, "pending", "scheduled"),
    )

    day = (request.args.get("date") or "").strip()
    if day:
        filtered = []
        for r in rows:
            needed_at_val = _row_value(r, "needed_at", 5, "")
            if _local_day(needed_at_val) == day:
                filtered.append(r)
        rows = filtered

    return render_template(
        "staff_transport_board.html",
        rows=rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


@transport.route("/staff/transport/print")
@require_login
@require_shelter
def staff_transport_print():
    import html as _html

    shelter = session["shelter"]
    _cleanup_transport_requests(shelter)

    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND status IN (%s, %s)
        ORDER BY needed_at ASC, id ASC
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT *
        FROM transport_requests
        WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND status IN (?, ?)
        ORDER BY needed_at ASC, id ASC
        """,
        (shelter, "pending", "scheduled"),
    )

    day = (request.args.get("date") or "").strip()
    if not day:
        day = datetime.now(CHICAGO_TZ).strftime("%Y-%m-%d")

    filtered = []
    for r in rows:
        needed_at_val = _row_value(r, "needed_at", 5, "")
        if _local_day(needed_at_val) == day:
            filtered.append(r)

    rows = filtered

    def _cell(v):
        return _html.escape("" if v is None else str(v))

    trs = []
    for r in rows:
        needed_at_val = _row_value(r, "needed_at", 5)
        needed_at = fmt_dt(needed_at_val)
        first = _row_value(r, "first_name", 3, "")
        last = _row_value(r, "last_name", 4, "")
        pickup = _row_value(r, "pickup_location", 6, "")
        dest = _row_value(r, "destination", 7, "")
        status = _row_value(r, "status", 11, "")

        name = f"{last}, {first}"

        trs.append(
            "<tr>"
            f"<td>{_cell(needed_at)}</td>"
            f"<td>{_cell(name)}</td>"
            f"<td>{_cell(pickup)}</td>"
            f"<td>{_cell(dest)}</td>"
            f"<td>{_cell(status)}</td>"
            "</tr>"
        )

    table_rows = "\n".join(trs) if trs else '<tr><td colspan="5">No rides found.</td></tr>'

    html_doc = f"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <title>Transportation Sheet</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: Arial, sans-serif; margin: 16px; }}
    h1 {{ margin: 0 0 10px 0; font-size: 20px; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ border: 1px solid #999; padding: 8px; font-size: 12px; vertical-align: top; }}
    th {{ text-align: left; }}
    .toolbar {{ margin-bottom: 12px; display:flex; gap:10px; }}
    @media print {{
      .toolbar {{ display:none; }}
      body {{ margin: 0.5in; }}
    }}
  </style>
</head>
<body>
  <div class="toolbar">
    <button onclick="window.print()">Print</button>
    <button onclick="window.close()">Close</button>
  </div>

  <h1>Transportation Sheet, {_cell(shelter)} | {_cell(day)}</h1>

  <table>
    <thead>
      <tr>
        <th>Time</th>
        <th>Name</th>
        <th>Pickup</th>
        <th>Destination</th>
        <th>Status</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</body>
</html>
""".strip()

    return html_doc


@transport.route("/staff/transport/<int:req_id>/schedule", methods=["POST"])
@require_login
@require_shelter
def staff_transport_schedule(req_id: int):
    if not _can_manage_transport():
        flash("You do not have permission to access that page.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    shelter = session["shelter"]
    staff_id = session["staff_user_id"]

    _cleanup_transport_requests(shelter)

    staff_notes = (request.form.get("staff_notes") or "").strip()

    db_execute(
        """
        UPDATE transport_requests
        SET status = %s, scheduled_at = %s, scheduled_by = %s, staff_notes = %s
        WHERE id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND status = %s
        """
        if g.get("db_kind") == "pg"
        else """
        UPDATE transport_requests
        SET status = ?, scheduled_at = ?, scheduled_by = ?, staff_notes = ?
        WHERE id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND status = ?
        """,
        ("scheduled", utcnow_iso(), staff_id, staff_notes or None, req_id, shelter, "pending"),
    )

    log_action("transport", req_id, shelter, staff_id, "approve", "Transport request approved")
    flash("Approved.", "ok")
    return redirect(url_for("transport.staff_transport_pending"))
