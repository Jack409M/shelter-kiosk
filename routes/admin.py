from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter

# Admin blueprint shell
#
# This file should stay thin.
# All substantive behavior now lives in routes.admin_parts.*
#
# Current delegated modules:
# helpers.py
# users.py
# audit.py
# dashboard.py
# system.py
#
# Future goal:
# keep this file limited to blueprint creation and decorated wrappers only.

from routes.admin_parts.audit import (
    staff_audit_log_csv_view,
    staff_audit_log_view,
)

from routes.admin_parts.dashboard import (
    admin_dashboard_live_view,
    admin_dashboard_view,
    admin_update_security_settings_view,
)

from routes.admin_parts.system import (
    recreate_schema_view,
    wipe_all_data_view,
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


@admin.route("/staff/admin/users", methods=["GET"])
@require_login
@require_shelter
def admin_users():
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
    return wipe_all_data_view()


@admin.route("/admin/recreate-schema", methods=["POST"])
@require_login
@require_shelter
def recreate_schema():
    return recreate_schema_view()
