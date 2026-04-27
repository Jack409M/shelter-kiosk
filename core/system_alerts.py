from __future__ import annotations

from typing import Any

from flask import current_app, g, session

from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import utcnow_iso

VALID_ALERT_STATUSES = {"open", "resolved"}
VALID_ALERT_SEVERITIES = {"info", "warn", "error", "critical"}


def _kind() -> str:
    return str(g.get("db_kind") or "").strip().lower()


def _normalize_text(value: Any) -> str:
    return str(value or "").strip()


def _normalize_severity(value: Any) -> str:
    severity = _normalize_text(value).lower()
    if severity not in VALID_ALERT_SEVERITIES:
        return "warn"
    return severity


def _normalize_status(value: Any) -> str:
    status = _normalize_text(value).lower()
    if status not in VALID_ALERT_STATUSES:
        return "open"
    return status


def _current_staff_user_id() -> int | None:
    try:
        raw_value = session.get("staff_user_id")
        if raw_value in (None, ""):
            return None
        return int(raw_value)
    except Exception:
        return None


def _open_alert_exists(alert_key: str) -> bool:
    row = db_fetchone(
        """
        SELECT id
        FROM system_alerts
        WHERE alert_key = %s
          AND status = %s
        ORDER BY id DESC
        LIMIT 1
        """,
        (alert_key, "open"),
    )
    return bool(row)


def create_system_alert(
    *,
    alert_type: str,
    severity: str,
    title: str,
    message: str,
    source_module: str = "",
    alert_key: str = "",
    entity_type: str = "",
    entity_id: int | None = None,
    metadata: str = "",
) -> bool:
    normalized_alert_type = _normalize_text(alert_type).lower()
    normalized_source = _normalize_text(source_module).lower()
    normalized_title = _normalize_text(title)
    normalized_message = _normalize_text(message)
    normalized_key = _normalize_text(alert_key)

    if not normalized_key:
        normalized_key = ":".join(
            part
            for part in (
                normalized_alert_type,
                normalized_source,
                _normalize_text(entity_type).lower(),
                str(entity_id or ""),
                normalized_title.lower(),
            )
            if part
        )

    if not normalized_key:
        normalized_key = normalized_title.lower() or normalized_alert_type or "system_alert"

    if _open_alert_exists(normalized_key):
        return False

    now = utcnow_iso()

    db_execute(
        """
        INSERT INTO system_alerts (
            alert_key,
            alert_type,
            severity,
            status,
            title,
            message,
            source_module,
            entity_type,
            entity_id,
            metadata,
            created_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            normalized_key,
            normalized_alert_type or "system",
            _normalize_severity(severity),
            "open",
            normalized_title,
            normalized_message,
            normalized_source,
            _normalize_text(entity_type).lower(),
            entity_id,
            _normalize_text(metadata),
            now,
            now,
        ),
    )
    return True


def create_system_alert_from_health_card(card: dict[str, Any]) -> bool:
    state = _normalize_text(card.get("state")).lower()
    if state not in {"warn", "error"}:
        return False

    label = _normalize_text(card.get("label"))
    detail = _normalize_text(card.get("detail"))
    meta = _normalize_text(card.get("meta"))
    severity = "error" if state == "error" else "warn"
    alert_key = f"system_health:{label.lower().replace(' ', '_')}:{state}"

    return create_system_alert(
        alert_type="system_health",
        severity=severity,
        title=f"{label} needs attention",
        message=detail or meta or "System health check reported a warning.",
        source_module="system_health",
        alert_key=alert_key,
        metadata=meta,
    )


def sync_system_health_alerts(cards: list[dict[str, Any]]) -> int:
    created = 0
    for card in cards or []:
        try:
            if create_system_alert_from_health_card(card):
                created += 1
        except Exception:
            current_app.logger.exception("system_health_alert_sync_failed")
    return created


def load_open_system_alerts(limit: int = 25) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 25), 100))
    return db_fetchall(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            severity,
            status,
            title,
            message,
            source_module,
            entity_type,
            entity_id,
            metadata,
            created_at,
            updated_at
        FROM system_alerts
        WHERE status = %s
        ORDER BY
            CASE severity
                WHEN 'critical' THEN 1
                WHEN 'error' THEN 2
                WHEN 'warn' THEN 3
                ELSE 4
            END,
            id DESC
        LIMIT %s
        """,
        ("open", safe_limit),
    )


def load_recent_system_alerts(limit: int = 50) -> list[dict[str, Any]]:
    safe_limit = max(1, min(int(limit or 50), 100))
    return db_fetchall(
        """
        SELECT
            id,
            alert_key,
            alert_type,
            severity,
            status,
            title,
            message,
            source_module,
            entity_type,
            entity_id,
            metadata,
            resolved_by_user_id,
            resolved_at,
            resolution_note,
            created_at,
            updated_at
        FROM system_alerts
        ORDER BY id DESC
        LIMIT %s
        """,
        (safe_limit,),
    )


def resolve_system_alert(alert_id: int, *, resolution_note: str = "") -> bool:
    alert = db_fetchone(
        "SELECT id, status FROM system_alerts WHERE id = %s LIMIT 1",
        (alert_id,),
    )
    if not alert:
        return False

    if _normalize_status(alert.get("status")) == "resolved":
        return True

    now = utcnow_iso()
    db_execute(
        """
        UPDATE system_alerts
        SET status = %s,
            resolved_by_user_id = %s,
            resolved_at = %s,
            resolution_note = %s,
            updated_at = %s
        WHERE id = %s
        """,
        (
            "resolved",
            _current_staff_user_id(),
            now,
            _normalize_text(resolution_note),
            now,
            alert_id,
        ),
    )
    return True


def count_open_system_alerts_by_severity() -> dict[str, int]:
    rows = db_fetchall(
        """
        SELECT severity, COUNT(1) AS count
        FROM system_alerts
        WHERE status = %s
        GROUP BY severity
        """,
        ("open",),
    )

    counts = {severity: 0 for severity in VALID_ALERT_SEVERITIES}
    for row in rows or []:
        severity = _normalize_severity(row.get("severity"))
        counts[severity] = int(row.get("count") or 0)
    return counts
