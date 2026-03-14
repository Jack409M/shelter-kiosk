from __future__ import annotations

from datetime import datetime, timedelta, timezone

from flask import (
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
    g,
)

from core import rate_limit as rate_limit_store
from core.audit import log_action
from core.db import db_execute
from core.helpers import fmt_dt, utcnow_iso
from core.rate_limit import ban_ip

from routes.admin_parts.helpers import (
    build_admin_dashboard_payload as _build_admin_dashboard_payload,
    current_role as _current_role,
    require_admin_role as _require_admin,
)


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
    return (datetime.now(timezone.utc) + timedelta(hours=AUTO_RESET_HOURS)).isoformat()


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


def admin_update_security_settings_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    field = (request.form.get("field") or "").strip()
    value = (request.form.get("value") or "").strip()

    if field not in SECURITY_FIELD_META:
        flash("Invalid security setting.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    if value not in {"0", "1"}:
        flash("Invalid security setting value.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    bool_value = value == "1"
    kind = g.get("db_kind")
    now = utcnow_iso()

    meta = SECURITY_FIELD_META[field]
    expires_field = meta["expires_field"]
    default_value = bool(meta["default"])

    expires_at = None
    if bool_value != default_value:
        expires_at = _temporary_expiration_iso()

    db_execute(
        f"""
        UPDATE security_settings
        SET {field} = {("%s" if kind == "pg" else "?")},
            {expires_field} = {("%s" if kind == "pg" else "?")},
            updated_at = {("%s" if kind == "pg" else "?")}
        WHERE id = (SELECT id FROM security_settings ORDER BY id ASC LIMIT 1)
        """,
        (
            bool_value if kind == "pg" else (1 if bool_value else 0),
            expires_at,
            now,
        ),
    )

    log_action(
        "security_settings",
        None,
        None,
        session.get("staff_user_id"),
        "security_setting_updated",
        f"field={field}\nvalue={value}\nauto_reset_hours={AUTO_RESET_HOURS}\nexpires_at={expires_at or 'none'}",
    )

    if expires_at:
        flash(f"Security setting updated. Auto reset scheduled in {AUTO_RESET_HOURS} hours.", "ok")
    else:
        flash("Security setting updated.", "ok")

    return redirect(url_for("admin.admin_dashboard"))


def admin_ban_ip_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    ip = (request.form.get("ip") or "").strip()

    if not ip:
        flash("IP address is required.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    ban_ip(ip, MANUAL_IP_BAN_SECONDS)

    log_action(
        "security",
        None,
        None,
        session.get("staff_user_id"),
        "manual_ip_ban",
        f"ip={ip}\nseconds={MANUAL_IP_BAN_SECONDS}",
    )

    flash("IP banned.", "ok")
    return redirect(url_for("admin.admin_dashboard"))


def admin_unban_ip_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    ip = (request.form.get("ip") or "").strip()

    if not ip:
        flash("IP address is required.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    removed = _manual_unban_ip(ip)

    log_action(
        "security",
        None,
        None,
        session.get("staff_user_id"),
        "manual_ip_unban",
        f"ip={ip}\nremoved={'yes' if removed else 'no'}",
    )

    if removed:
        flash("IP unbanned.", "ok")
    else:
        flash("IP was not currently banned.", "error")

    return redirect(url_for("admin.admin_dashboard"))


def admin_unlock_username_view():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    username = (request.form.get("username") or "").strip()

    if not username:
        flash("Username is required.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    removed = _manual_unlock_username(username)

    log_action(
        "security",
        None,
        None,
        session.get("staff_user_id"),
        "manual_username_unlock",
        f"username={username.lower()}\nremoved={'yes' if removed else 'no'}",
    )

    if removed:
        flash("Username unlocked.", "ok")
    else:
        flash("Username was not currently locked.", "error")

    return redirect(url_for("admin.admin_dashboard"))
