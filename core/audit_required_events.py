from __future__ import annotations

"""Compliance audit coverage registry for Shelter Kiosk.

This file is deliberately declarative. It defines the minimum operational event
surface that must remain auditable before the application can be treated as
having HIPAA style logging controls.

This does not certify the organization as HIPAA compliant. It gives the app a
single, reviewable control map for authentication, security, resident records,
case management, passes, data quality, backups, reporting, and system health.
"""

REQUIRED_AUDIT_EVENTS = {
    "auth": {
        "AUTH_LOGIN",
        "AUTH_LOGOUT",
        "AUTH_FAILED",
        "MICROSOFT_SSO_LOGIN",
        "MICROSOFT_SSO_FAILED",
        "SESSION_INVALIDATED",
        "PASSWORD_RESET",
    },
    "security": {
        "ADMIN_CONFIG_CHANGE",
        "SECURITY_SETTINGS_UPDATED",
        "ADMIN_LOGIN_ONLY_ENABLED",
        "ADMIN_LOGIN_ONLY_DISABLED",
        "IP_BANNED",
        "IP_UNBANNED",
        "USERNAME_UNLOCKED",
        "USER_CREATE",
        "USER_ACTIVATE",
        "USER_DEACTIVATE",
        "USER_ROLE_CHANGE",
        "USER_SHELTER_ASSIGNMENT_CHANGE",
    },
    "resident_record": {
        "RESIDENT_CREATE",
        "RESIDENT_UPDATE",
        "RESIDENT_DELETE",
        "ENROLLMENT_CREATE",
        "ENROLLMENT_EXIT",
        "ENROLLMENT_TRANSFER",
        "INTAKE_DRAFT_SAVE",
        "INTAKE_DRAFT_DELETE",
        "INTAKE_SUBMIT",
        "FAMILY_BASELINE_CREATE",
        "FAMILY_BASELINE_REPAIR",
    },
    "case_management": {
        "CASE_NOTE_CREATE",
        "CASE_NOTE_EDIT",
        "WRITEUP_CREATE",
        "WRITEUP_EDIT",
        "PROMOTION_REVIEW_CREATE",
        "TRANSFER_CREATE",
        "EXIT_CREATE",
    },
    "resident_passes": {
        "PASS_REQUEST",
        "PASS_APPROVE",
        "PASS_DENY",
        "PASS_CHECKIN",
        "PASS_EXPIRE",
        "PASS_CLEANUP_COMPLETED",
        "PASS_CLEANUP_FAILED",
    },
    "resident_operations": {
        "RENT_UPDATE",
        "EMPLOYMENT_UPDATE",
        "INCOME_UPDATE",
        "INSPECTION_CREATE",
        "INSPECTION_UPDATE",
        "ATTENDANCE_UPDATE",
    },
    "data_quality": {
        "MISSING_INTAKE_BASELINE_REPAIR",
        "MISSING_FAMILY_BASELINE_REPAIR",
        "SHELTER_MISMATCH_REPAIR",
        "DUPLICATE_NAMES_MARKED_SAME",
        "DUPLICATE_NAMES_CONFIRMED_SEPARATE",
        "DUPLICATE_MERGE_EXECUTE",
    },
    "system_health": {
        "SYSTEM_ALERT_CREATE",
        "SYSTEM_ALERT_ACKNOWLEDGE",
        "SYSTEM_ALERT_RESOLVE",
        "SYSTEM_ALERT_DELIVERY_SUCCESS",
        "SYSTEM_ALERT_DELIVERY_ERROR",
        "TIMESTAMP_CLEANUP_COMPLETED",
        "TIMESTAMP_CLEANUP_FAILED",
    },
    "backup_recovery": {
        "SYSTEM_BACKUP_RUN",
        "SYSTEM_BACKUP_VERIFY",
        "SYSTEM_BACKUP_RESTORE",
        "RESTORE_TEST_STARTED",
        "RESTORE_TEST_COMPLETED",
        "RESTORE_TEST_FAILED",
        "PRODUCTION_RECOVERY_STARTED",
        "PRODUCTION_RECOVERY_COMPLETED",
    },
    "reporting": {
        "REPORT_VIEW",
        "REPORT_EXPORT",
        "AUDIT_LOG_VIEW",
        "AUDIT_LOG_EXPORT",
        "SMS_LOG_VIEW",
        "SYSTEM_HEALTH_VIEW",
    },
}

COMPLIANCE_CONTROL_NOTES = {
    "purpose": "HIPAA style operational logging control map for DWC Shelter Kiosk.",
    "minimum_retention": "Retain audit, alert, SMS, security, and backup recovery logs according to the approved DWC retention policy.",
    "access_review": "Review admin, shelter director, case manager, staff, RA, and demographics viewer access on a recurring schedule.",
    "incident_response": "Treat unauthorized access, failed restore, missing backup, failed alert delivery, and data corruption as operational incidents.",
    "exports": "Report and audit exports should be limited to authorized staff and should leave an audit trail.",
    "resident_privacy": "Resident identifying information should only be accessed for a legitimate shelter operational purpose.",
}


def normalize_audit_event(value: str) -> str:
    return str(value or "").strip().upper().replace(" ", "_").replace("-", "_")


def required_audit_categories() -> list[str]:
    return sorted(REQUIRED_AUDIT_EVENTS.keys())


def required_audit_event_count() -> int:
    return sum(len(events) for events in REQUIRED_AUDIT_EVENTS.values())


def required_audit_event_names() -> set[str]:
    names: set[str] = set()
    for events in REQUIRED_AUDIT_EVENTS.values():
        names.update(normalize_audit_event(event) for event in events)
    return names


def is_required_audit_event(action_type: str) -> bool:
    return normalize_audit_event(action_type) in required_audit_event_names()


def compliance_summary() -> dict[str, object]:
    return {
        "category_count": len(REQUIRED_AUDIT_EVENTS),
        "event_count": required_audit_event_count(),
        "categories": required_audit_categories(),
        "notes": COMPLIANCE_CONTROL_NOTES,
    }
