from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from flask import current_app

from core.db import db_fetchone
from core.system_alerts import create_system_alert

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def _env_truthy(name: str) -> bool:
    return _env(name).lower() in TRUTHY_ENV_VALUES


def _status(
    key: str,
    label: str,
    state: str,
    detail: str,
    owner: str,
    next_step: str,
) -> dict[str, str]:
    return {
        "key": key,
        "label": label,
        "state": state,
        "detail": detail,
        "owner": owner,
        "next_step": next_step,
    }


def _table_is_readable(table_name: str) -> bool:
    safe_table_name = "".join(
        char for char in str(table_name or "") if char.isalnum() or char == "_"
    )
    if not safe_table_name:
        return False

    try:
        db_fetchone(f"SELECT 1 AS ok FROM {safe_table_name} LIMIT 1")
        return True
    except Exception:
        current_app.logger.exception(
            "enterprise_readiness_table_check_failed table=%s",
            safe_table_name,
        )
        return False


def _microsoft_sso_is_configured() -> bool:
    return (
        _env_truthy("MS_SSO_ENABLED")
        and bool(_env("MS_CLIENT_ID"))
        and bool(_env("MS_CLIENT_SECRET"))
        and bool(_env("MS_TENANT_ID"))
    )


def _identity_provider_card() -> dict[str, str]:
    if _microsoft_sso_is_configured():
        return _status(
            "identity_provider",
            "Identity Provider",
            "ok",
            "Microsoft Entra ID staff login is configured and enabled.",
            "Admin",
            "Keep local break glass admin credentials documented and test SSO after secret rotation.",
        )

    if _env_truthy("MS_SSO_ENABLED"):
        missing = []
        if not _env("MS_CLIENT_ID"):
            missing.append("MS_CLIENT_ID")
        if not _env("MS_CLIENT_SECRET"):
            missing.append("MS_CLIENT_SECRET")
        if not _env("MS_TENANT_ID"):
            missing.append("MS_TENANT_ID")

        return _status(
            "identity_provider",
            "Identity Provider",
            "error",
            "Microsoft SSO is enabled, but required Microsoft settings are missing.",
            "Admin",
            "Add missing Railway variables: " + ", ".join(missing),
        )

    if _env_truthy("IDENTITY_PROVIDER_ENABLED"):
        provider = _env("IDENTITY_PROVIDER_NAME") or "configured provider"
        has_oidc = bool(_env("OIDC_ISSUER_URL") and _env("OIDC_CLIENT_ID"))
        has_saml = bool(_env("SAML_METADATA_URL") or _env("SAML_METADATA_XML"))

        if has_oidc or has_saml:
            return _status(
                "identity_provider",
                "Identity Provider",
                "ok",
                f"External identity provider is marked enabled: {provider}.",
                "Admin",
                "Keep local break glass admin credentials documented and tested.",
            )

        return _status(
            "identity_provider",
            "Identity Provider",
            "error",
            "Identity provider is enabled, but no OIDC or SAML settings were found.",
            "Admin",
            "Add OIDC or SAML configuration before enforcing external login.",
        )

    return _status(
        "identity_provider",
        "Identity Provider",
        "warn",
        "Staff login is still local username and password, not SSO backed.",
        "Admin",
        "Configure Microsoft Entra ID SSO or another approved identity provider.",
    )


def _role_security_card() -> dict[str, str]:
    if _table_is_readable("staff_users") and _table_is_readable("staff_shelter_assignments"):
        return _status(
            "role_security",
            "Role Based Security",
            "ok",
            "Local role and shelter assignment tables are present and readable.",
            "Admin",
            "Finish the role permission matrix review and then connect roles to the identity provider.",
        )

    return _status(
        "role_security",
        "Role Based Security",
        "error",
        "Role or shelter assignment tables are missing or not readable.",
        "Admin",
        "Repair staff user and shelter assignment tables before expanding access controls.",
    )


def _alerting_card() -> dict[str, str]:
    channels = [
        _env_truthy("ALERT_EMAIL_ENABLED"),
        _env_truthy("ALERT_SMS_ENABLED"),
        bool(_env("ALERT_WEBHOOK_URL")),
    ]

    if not _table_is_readable("system_alerts"):
        return _status(
            "alerting_pipeline",
            "Automated Alerting Pipeline",
            "error",
            "System alerts table is not readable.",
            "Admin",
            "Repair system_alerts before relying on operational alerts.",
        )

    if any(channels):
        return _status(
            "alerting_pipeline",
            "Automated Alerting Pipeline",
            "ok",
            "System alerts are stored and at least one outbound alert channel is configured.",
            "Admin",
            "Confirm alert recipients and test one warning and one critical alert.",
        )

    return _status(
        "alerting_pipeline",
        "Automated Alerting Pipeline",
        "warn",
        "System alerts are stored in the app, but no outbound email, SMS, or webhook channel is configured.",
        "Admin",
        "Add alert recipients or webhook delivery so critical failures leave the dashboard.",
    )


