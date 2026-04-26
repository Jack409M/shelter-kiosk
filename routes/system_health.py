from __future__ import annotations

from flask import Blueprint, redirect, url_for

from core.auth import require_login

system_health = Blueprint("system_health", __name__)


@system_health.get("/staff/system-health")
@require_login
def system_health_dashboard():
    return redirect(url_for("admin.admin_system_health"), code=302)
