from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchone
from core.runtime import init_db

reports_followup_outcomes = Blueprint("reports_followup_outcomes", __name__)


@reports_followup_outcomes.route("/staff/reports/follow-up-outcomes")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def followup_outcomes_report():
    init_db()

    six_month = db_fetchone(
        "SELECT COUNT(*) AS total FROM followups WHERE followup_type = '6_month'"
    )["total"]
    one_year = db_fetchone(
        "SELECT COUNT(*) AS total FROM followups WHERE followup_type = '1_year'"
    )["total"]

    return render_template(
        "reports/follow_up_outcomes.html", six_month=six_month, one_year=one_year
    )
