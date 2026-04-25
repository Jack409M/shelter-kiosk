from __future__ import annotations

from flask import Blueprint, render_template
from core.auth import require_login, require_roles
from core.db import db_fetchone
import os
import datetime

system_health = Blueprint("system_health", __name__)


@system_health.get("/staff/system-health")
@require_login
@require_roles("admin", "director")
def system_health_dashboard():
    db_status = "unknown"

    try:
        row = db_fetchone("SELECT 1 as ok")
        db_status = "online" if row else "error"
    except Exception:
        db_status = "error"

    app_version = os.getenv("APP_VERSION", "unknown")

    now = datetime.datetime.now()

    return render_template(
        "system_health/dashboard.html",
        db_status=db_status,
        app_version=app_version,
        current_time=now,
    )
