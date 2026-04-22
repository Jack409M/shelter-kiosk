from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchone
from core.runtime import init_db

reports_sobriety_progress = Blueprint("reports_sobriety_progress", __name__)


@reports_sobriety_progress.route("/staff/reports/sobriety-progress")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def sobriety_progress_report():
    init_db()

    entry_avg = db_fetchone("SELECT AVG(COALESCE(days_sober_at_entry, 0)) AS val FROM intake_assessments")["val"]
    followup_avg = db_fetchone("SELECT AVG(COALESCE(sober_at_followup, 0)) AS val FROM followups")["val"]

    return render_template(
        "reports/sobriety_progress.html",
        entry_avg=entry_avg,
        followup_avg=followup_avg
    )
