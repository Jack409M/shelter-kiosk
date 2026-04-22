from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall
from core.runtime import init_db

reports_prior_living = Blueprint("reports_prior_living", __name__)


@reports_prior_living.route("/staff/reports/prior-living")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def prior_living_report():
    init_db()

    rows = db_fetchall("""
        SELECT place_staying_before_entry AS label, COUNT(*) AS total
        FROM intake_assessments
        GROUP BY place_staying_before_entry
    """)

    return render_template(
        "reports/prior_living.html",
        rows=rows
    )
