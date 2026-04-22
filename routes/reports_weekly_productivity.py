from __future__ import annotations

from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchone
from core.runtime import init_db

reports_weekly_productivity = Blueprint("reports_weekly_productivity", __name__)

@reports_weekly_productivity.route("/staff/reports/weekly-productivity")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager")
def weekly_productivity_report():
    init_db()

    total_hours = db_fetchone("SELECT COALESCE(SUM(hours),0) FROM attendance_events")

    return render_template(
        "reports/weekly_productivity.html",
        title="Weekly Productivity Report",
        total_hours=(total_hours[0] if total_hours else 0),
    )
