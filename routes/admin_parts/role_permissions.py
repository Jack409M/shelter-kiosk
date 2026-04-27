from __future__ import annotations

from flask import flash, redirect, render_template, url_for

from core.auth import PASS_STATUS_ROLES, REQUEST_MANAGER_ROLES
from routes.admin_parts.helpers import ROLE_ORDER, require_admin_role

ROLE_LABELS = {
    "admin": "Admin",
    "shelter_director": "Shelter Director",
    "case_manager": "Case Manager",
    "ra": "Resident Assistant",
    "staff": "Staff",
    "demographics_viewer": "Demographics Viewer",
}

PERMISSION_DEFINITIONS = [
    {
        "key": "staff_login",
        "label": "Staff login",
        "description": "Can sign in to the staff side when active and assigned to a shelter.",
        "roles": set(ROLE_ORDER),
        "source": "core.auth.require_login",
    },
    {
        "key": "select_shelter",
        "label": "Use assigned shelter context",
        "description": "Can work inside a selected shelter when the shelter is allowed for that user.",
        "roles": set(ROLE_ORDER),
        "source": "core.auth.require_shelter",
    },
    {
        "key": "admin_dashboard",
        "label": "Admin dashboard",
        "description": "Can reach the admin dashboard route after login and shelter selection.",
        "roles": {"admin", "shelter_director"},
        "source": "routes.admin + admin helper policy",
    },
    {
        "key": "manage_users",
        "label": "Manage staff users",
        "description": "Can create, edit, activate, deactivate, reset passwords, and change staff roles according to allowed role rules.",
        "roles": {"admin", "shelter_director"},
        "source": "routes.admin_parts.users + allowed_roles_to_create",
    },
    {
        "key": "assign_admin_role",
        "label": "Create or assign admin role",
        "description": "Can grant the admin role to another staff account.",
        "roles": {"admin"},
        "source": "routes.admin_parts.helpers.allowed_roles_to_create",
    },
    {
        "key": "system_health",
        "label": "System Health dashboard",
        "description": "Can view database, scheduler, SMS, app version, event, alert, and cleanup status.",
        "roles": {"admin"},
        "source": "routes.admin_parts.sh_dashboard.require_admin_role",
    },
    {
        "key": "resolve_system_alerts",
        "label": "Resolve system alerts",
        "description": "Can mark System Health alerts as resolved.",
        "roles": {"admin"},
        "source": "routes.admin_parts.sh_dashboard.resolve_system_health_alert_view",
    },
    {
        "key": "data_quality",
        "label": "Data Quality tools",
        "description": "Can review and repair missing intake baselines, shelter mismatches, and duplicate resident findings.",
        "roles": {"admin"},
        "source": "routes.admin_parts.sh_data_quality + duplicate review routes",
    },
    {
        "key": "audit_log",
        "label": "Audit log",
        "description": "Can view and export operational audit log entries.",
        "roles": {"admin"},
        "source": "routes.admin_parts.audit.require_admin_role",
    },
    {
        "key": "field_audit",
        "label": "Field audit",
        "description": "Can review field-level audit visibility in the admin area.",
        "roles": {"admin"},
        "source": "routes.admin_parts.field_audit",
    },
    {
        "key": "security_controls",
        "label": "Security controls",
        "description": "Can update security settings, ban IPs, unban IPs, and unlock usernames.",
        "roles": {"admin"},
        "source": "routes.admin_parts.dashboard security actions",
    },
    {
        "key": "demo_data_tools",
        "label": "Demo data tools",
        "description": "Can seed and clear demo data from the admin area.",
        "roles": {"admin"},
        "source": "routes.admin_parts.system",
    },
    {
        "key": "manage_requests",
        "label": "Manage resident requests",
        "description": "Can manage request workflows guarded by can_manage_requests().",
        "roles": REQUEST_MANAGER_ROLES,
        "source": "core.auth.REQUEST_MANAGER_ROLES",
    },
    {
        "key": "view_pass_status",
        "label": "View pass status",
        "description": "Can see resident pass status where guarded by can_view_pass_status().",
        "roles": PASS_STATUS_ROLES,
        "source": "core.auth.PASS_STATUS_ROLES",
    },
    {
        "key": "review_passes",
        "label": "Review passes",
        "description": "Can participate in staff pass review workflows when allowed by the pass routes and staff permissions.",
        "roles": {"admin", "shelter_director", "case_manager"},
        "source": "staff pass review workflow policy",
    },
    {
        "key": "case_management",
        "label": "Case management workspace",
        "description": "Can work with residents in the case management workspace according to route-level staff access.",
        "roles": {"admin", "shelter_director", "case_manager"},
        "source": "case management route policy",
    },
    {
        "key": "reports",
        "label": "Reports",
        "description": "Can access staff reporting pages where report routes allow staff access.",
        "roles": {"admin", "shelter_director", "case_manager"},
        "source": "reports route policy",
    },
]


def _matrix_rows() -> list[dict]:
    rows: list[dict] = []

    for permission in PERMISSION_DEFINITIONS:
        allowed_roles = set(permission["roles"])
        rows.append(
            {
                "key": permission["key"],
                "label": permission["label"],
                "description": permission["description"],
                "source": permission["source"],
                "role_access": [
                    {
                        "role": role,
                        "label": ROLE_LABELS.get(role, role.replace("_", " ").title()),
                        "allowed": role in allowed_roles,
                    }
                    for role in ROLE_ORDER
                ],
            }
        )

    return rows


def role_permission_matrix_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    roles = [
        {
            "key": role,
            "label": ROLE_LABELS.get(role, role.replace("_", " ").title()),
        }
        for role in ROLE_ORDER
    ]

    return render_template(
        "role_permissions.html",
        title="Role Permission Matrix",
        roles=roles,
        rows=_matrix_rows(),
    )
