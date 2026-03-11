from flask import jsonify, redirect, render_template, request, session, url_for, flash
from flask import current_app, g

from . import admin

from core.auth import require_login, require_shelter
from core.helpers import fmt_dt
from core.audit import log_action

# These will temporarily import from the old file
# until we move all helper functions
from routes.admin import (
    _require_admin,
    _build_admin_dashboard_payload,
)


@admin.route("/staff/admin/dashboard", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard():
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
        current_role=session.get("role"),
    )


@admin.route("/staff/admin/dashboard/live", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard_live():
    if not _require_admin():
        return jsonify({"ok": False, "error": "forbidden"}), 403

    payload = _build_admin_dashboard_payload(send_alerts=True)

    live_payload = payload["live_payload"]
    live_payload["ok"] = True

    return jsonify(live_payload)


@admin.post("/staff/admin/security-settings/update")
@require_login
@require_shelter
def admin_update_security_settings():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    allowed_fields = {
        "sms_system_enabled",
        "kiosk_intake_enabled",
        "admin_login_only_mode",
        "security_alerts_enabled",
    }

    field = (request.form.get("field") or "").strip()
    value = (request.form.get("value") or "").strip()

    if field not in allowed_fields:
        flash("Invalid security setting.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    if value not in {"0", "1"}:
        flash("Invalid security setting value.", "error")
        return redirect(url_for("admin.admin_dashboard"))

    bool_value = value == "1"

    kind = g.get("db_kind")
    from core.helpers import utcnow_iso
    from core.db import db_execute

    now = utcnow_iso()

    db_execute(
        f"UPDATE security_settings SET {field} = "
        + ("%s" if kind == "pg" else "?")
        + ", updated_at = "
        + ("%s" if kind == "pg" else "?")
        + " WHERE id = (SELECT id FROM security_settings ORDER BY id ASC LIMIT 1)",
        (bool_value if kind == "pg" else (1 if bool_value else 0), now),
    )

    log_action(
        "security_settings",
        None,
        None,
        session.get("staff_user_id"),
        "security_setting_updated",
        f"field={field}\nvalue={value}",
    )

    flash("Security setting updated.", "ok")
    return redirect(url_for("admin.admin_dashboard"))
