from flask import Blueprint, render_template

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall, db_fetchone
from core.runtime import init_db

reports_intake_profile = Blueprint("reports_intake_profile", __name__)


@reports_intake_profile.route("/staff/reports/intake-profile")
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def intake_profile_report():
    init_db()

    summary = (
        db_fetchone(
            """
        SELECT
            COUNT(*) AS total,
            AVG(COALESCE(income_at_entry, 0)) AS avg_income_at_entry,
            AVG(COALESCE(days_sober_at_entry, 0)) AS avg_days_sober_at_entry,
            AVG(COALESCE(ace_score, 0)) AS avg_ace_score,
            AVG(COALESCE(grit_score, 0)) AS avg_grit_score
        FROM intake_assessments
        """
        )
        or {}
    )

    education_rows = (
        db_fetchall(
            """
        SELECT COALESCE(education_at_entry, 'Unknown') AS label, COUNT(*) AS total
        FROM intake_assessments
        GROUP BY COALESCE(education_at_entry, 'Unknown')
        ORDER BY total DESC, label ASC
        """
        )
        or []
    )

    employment_rows = (
        db_fetchall(
            """
        SELECT COALESCE(employment_status_at_entry, 'Unknown') AS label, COUNT(*) AS total
        FROM intake_assessments
        GROUP BY COALESCE(employment_status_at_entry, 'Unknown')
        ORDER BY total DESC, label ASC
        """
        )
        or []
    )

    need_rows = (
        db_fetchall(
            """
        SELECT 'Mental Health Need' AS label, SUM(CASE WHEN COALESCE(mental_health_need_at_entry, 0) = 1 THEN 1 ELSE 0 END) AS total FROM intake_assessments
        UNION ALL
        SELECT 'Medical Need' AS label, SUM(CASE WHEN COALESCE(medical_need_at_entry, 0) = 1 THEN 1 ELSE 0 END) AS total FROM intake_assessments
        UNION ALL
        SELECT 'Substance Use Need' AS label, SUM(CASE WHEN COALESCE(substance_use_need_at_entry, 0) = 1 THEN 1 ELSE 0 END) AS total FROM intake_assessments
        UNION ALL
        SELECT 'Dental Need' AS label, SUM(CASE WHEN COALESCE(dental_need_at_entry, 0) = 1 THEN 1 ELSE 0 END) AS total FROM intake_assessments
        UNION ALL
        SELECT 'Vision Need' AS label, SUM(CASE WHEN COALESCE(vision_need_at_entry, 0) = 1 THEN 1 ELSE 0 END) AS total FROM intake_assessments
        """
        )
        or []
    )

    return render_template(
        "reports/intake_profile.html",
        summary=summary,
        education_rows=education_rows,
        employment_rows=employment_rows,
        need_rows=need_rows,
    )
