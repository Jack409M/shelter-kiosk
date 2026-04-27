from __future__ import annotations

from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall
from core.runtime import init_db

reports_weekly_productivity = Blueprint("reports_weekly_productivity", __name__)


@reports_weekly_productivity.route("/staff/reports/weekly-productivity")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def weekly_productivity_report():
    init_db()

    rows = (
        db_fetchall(
            """
        SELECT
            r.id AS resident_id,
            COALESCE(NULLIF(TRIM(r.first_name || ' ' || r.last_name), ''), 'Unknown') AS resident_name,
            COALESCE(SUM(COALESCE(ae.logged_hours, 0)), 0) AS total_hours
        FROM attendance_events ae
        JOIN residents r
          ON r.id = ae.resident_id
        GROUP BY r.id, resident_name
        ORDER BY total_hours DESC, resident_name ASC
        """
        )
        or []
    )

    normalized_rows = [dict(row) for row in rows]
    total_hours = round(sum(float(row.get("total_hours") or 0) for row in normalized_rows), 2)

    return render_template(
        "reports/weekly_productivity.html",
        title="Weekly Productivity Report",
        rows=normalized_rows,
        total_hours=total_hours,
    )
