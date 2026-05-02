from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter
from routes.admin_parts.job_monitor import job_monitor_view

job_monitor = Blueprint("job_monitor", __name__)


@job_monitor.route("/staff/admin/system-health/job-monitor", methods=["GET"])
@require_login
@require_shelter
def admin_job_monitor():
    return job_monitor_view()
