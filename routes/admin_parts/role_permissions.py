from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

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

PUBLIC_ENDPOINT_PREFIXES = (
    "static",
    "auth.staff_login",
)

RESIDENT_ENDPOINT_PREFIXES = (
    "resident_portal",
    "resident_auth",
    "resident.",
)

ADMIN_ONLY_ENDPOINT_PREFIXES = (
    "admin.admin_system_health",
    "admin.admin_system_health_events",
    "admin.admin_system_health_data_quality",
    "admin.admin_resolve_system_alert",
    "admin.duplicate_name_group_review",
    "admin.duplicate_merge_review_queue",
    "admin.duplicate_merge_resident_snapshot",
    "admin.admin_select_duplicate_primary",
    "admin.admin_duplicate_merge_execute",
    "admin.admin_fix_missing_intake_baseline",
    "admin.admin_fix_shelter_mismatch",
    "admin.admin_confirm_duplicate_names_separate",
    "admin.admin_mark_duplicate_names_same",
    "admin.staff_audit_log",
    "admin.staff_audit_log_csv",
    "admin.admin_field_audit",
    "admin.admin_demo_data",
    "admin.admin_seed_demo_data",
    "admin.admin_clear_demo_data",
    "admin.admin_run_pass_cleanup",
    "admin.admin_role_permissions",
)

ADMIN_OR_DIRECTOR_ENDPOINT_PREFIXES = (
    "admin.admin_dashboard",
    "admin.admin_dashboard_live",
    "admin.admin_users",
    "admin.admin_add_user",
    "admin.admin_edit_user",
    "admin.admin_set_user_active",
    "admin.admin_set_user_role",
    "admin.admin_reset_user_password",
)

SECURITY_ADMIN_ENDPOINT_PREFIXES = (
    "admin.admin_update_security_settings",
    "admin.admin_ban_ip",
    "admin.admin_unban_ip",
    "admin.admin_unlock_username",
)

CASE_MANAGER_ENDPOINT_PREFIXES = (
    "case_management",
    "resident_detail",
    "residents",
)

PASS_REVIEW_ENDPOINT_PREFIXES = (
    "attendance.staff_passes",
    "attendance.staff_pass_detail",
    "attendance.staff_pass_approve",
    "attendance.staff_pass_deny",
    "attendance.staff_pass_check_in",
)

STAFF_VISIBLE_ENDPOINT_PREFIXES = (
    "attendance",
    "staff_portal",
    "reports",
)

DANGEROUS_ROUTE_TERMS = (
    "approve",
    "ban",
    "clear",
    "delete",
    "deny",
    "execute",
    "fix",
    "merge",
    "reset",
    "run",
    "seed",
    "set-active",
    "set-role",
    "unban",
    "unlock",
    "update",
)

CRITICAL_ROUTE_TERMS = (
    "clear",
    "delete",
    "execute",
    "merge",
    "reset",
    "run-pass-cleanup",
    "seed",
    "set-role",
)

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

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


def _role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role.replace("_", " ").title())


def _matrix_rows() -> list[dict]:
    rows: list[dict] = []

    for permission in PERMISSION_DEFINITIONS:
        allowed_roles = set(permission["roles"])
        role_access = []

        for role in ROLE_ORDER:
            role_access.append(
                {
                    "role": role,
                    "label": _role_label(role),
                    "allowed": role in allowed_roles,
                }
            )

        rows.append(
            {
                "key": permission["key"],
                "label": permission["label"],
                "description": permission["description"],
                "source": permission["source"],
                "role_access": role_access,
            }
        )

    return rows


def _endpoint_startswith(endpoint: str, prefixes: tuple[str, ...]) -> bool:
    return any(endpoint == prefix or endpoint.startswith(prefix) for prefix in prefixes)


def _infer_route_roles(endpoint: str, rule: str) -> tuple[str, set[str], str]:
    if _endpoint_startswith(endpoint, PUBLIC_ENDPOINT_PREFIXES):
        return "Public", set(), "public/static or login endpoint"

    if _endpoint_startswith(endpoint, RESIDENT_ENDPOINT_PREFIXES) or rule.startswith("/resident"):
        return "Resident facing", set(), "resident route namespace"

    if _endpoint_startswith(endpoint, ADMIN_ONLY_ENDPOINT_PREFIXES):
        return "Admin only", {"admin"}, "known admin-only endpoint"

    if _endpoint_startswith(endpoint, SECURITY_ADMIN_ENDPOINT_PREFIXES):
        return "Admin only", {"admin"}, "security admin action endpoint"

    if _endpoint_startswith(endpoint, ADMIN_OR_DIRECTOR_ENDPOINT_PREFIXES):
        return "Admin or shelter director", {"admin", "shelter_director"}, "known admin/director endpoint"

    if _endpoint_startswith(endpoint, PASS_REVIEW_ENDPOINT_PREFIXES):
        return "Pass review staff", {"admin", "shelter_director", "case_manager"}, "pass review route namespace"

    if _endpoint_startswith(endpoint, CASE_MANAGER_ENDPOINT_PREFIXES):
        return "Case management staff", {"admin", "shelter_director", "case_manager"}, "case management route namespace"

    if _endpoint_startswith(endpoint, STAFF_VISIBLE_ENDPOINT_PREFIXES) or rule.startswith("/staff"):
        return "Logged-in staff", set(ROLE_ORDER), "staff route namespace"

    return "Unknown or unclassified", set(), "no known route policy match"


