from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from core.alert_escalation import (
    build_escalation_targets,
    escalation_enabled,
    escalation_failure_window_minutes,
    escalation_level_for_failure_count,
)
from core.db import db_fetchone

LogDeliveryFn = Callable[..., None]


def _safe_text(value: Any, max_length: int = 480) -> str:
    text = str(value or "").strip()
    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def _recent_failure_cutoff() -> str:
    window_minutes = escalation_failure_window_minutes()
    cutoff = datetime.now(UTC) - timedelta(minutes=window_minutes)
    return cutoff.isoformat(timespec="seconds")


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

    failure_count = recent_failure_count(alert_key)
    level = escalation_level_for_failure_count(failure_count)
    if not level:
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
        },
    )
