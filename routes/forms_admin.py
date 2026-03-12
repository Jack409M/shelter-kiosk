from __future__ import annotations

from flask import Blueprint, g, render_template

from core.auth import require_login
from core.db import db_fetchall

forms_admin = Blueprint("forms_admin", __name__, url_prefix="/staff/forms")


@forms_admin.route("")
@require_login
def forms_index():
    rows = db_fetchall(
        """
        SELECT
            rfs.id,
            rfs.form_type,
            rfs.form_source,
            rfs.submitted_at,
            rfs.created_at,
            r.first_name,
            r.last_name,
            wrs.productive_hours,
            wrs.work_hours,
            wrs.meeting_count
        FROM resident_form_submissions rfs
        LEFT JOIN residents r
            ON r.id = rfs.resident_id
        LEFT JOIN weekly_resident_summary wrs
            ON wrs.submission_id = rfs.id
        ORDER BY rfs.created_at DESC
        LIMIT 100
        """
    )

    return render_template("forms_admin/index.html", rows=rows)
