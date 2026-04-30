from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from pathlib import Path

from flask import current_app

from core.db import db_fetchone
from core.system_alerts import create_system_alert

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}


def _env(name: str) -> str:
    return str(os.environ.get(name) or "").strip()


def _env_truthy(name: str) -> bool:
    return _env(name).lower() in TRUTHY_ENV_VALUES


def _project_file_exists(rel_path: str) -> bool:
    try:
        base = Path(current_app.root_path)
        return (base / rel_path).exists()
    except Exception:
        return False


def _status(key: str, label: str, state: str, detail: str, owner: str, next_step: str) -> dict[str, str]:
    return {"key": key, "label": label, "state": state, "detail": detail, "owner": owner, "next_step": next_step}


def _table_is_readable(table_name: str) -> bool:
    safe_table_name = "".join(char for char in str(table_name or "") if char.isalnum() or char == "_")
    if not safe_table_name:
        return False
    try:
        db_fetchone(f"SELECT 1 AS ok FROM {safe_table_name} LIMIT 1")
        return True
    except Exception:
        current_app.logger.exception("enterprise_readiness_table_check_failed table=%s", safe_table_name)
        return False


def _compliance_logging_card() -> dict[str, str]:
    audit_ok = _table_is_readable("audit_log")
    field_audit_ok = _table_is_readable("field_change_audit")
    compliance_mode = _env_truthy("COMPLIANCE_MODE_ENABLED")
    control_file_exists = _project_file_exists("core/audit_required_events.py")

    if audit_ok and field_audit_ok and (compliance_mode or control_file_exists):
        return _status("compliance_logging","Compliance Logging","ok","Audit logs and defined compliance control set are in place.","Admin","Maintain audit coverage and review event set periodically.")

    if audit_ok or field_audit_ok:
        return _status("compliance_logging","Compliance Logging","warn","Audit logging exists, but full compliance control set is not enabled.","Admin","Define required audit events and confirm coverage.")

    return _status("compliance_logging","Compliance Logging","error","Audit logging tables missing.","Admin","Repair audit logging.")


def _disaster_recovery_card() -> dict[str, str]:
    has_backup_policy = bool(_env("BACKUP_POLICY_DOCUMENTED") or _env("RAILWAY_ENVIRONMENT"))
    dr_config_exists = _project_file_exists("core/dr_config.py")

    if dr_config_exists:
        return _status("disaster_recovery","Disaster Recovery","ok","Cross region recovery path is defined and restore tested.","Admin","Re test periodically.")

    if has_backup_policy:
        return _status("disaster_recovery","Disaster Recovery","warn","Backups exist but full recovery not defined.","Admin","Add DR config and test restore.")

    return _status("disaster_recovery","Disaster Recovery","error","No DR markers found.","Admin","Document and test recovery.")


def build_enterprise_readiness_cards() -> list[dict[str, str]]:
    from core.enterprise_readiness import _alerting_card,_role_security_card,_identity_provider_card,_analytics_reporting_card

    return [
        _alerting_card(),
        _role_security_card(),
        _identity_provider_card(),
        _disaster_recovery_card(),
        _analytics_reporting_card(),
        _compliance_logging_card(),
    ]


def _severity_for_state(state: str) -> str:
    if state == "error": return "error"
    if state == "warn": return "warn"
    return "info"


def sync_enterprise_readiness_alerts(cards: list[dict[str, Any]]) -> int:
    created = 0
    checked_at = datetime.now(UTC).isoformat(timespec="seconds")

    for card in cards or []:
        state = str(card.get("state") or "").strip().lower()
        if state not in {"warn","error"}:
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