def _contains_any(value: str, terms: tuple[str, ...]) -> bool:
    lower_value = value.lower()
    return any(term in lower_value for term in terms)


def _route_risk(
    rule: str,
    endpoint: str,
    methods: list[str],
    classification: str,
    allowed_roles: set[str],
) -> dict:
    combined = f"{rule} {endpoint}"
    findings: list[str] = []
    score = 0
    has_write_method = any(method in WRITE_METHODS for method in methods)
    has_dangerous_term = _contains_any(combined, DANGEROUS_ROUTE_TERMS)
    has_critical_term = _contains_any(combined, CRITICAL_ROUTE_TERMS)

    if classification == "Unknown or unclassified":
        score += 4
        findings.append("Route is not classified by the permission audit map.")

    if has_write_method:
        score += 2
        findings.append("Route accepts a data changing method.")

    if has_dangerous_term:
        score += 2
        findings.append("Route name suggests data changing or security sensitive behavior.")

    if has_critical_term:
        score += 2
        findings.append("Route contains a high impact action keyword.")

    if has_write_method and allowed_roles == set(ROLE_ORDER):
        score += 4
        findings.append("Write route appears broadly available to all staff roles.")

    if has_write_method and classification in {"Public", "Resident facing", "Unknown or unclassified"}:
        score += 5
        findings.append("Write route is public, resident facing, or unclassified and needs review.")

    if has_critical_term and "admin" not in allowed_roles:
        score += 4
        findings.append("High impact route is not clearly admin protected.")

    if score >= 9:
        level = "critical"
    elif score >= 6:
        level = "high"
    elif score >= 3:
        level = "medium"
    else:
        level = "low"

    return {
        "score": score,
        "level": level,
        "findings": findings,
    }


def _route_audit_rows() -> list[dict]:
    rows: list[dict] = []

    for rule in sorted(current_app.url_map.iter_rules(), key=lambda item: item.rule):
        methods = sorted(
            method
            for method in rule.methods or []
            if method not in {"HEAD", "OPTIONS"}
        )
        classification, allowed_roles, source = _infer_route_roles(rule.endpoint, rule.rule)
        risk = _route_risk(
            rule.rule,
            rule.endpoint,
            methods,
            classification,
            allowed_roles,
        )
        role_access = []

        for role in ROLE_ORDER:
            role_access.append(
                {
                    "role": role,
                    "label": _role_label(role),
                    "allowed": role in allowed_roles,
                }
            )

        rows.append(
            {
                "rule": rule.rule,
                "endpoint": rule.endpoint,
                "methods": ", ".join(methods),
                "classification": classification,
                "source": source,
                "risk": risk,
                "role_access": role_access,
            }
        )

    rows.sort(key=lambda row: (int(row["risk"]["score"]), row["rule"]), reverse=True)
    return rows


def _filter_rows_by_role(rows: list[dict], selected_role: str) -> list[dict]:
    if not selected_role:
        return rows

    filtered = []
    for row in rows:
        for access in row["role_access"]:
            if access["role"] == selected_role and access["allowed"]:
                filtered.append(row)
                break

    return filtered


def role_permission_matrix_view():
    if not require_admin_role():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    selected_role = request.args.get("role", "").strip()
    if selected_role not in ROLE_ORDER:
        selected_role = ""

    roles = []
    for role in ROLE_ORDER:
        roles.append(
            {
                "key": role,
                "label": _role_label(role),
            }
        )

    all_route_rows = _route_audit_rows()
    route_rows = _filter_rows_by_role(all_route_rows, selected_role)
    risk_findings = [
        row
        for row in all_route_rows
        if row["risk"]["level"] in {"critical", "high"}
    ]
    unclassified_count = sum(
        1
        for row in all_route_rows
        if row["classification"] == "Unknown or unclassified"
    )

    return render_template(
        "role_permissions.html",
        title="Role Permission Matrix",
        roles=roles,
        rows=_matrix_rows(),
        route_rows=route_rows,
        route_count=len(all_route_rows),
        filtered_route_count=len(route_rows),
        unclassified_count=unclassified_count,
        selected_role=selected_role,
        selected_role_label=_role_label(selected_role) if selected_role else "All Roles",
        risk_findings=risk_findings[:25],
        risk_finding_count=len(risk_findings),
    )
