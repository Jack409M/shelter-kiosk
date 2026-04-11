from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter

from routes.admin_parts.audit import (
    staff_audit_log_csv_view,
    staff_audit_log_view,
)

from routes.admin_parts.dashboard import (
    admin_ban_ip_view,
    admin_dashboard_live_view,
    admin_dashboard_view,
    admin_unban_ip_view,
    admin_unlock_username_view,
    admin_update_security_settings_view,
)

from routes.admin_parts.field_audit import (
    admin_field_audit_view,
)

from routes.admin_parts.system import (
    admin_demo_data_view,
    clear_demo_data_view,
    seed_demo_data_view,
)

from routes.admin_parts.users import (
    admin_add_user_view,
    admin_edit_user_view,
    admin_reset_user_password_view,
    admin_set_user_active_view,
    admin_set_user_role_view,
    admin_users_view,
)

admin = Blueprint("admin", __name__)


@admin.route("/staff/admin/dashboard", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard():
    return admin_dashboard_view()


@admin.route("/staff/admin/dashboard/live", methods=["GET"])
@require_login
@require_shelter
def admin_dashboard_live():
    return admin_dashboard_live_view()


@admin.post("/staff/admin/security-settings/update")
@require_login
@require_shelter
def admin_update_security_settings():
    return admin_update_security_settings_view()


@admin.post("/staff/admin/security/ban-ip")
@require_login
@require_shelter
def admin_ban_ip():
    return admin_ban_ip_view()


@admin.post("/staff/admin/security/unban-ip")
@require_login
@require_shelter
def admin_unban_ip():
    return admin_unban_ip_view()


@admin.post("/staff/admin/security/unlock-username")
@require_login
@require_shelter
def admin_unlock_username():
    return admin_unlock_username_view()


@admin.route("/staff/admin/users", methods=["GET"])
@require_login
@require_shelter
def admin_users():
    return admin_users_view()


@admin.route("/staff/admin/users/add", methods=["GET", "POST"])
@require_login
@require_shelter
def admin_add_user():
    return admin_add_user_view()


@admin.route("/staff/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
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
    return staff_audit_log_view()


@admin.get("/staff/admin/audit-log/csv")
@require_login
@require_shelter
def staff_audit_log_csv():
    return staff_audit_log_csv_view()


@admin.route("/staff/admin/field-audit", methods=["GET"])
@require_login
@require_shelter
def admin_field_audit():
    return admin_field_audit_view()


@admin.get("/staff/admin/demo-data")
@require_login
@require_shelter
def admin_demo_data():
    return admin_demo_data_view()


@admin.post("/staff/admin/demo-data/seed")
@require_login
@require_shelter
def admin_seed_demo_data():
    return seed_demo_data_view()


@admin.post("/staff/admin/demo-data/clear")
@require_login
@require_shelter
def admin_clear_demo_data():
    return clear_demo_data_view()
