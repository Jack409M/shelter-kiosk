from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchone
from core.runtime import init_db

reports_program_flow = Blueprint("reports_program_flow", __name__)


@reports_program_flow.route("/staff/reports/program-flow")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def program_flow_report():
    init_db()

    total_entries = db_fetchone("SELECT COUNT(*) AS total FROM program_enrollments")["total"]
    total_exits = db_fetchone("SELECT COUNT(*) AS total FROM program_enrollments WHERE exit_date IS NOT NULL AND exit_date <> ''")["total"]

    return render_template(
        "reports/program_flow.html",
        total_entries=total_entries,
        total_exits=total_exits
    )
