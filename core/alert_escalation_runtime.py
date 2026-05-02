from __future__ import annotations

import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from core.alert_escalation import (
    build_escalation_targets,
    escalation_enabled,
    escalation_failure_window_minutes,
    escalation_level_for_failure_count,
)
from core.db import db_fetchone
from core.time_utils import utc_naive_iso

LogDeliveryFn = Callable[..., None]
DEFAULT_ESCALATION_COOLDOWN_MINUTES = 10


def _safe_text(value: Any, max_length: int = 480) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _recent_failure_cutoff() -> str:
    window_minutes = escalation_failure_window_minutes()
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
    normalized = utc_naive_iso(cutoff)
    if normalized is None:
        raise RuntimeError("Escalation failure cutoff could not be normalized.")
    return normalized


def _cooldown_minutes() -> int:
    raw_value = str(os.environ.get("ALERT_ESCALATION_COOLDOWN_MINUTES") or DEFAULT_ESCALATION_COOLDOWN_MINUTES).strip()
    try:
        minutes = int(raw_value)
    except Exception:
        minutes = DEFAULT_ESCALATION_COOLDOWN_MINUTES
    return max(1, min(minutes, 1440))


def _cooldown_cutoff() -> str:
    cutoff = datetime.now(UTC) - timedelta(minutes=_cooldown_minutes())
    normalized = utc_naive_iso(cutoff)
    if normalized is None:
        raise RuntimeError("Escalation cooldown cutoff could not be normalized.")
    return normalized


def recent_failure_count(alert_key: str) -> int:
    cleaned_key = _safe_text(alert_key, 240)
    if not cleaned_key:
        return 0

    try:
        row = db_fetchone(
            """
            SELECT COUNT(1) AS failure_count
            FROM system_alert_delivery_logs
            WHERE alert_key = %s
              AND delivery_status = %s
              AND created_at >= %s
            """,
            (cleaned_key, "error", _recent_failure_cutoff()),
        )
    except Exception:
        return 0

    if not row:
        return 0

    if isinstance(row, dict):
        return int(row.get("failure_count") or 0)

    return int(row[0] or 0)


def escalation_is_acknowledged(alert_key: str) -> bool:
    cleaned_key = _safe_text(alert_key, 240)
    if not cleaned_key:
        return False

    try:
        row = db_fetchone(
            """
            SELECT id, acknowledged_at, status
            FROM system_alerts
            WHERE alert_key = %s
              AND status = %s
            ORDER BY id DESC
            LIMIT 1
            """,
            (cleaned_key, "open"),
        )
    except Exception:
        return False

    if not row:
        return False

    acknowledged_at = row.get("acknowledged_at") if isinstance(row, dict) else row[1]
    return bool(_safe_text(acknowledged_at, 120))


def escalation_recently_sent(alert_key: str, level: str) -> bool:
    cleaned_key = _safe_text(alert_key, 240)
    cleaned_level = _safe_text(level, 80)
    if not cleaned_key or not cleaned_level:
        return False

    try:
        row = db_fetchone(
            """
            SELECT COUNT(1) AS recent_count
            FROM system_alert_delivery_logs
            WHERE alert_key = %s
              AND channel = %s
              AND delivery_status = %s
              AND metadata LIKE %s
              AND created_at >= %s
            """,
            (
                cleaned_key,
                "escalation",
                "success",
                f'%"level": "{cleaned_level}"%',
                _cooldown_cutoff(),
            ),
        )
    except Exception:
        return False

    if not row:
        return False

    if isinstance(row, dict):
        return int(row.get("recent_count") or 0) > 0

    return int(row[0] or 0) > 0


def _send_sms_escalation(recipient: str, message: str) -> bool:
    try:
        from core.sms_sender import send_sms
    except Exception:
        return False

    try:
        return bool(send_sms(recipient, message, enforce_consent=False))
    except Exception:
        return False


def _send_escalation_target(target, message: str) -> bool:
    if target.channel == "sms":
        return _send_sms_escalation(target.recipient, message)

    return False


def handle_alert_escalation(
    *,
    alert: dict[str, Any],
    results: dict[str, bool],
    log_delivery: LogDeliveryFn,
) -> None:
    if not escalation_enabled():
        return

    if any(bool(value) for value in (results or {}).values()):
        return

    alert_key = _safe_text(alert.get("alert_key"), 240)
    if not alert_key:
        return

    if escalation_is_acknowledged(alert_key):
        log_delivery(
            channel="escalation",
            status="suppressed",
            alert=alert,
            message="Alert escalation suppressed because the alert has been acknowledged.",
            metadata={"alert_key": alert_key},
        )
        return

    failure_count = recent_failure_count(alert_key)
    level = escalation_level_for_failure_count(failure_count)
    if not level:
        return

    if escalation_recently_sent(alert_key, level):
        log_delivery(
            channel="escalation",
            status="suppressed",
            alert=alert,
            message=f"Alert escalation {level} suppressed because it is inside the cooldown window.",
            metadata={
                "failure_count": failure_count,
                "level": level,
                "cooldown_minutes": _cooldown_minutes(),
            },
        )
        return

    targets = build_escalation_targets(level)
    if not targets:
        log_delivery(
            channel="escalation",
            status="skipped",
            alert=alert,
            message=f"Alert escalation level {level} matched, but no escalation recipients are configured.",
            metadata={"failure_count": failure_count, "level": level},
        )
        return

    message = _safe_text(
        f"[ESCALATION {level.upper()}] {_safe_text(alert.get('title'), 160)}: {_safe_text(alert.get('message'), 260)}",
        480,
    )

    sent_count = 0
    failed_count = 0

    for target in targets:
        if _send_escalation_target(target, message):
            sent_count += 1
        else:
            failed_count += 1

    status = "success" if sent_count else "error"
    log_delivery(
        channel="escalation",
        status=status,
        alert=alert,
        message=f"Alert escalation {level} processed.",
        metadata={
            "failure_count": failure_count,
            "level": level,
            "target_count": len(targets),
            "sent_count": sent_count,
            "failed_count": failed_count,
            "cooldown_minutes": _cooldown_minutes(),
        },
    )
