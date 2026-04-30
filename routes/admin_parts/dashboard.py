from __future__ import annotations

from datetime import UTC, datetime, timedelta

from flask import (
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from core import rate_limit as rate_limit_store
from core.admin_dashboard_payload import build_admin_dashboard_payload as _build_admin_dashboard_payload
from core.admin_rbac import current_role as _current_role
from core.admin_rbac import require_admin_role as _require_admin
from core.audit import log_action
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_dt, utcnow_iso
from core.rate_limit import ban_ip

AUTO_RESET_HOURS = 8
MANUAL_IP_BAN_SECONDS = 3600

SECURITY_FIELD_META = {
    "sms_system_enabled": {
        "expires_field": "sms_system_expires_at",
        "default": True,
    },
    "kiosk_intake_enabled": {
        "expires_field": "kiosk_intake_expires_at",
        "default": True,
    },
    "admin_login_only_mode": {
        "expires_field": "admin_login_only_expires_at",
        "default": False,
    },
    "security_alerts_enabled": {
        "expires_field": "security_alerts_expires_at",
        "default": True,
    },
}


def _temporary_expiration_iso() -> str:
    return (datetime.now(UTC) + timedelta(hours=AUTO_RESET_HOURS)).isoformat()


def _manual_unban_ip(ip: str) -> bool:
    ip = (ip or "").strip()
    if not ip:
        return False

    removed = ip in rate_limit_store._BANNED_IPS
    rate_limit_store._BANNED_IPS.pop(ip, None)
    return removed


def _manual_unlock_username(username: str) -> bool:
    username = (username or "").strip().lower()
    if not username:
        return False

    key = f"staff_login_username_lock:{username}"
    removed = key in rate_limit_store._LOCKED_KEYS
    rate_limit_store._LOCKED_KEYS.pop(key, None)
    return removed


def _security_setting_bool(raw_value) -> bool:
    if isinstance(raw_value, bool):
        return raw_value

    if isinstance(raw_value, int):
        return raw_value == 1

    normalized = str(raw_value or "").strip().lower()
    return normalized in {"1", "true", "t", "yes", "y", "on"}


def _security_setting_value_for_db(bool_value: bool, kind: str):
    if kind == "pg":
        return bool_value

    return 1 if bool_value else 0


def _security_setting_value_for_history(bool_value: bool) -> str:
    return "1" if bool_value else "0"


def admin_dashboard_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    payload = _build_admin_dashboard_payload(send_alerts=True)

    return render_template(
        "admin_dashboard.html",
        total_users=payload["total_users"],
        active_users=payload["active_users"],
        recent_audit=payload["recent_audit"],
        failed_login_count=payload["failed_login_count"],
        recent_failed_logins=payload["recent_failed_logins"],
        top_attacking_ips=payload["top_attacking_ips"],
        targeted_usernames=payload["targeted_usernames"],
        top_threats=payload["top_threats"],
        top_threat_score=payload["top_threat_score"],
        attack_map_points=payload["attack_map_points"],
        banned_ips=payload["banned_ips"],
        locked_usernames=payload["locked_usernames"],
        rate_limit_activity=payload["rate_limit_activity"],
        kiosk_security_events=payload["kiosk_security_events"],
        recent_staff_sessions=payload["recent_staff_sessions"],
        recent_security_incidents=payload["recent_security_incidents"],
        security_settings=payload["settings"],
        dashboard_live_url=url_for("admin.admin_dashboard_live"),
        fmt_dt=fmt_dt,
        current_role=_current_role(),
    )


def admin_dashboard_live_view():
    if not _require_admin():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = _build_admin_dashboard_payload(send_alerts=True, include_static=False)
    live_payload = payload["live_payload"]
    live_payload["ok"] = True

    return jsonify(live_payload)

# rest of file unchanged