def _disaster_recovery_card() -> dict[str, str]:
    has_backup_policy = bool(_env("BACKUP_POLICY_DOCUMENTED") or _env("RAILWAY_ENVIRONMENT"))
    has_secondary_region = bool(_env("DR_SECONDARY_REGION"))
    has_restore_test = bool(_env("DR_LAST_RESTORE_TESTED_AT") or _env("BACKUP_LAST_RESTORE_TESTED_AT"))
    has_runbook = bool(_env("DR_RUNBOOK_URL"))

    if has_secondary_region and has_restore_test and has_runbook:
        return _status(
            "disaster_recovery",
            "Disaster Recovery",
            "ok",
            "Secondary region, restore test marker, and recovery runbook are configured.",
            "Admin",
            "Schedule recurring restore tests and document actual recovery time.",
        )

    if has_backup_policy or has_restore_test:
        return _status(
            "disaster_recovery",
            "Disaster Recovery",
            "warn",
            "Backups are documented, but full cross region recovery is not fully configured.",
            "Admin",
            "Add secondary region, restore test date, and recovery runbook references.",
        )

    return _status(
        "disaster_recovery",
        "Disaster Recovery",
        "error",
        "No backup or disaster recovery environment markers were found.",
        "Admin",
        "Document backups, test restore, and define secondary region recovery steps.",
    )


def _analytics_reporting_card() -> dict[str, str]:
    if _table_is_readable("user_dashboard_favorites"):
        return _status(
            "analytics_reporting",
            "Analytics and Reporting",
            "ok",
            "Reporting dashboards and user dashboard favorites are available.",
            "Admin",
            "Continue building governed exports and scheduled board level reports.",
        )

    return _status(
        "analytics_reporting",
        "Analytics and Reporting",
        "warn",
        "Reporting routes exist, but dashboard preference storage was not readable.",
        "Admin",
        "Verify reporting schema and add governed export history.",
    )


def _compliance_logging_card() -> dict[str, str]:
    audit_ok = _table_is_readable("audit_log")
    field_audit_ok = _table_is_readable("field_change_audit")
    compliance_mode = _env_truthy("COMPLIANCE_MODE_ENABLED")

    if audit_ok and field_audit_ok and compliance_mode:
        return _status(
            "compliance_logging",
            "Compliance Logging",
            "ok",
            "Audit logs, field change audit, and compliance mode are enabled.",
            "Admin",
            "Review retention policy, minimum necessary access rules, and incident response workflow.",
        )

    if audit_ok or field_audit_ok:
        return _status(
            "compliance_logging",
            "Compliance Logging",
            "warn",
            "Audit logging exists, but the full compliance control set is not marked enabled.",
            "Admin",
            "Turn on compliance mode only after access review, retention policy, and incident procedures are approved.",
        )

    return _status(
        "compliance_logging",
        "Compliance Logging",
        "error",
        "Audit logging tables are missing or not readable.",
        "Admin",
        "Repair audit logging before adding HIPAA style controls.",
    )


def build_enterprise_readiness_cards() -> list[dict[str, str]]:
    return [
        _alerting_card(),
        _role_security_card(),
        _identity_provider_card(),
        _disaster_recovery_card(),
        _analytics_reporting_card(),
        _compliance_logging_card(),
    ]


def _severity_for_state(state: str) -> str:
    if state == "error":
        return "error"
    if state == "warn":
        return "warn"
    return "info"


def sync_enterprise_readiness_alerts(cards: list[dict[str, Any]]) -> int:
    created = 0
    checked_at = datetime.now(UTC).isoformat(timespec="seconds")

    for card in cards or []:
        state = str(card.get("state") or "").strip().lower()
        if state not in {"warn", "error"}:
            continue

        key = str(card.get("key") or "enterprise_control").strip()
        label = str(card.get("label") or "Enterprise control").strip()
        detail = str(card.get("detail") or "Enterprise readiness check needs attention.").strip()
        next_step = str(card.get("next_step") or "Review this enterprise control.").strip()

        if create_system_alert(
            alert_type="enterprise_readiness",
            severity=_severity_for_state(state),
            title=f"{label} needs attention",
            message=detail,
            source_module="enterprise_readiness",
            alert_key=f"enterprise_readiness:{key}:{state}",
            metadata=f"checked_at={checked_at} next_step={next_step}",
        ):
            created += 1

    return created
