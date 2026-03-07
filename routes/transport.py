from flask import Blueprint, render_template, session, request, redirect, url_for, flash, current_app
from datetime import datetime
from core.auth import require_login, require_shelter
from core.helpers import fmt_dt
from core.db import db_fetchall, db_execute
from core.audit import log_action
from flask import g

transport = Blueprint("transport", __name__)


def parse_dt(dt_str):
    from datetime import datetime
    return datetime.fromisoformat(dt_str)


@transport.route("/staff/transport/pending")
@require_login
@require_shelter
def staff_transport_pending():
    shelter = session["shelter"]

    rows = db_fetchall(
        "SELECT * FROM transport_requests WHERE status = %s AND shelter = %s ORDER BY id DESC"
        if current_app.config.get("DATABASE_URL")
        else "SELECT * FROM transport_requests WHERE status = ? AND shelter = ? ORDER BY id DESC",
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

    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE shelter = %s
          AND status IN (%s, %s)
        ORDER BY needed_at ASC
        """
        if current_app.config.get("DATABASE_URL")
        else """
        SELECT *
        FROM transport_requests
        WHERE shelter = ?
          AND status IN (?, ?)
        ORDER BY needed_at ASC
        """,
        (shelter, "pending", "scheduled"),
    )

    day = (request.args.get("date") or "").strip()
    if day:
        filtered = []
        for r in rows:
            try:
                needed_at_val = r.get("needed_at") if isinstance(r, dict) else r["needed_at"]
                dt = parse_dt(needed_at_val)
                if dt.strftime("%Y-%m-%d") == day:
                    filtered.append(r)
            except Exception:
                pass
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
    rows = db_fetchall(
        """
        SELECT *
        FROM transport_requests
        WHERE shelter = %s
          AND status IN (%s, %s)
        ORDER BY needed_at ASC
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT *
        FROM transport_requests
        WHERE shelter = ?
          AND status IN (?, ?)
        ORDER BY needed_at ASC
        """,
        (shelter, "pending", "scheduled"),
    )

    day = (request.args.get("date") or "").strip()
    if not day:
        day = datetime.utcnow().strftime("%Y-%m-%d")

    filtered = []
    for r in rows:
        try:
            needed_at_val = r.get("needed_at") if isinstance(r, dict) else r["needed_at"]
            dt = parse_dt(needed_at_val)
            if dt.strftime("%Y-%m-%d") == day:
                filtered.append(r)
        except Exception:
            pass

    rows = filtered

    def _cell(v):
        return _html.escape("" if v is None else str(v))

    trs = []
    for r in rows:
        needed_at_val = r.get("needed_at") if isinstance(r, dict) else r["needed_at"]
        needed_at = fmt_dt(needed_at_val)
        first = r.get("first_name") if isinstance(r, dict) else r["first_name"]
        last = r.get("last_name") if isinstance(r, dict) else r["last_name"]
        pickup = r.get("pickup_location") if isinstance(r, dict) else r["pickup_location"]
        dest = r.get("destination") if isinstance(r, dict) else r["destination"]
        status = r.get("status") if isinstance(r, dict) else r["status"]

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
