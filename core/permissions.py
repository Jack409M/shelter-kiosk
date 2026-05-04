from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from flask import abort, current_app, request, session

PUBLIC_ENDPOINT_PREFIXES: Final[tuple[str, ...]] = (
    "auth.",
    "microsoft_auth.",
    "public.",
    "resident_requests.",
    "resident_portal.",
    "static",
    "twilio.",
    "health.",
)

STAFF_PERMISSION_PREFIXES: Final[dict[str, str]] = {
    "NP_placement.": "placement.manage",
    "RR_rent_admin.": "rent.manage",
    "admin.": "admin.manage",
    "attendance.": "attendance.view",
    "bed_turnover.": "shelter_operations.manage",
    "calendar.": "calendar.view",
    "case_dashboard.": "case_management.view",
    "case_management.": "case_management.manage",
    "case_management_exit.": "case_management.exit",
    "field_audit.": "audit.view",
    "inspection_v2.": "inspections.manage",
    "kiosk.": "kiosk.manage",
    "operations_settings.": "operations_settings.manage",
    "rent_tracking.": "rent.manage",
    "reports.": "reports.view",
    "reports_active_census.": "reports.view",
    "reports_exit_outcomes.": "reports.view",
    "reports_family_children.": "reports.view",
    "reports_followup_outcomes.": "reports.view",
    "reports_income_change.": "reports.view",
    "reports_intake_profile.": "reports.view",
    "reports_length_of_stay.": "reports.view",
    "reports_prior_living.": "reports.view",
    "reports_program_flow.": "reports.view",
    "reports_rent_financial.": "reports.financial.view",
    "reports_resident_demographics_summary.": "reports.demographics.view",
    "reports_sobriety_progress.": "reports.view",
    "reports_weekly_productivity.": "reports.view",
    "resident_detail.": "residents.view",
    "residents.": "residents.manage",
    "shelter_capacity.": "shelter_operations.manage",
    "shelter_operations.": "shelter_operations.manage",
    "staff_email_admin.": "communications.email.admin",
    "staff_portal.": "staff_portal.view",
    "staff_sms.": "communications.sms.manage",
    "system.": "system.view",
    "system_health.": "system.health.view",
    "transport.": "transport.manage",
    "writeups.": "writeups.manage",
}

ROLE_PERMISSIONS: Final[dict[str, set[str]]] = {
    "admin": {"*"},
    "shelter_director": {
        "attendance.view",
        "audit.view",
        "calendar.view",
        "case_management.exit",
        "case_management.manage",
        "case_management.view",
        "communications.sms.manage",
        "inspections.manage",
        "placement.manage",
        "rent.manage",
        "reports.demographics.view",
        "reports.financial.view",
        "reports.view",
        "residents.manage",
        "residents.view",
        "shelter_operations.manage",
        "staff_portal.view",
        "system.health.view",
        "system.view",
        "transport.manage",
        "writeups.manage",
    },
    "case_manager": {
        "attendance.view",
        "calendar.view",
        "case_management.exit",
        "case_management.manage",
        "case_management.view",
        "communications.sms.manage",
        "inspections.manage",
        "placement.manage",
        "rent.manage",
        "reports.view",
        "residents.manage",
        "residents.view",
        "shelter_operations.manage",
        "staff_portal.view",
        "transport.manage",
        "writeups.manage",
    },
    "staff": {
        "attendance.view",
        "calendar.view",
        "staff_portal.view",
        "transport.manage",
    },
    "ra": {
        "attendance.view",
        "calendar.view",
        "case_management.view",
        "inspections.manage",
        "residents.manage",
        "residents.view",
        "shelter_operations.manage",
        "staff_portal.view",
        "transport.manage",
    },
    "demographics_viewer": {
        "reports.demographics.view",
        "reports.view",
        "staff_portal.view",
    },
}


@dataclass(frozen=True)
class RoutePermissionDecision:
    endpoint: str
    required_permission: str | None
    is_public: bool
    is_staff_route: bool


def _clean_role(value: object) -> str:
    return str(value or "").strip()


def endpoint_is_public(endpoint: str | None) -> bool:
    cleaned_endpoint = str(endpoint or "").strip()
    if not cleaned_endpoint:
        return True

    return cleaned_endpoint.startswith(PUBLIC_ENDPOINT_PREFIXES)


def permission_for_endpoint(endpoint: str | None) -> str | None:
    cleaned_endpoint = str(endpoint or "").strip()
    if not cleaned_endpoint or endpoint_is_public(cleaned_endpoint):
        return None

    for prefix, permission in STAFF_PERMISSION_PREFIXES.items():
        if cleaned_endpoint.startswith(prefix):
            return permission

    return None


def route_permission_decision(endpoint: str | None) -> RoutePermissionDecision:
    cleaned_endpoint = str(endpoint or "").strip()
    required_permission = permission_for_endpoint(cleaned_endpoint)

    return RoutePermissionDecision(
        endpoint=cleaned_endpoint,
        required_permission=required_permission,
        is_public=endpoint_is_public(cleaned_endpoint),
        is_staff_route=required_permission is not None,
    )


def role_has_permission(role: str | None, permission: str | None) -> bool:
    if not permission:
        return True

    permissions = ROLE_PERMISSIONS.get(_clean_role(role), set())

    return "*" in permissions or permission in permissions


def enforce_route_permission():
    endpoint = str(request.endpoint or "").strip()
    decision = route_permission_decision(endpoint)

    if decision.is_public:
        return None

    if "staff_user_id" not in session:
        return None

    if not decision.required_permission:
        current_app.logger.warning(
            "permission_registry_missing endpoint=%s path=%s role=%s",
            endpoint,
            request.path,
            _clean_role(session.get("role")),
        )
        abort(403)

    if not role_has_permission(_clean_role(session.get("role")), decision.required_permission):
        current_app.logger.warning(
            "permission_denied endpoint=%s path=%s role=%s required_permission=%s staff_user_id=%s",
            endpoint,
            request.path,
            _clean_role(session.get("role")),
            decision.required_permission,
            session.get("staff_user_id"),
        )
        abort(403)

    return None


def unmapped_staff_endpoints(app) -> list[str]:
    missing: list[str] = []

    for rule in app.url_map.iter_rules():
        endpoint = str(rule.endpoint or "").strip()
        if endpoint_is_public(endpoint):
            continue
        if permission_for_endpoint(endpoint):
            continue
        missing.append(endpoint)

    return sorted(set(missing))
