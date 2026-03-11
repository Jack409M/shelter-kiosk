from __future__ import annotations

from flask import (
    Blueprint,
    abort,
    g,
    jsonify,
    redirect,
    request,
    session,
    url_for,
    flash,
)

from core.audit import log_action
from core.auth import require_login, require_shelter
from core.db import db_execute
from core.helpers import utcnow_iso

# Future extraction note
# This file is now acting as the admin blueprint shell.
# Shared helper logic lives in routes.admin_parts.helpers
# User management view logic lives in routes.admin_parts.users
# Audit view logic lives in routes.admin_parts.audit
#
# Next extraction targets:
# 1. dashboard and security routes into routes.admin_parts.dashboard
# 2. dangerous system routes into routes.admin_parts.system
#
# End state goal:
# this file should eventually contain only:
# blueprint creation
# imports of delegated view functions
# thin route wrappers with decorators

from routes.admin_parts.helpers import (
    build_admin_dashboard_payload as _build_admin_dashboard_payload,
    current_role as _current_role,
    require_admin_role as _require_admin,
)

from routes.admin_parts.users import (
    admin_add_user_view,
    admin_edit_user_view,
    admin_reset_user_password_view,
    admin_set_user_active_view,
    admin_set_user_role_view,
    admin_users_view,
)

from routes.admin_parts.audit import (
    staff_audit_log_csv_view,
    staff_audit_log_view,
)

admin = Blueprint("admin", __name__)


@admin.route("/staff/admin/dashboard", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard():
    # Future extraction note
    # Move this route into routes.admin_parts.dashboard once the paired live
    # endpoint and security settings update route are extracted together.
    from core.helpers import fmt_dt
    from flask import render_template

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
    # Future extraction note
    # This should move with the dashboard routes into a dedicated admin
    # security module or service backed route file.
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


@admin.route("/staff/admin/users", methods=["GET"])
@require_login
@require_shelter
def admin_users():
    # Thin delegation wrapper.
    # Safe to remove later once decorators move to extracted route modules.
    return admin_users_view()


@admin.route("/staff/admin/users/add", methods=["GET"])
@require_login
@require_shelter
def admin_add_user():
    return admin_add_user_view()


@admin.route("/staff/admin/users/<int:user_id>/edit", methods=["GET"])
@require_login
@require_shelter
def admin_edit_user(user_id: int):
    return admin_edit_user_view(user_id)


@admin.post("/staff/admin/users/<int:user_id>/set-active")
@require_login
@require_shelter
def admin_set_user_active(user_id: int):
    return admin_set_user_active_view(user_id)


@admin.post("/staff/admin/users/<int:user_id>/set-role")
@require_login
@require_shelter
def admin_set_user_role(user_id: int):
    return admin_set_user_role_view(user_id)


@admin.post("/staff/admin/users/<int:user_id>/reset-password")
@require_login
@require_shelter
def admin_reset_user_password(user_id: int):
    return admin_reset_user_password_view(user_id)


@admin.route("/staff/admin/audit-log")
@require_login
@require_shelter
def staff_audit_log():
    # Thin delegation wrapper.
    # Audit now lives in routes.admin_parts.audit.
    return staff_audit_log_view()


@admin.get("/staff/admin/audit-log/csv")
@require_login
@require_shelter
def staff_audit_log_csv():
    return staff_audit_log_csv_view()


@admin.route("/admin/wipe-all-data", methods=["POST"])
@require_login
@require_shelter
def wipe_all_data():
    # Future extraction note
    # Dangerous admin actions should move into routes.admin_parts.system and
    # eventually behind a guarded service layer for destructive actions.
    from app import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    db_execute(
        "TRUNCATE TABLE attendance_events RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM attendance_events"
    )
    db_execute(
        "TRUNCATE TABLE leave_requests RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM leave_requests"
    )
    db_execute(
        "TRUNCATE TABLE transport_requests RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM transport_requests"
    )
    db_execute(
        "TRUNCATE TABLE residents RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM residents"
    )
    db_execute(
        "TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM audit_log"
    )
    db_execute(
        "TRUNCATE TABLE security_incidents RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM security_incidents"
    )

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "wipe_all_data",
        "Wiped attendance, leave, transport, residents, audit_log, security_incidents",
    )
    return "All non staff data wiped."


@admin.route("/admin/recreate-schema", methods=["POST"])
@require_login
@require_shelter
def recreate_schema():
    from app import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    if g.get("db_kind") == "pg":
        db_execute("DROP TABLE IF EXISTS attendance_events CASCADE")
        db_execute("DROP TABLE IF EXISTS leave_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS transport_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS residents CASCADE")
        db_execute("DROP TABLE IF EXISTS audit_log CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_transfers CASCADE")
        db_execute("DROP TABLE IF EXISTS rate_limit_events CASCADE")
        db_execute("DROP TABLE IF EXISTS security_incidents CASCADE")
        db_execute("DROP TABLE IF EXISTS security_settings CASCADE")
    else:
        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS leave_requests")
        db_execute("DROP TABLE IF EXISTS transport_requests")
        db_execute("DROP TABLE IF EXISTS residents")
        db_execute("DROP TABLE IF EXISTS audit_log")
        db_execute("DROP TABLE IF EXISTS resident_transfers")
        db_execute("DROP TABLE IF EXISTS security_incidents")
        db_execute("DROP TABLE IF EXISTS security_settings")

    init_db()

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "recreate_schema",
        "Dropped and recreated tables",
    )
    return "Schema recreated."
