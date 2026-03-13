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

from core.audit import log_action
from core.db import db_execute
from core.helpers import fmt_dt, utcnow_iso

from routes.admin_parts.helpers import (
    build_admin_dashboard_payload as _build_admin_dashboard_payload,
    current_role as _current_role,
    require_admin_role as _require_admin,
)


# ------------------------------------------------------------
# Admin Dashboard
# ------------------------------------------------------------
# This module holds dashboard and security related logic.
#
# Keeping it isolated prevents admin.py from becoming a large
# operational file again.
#
# Future possible splits:
# dashboard_metrics.py
# security_controls.py
# ------------------------------------------------------------


AUTO_RESET_HOURS = 8

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


def admin_dashboard_view():

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

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


# ------------------------------------------------------------
# Live dashboard polling endpoint
# ------------------------------------------------------------

def admin_dashboard_live_view():

    if not _require_admin():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = _build_admin_dashboard_payload(send_alerts=True)
    live_payload = payload["live_payload"]
    live_payload["ok"] = True

    return jsonify(live_payload)


# ------------------------------------------------------------
# Security settings update
# ------------------------------------------------------------

def admin_update_security_settings_view():

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

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
