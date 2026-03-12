from __future__ import annotations

from flask import Blueprint, render_template
from core.auth import require_login
from core.db import db_fetchall

compliance = Blueprint("compliance", __name__, url_prefix="/staff/compliance")


@compliance.route("")
@require_login
def compliance_dashboard():

    rows = db_fetchall(
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            wrs.productive_hours,
            wrs.work_hours,
            wrs.meeting_count
        FROM residents r
        LEFT JOIN program_enrollments pe
            ON pe.resident_id = r.id
        LEFT JOIN weekly_resident_summary wrs
            ON wrs.enrollment_id = pe.id
        WHERE pe.status = 'active'
        ORDER BY r.last_name ASC
        """
    )

    results = []

    for row in rows:

        if isinstance(row, dict):
            productive = row.get("productive_hours") or 0
            meetings = row.get("meeting_count") or 0
        else:
            productive = row[3] or 0
            meetings = row[5] or 0

        status = "missing"

        if productive >= 35 and meetings >= 3:
            status = "compliant"
        elif productive > 0:
            status = "attention"

        results.append((row, status))

    return render_template(
        "compliance/dashboard.html",
        rows=results
    )
