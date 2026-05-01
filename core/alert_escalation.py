from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

TRUTHY_ENV_VALUES = {"1", "true", "yes", "on"}
FALSEY_ENV_VALUES = {"0", "false", "no", "off"}
DEFAULT_FAILURE_WINDOW_MINUTES = 60
DEFAULT_ESCALATION_THRESHOLDS = {
    3: "tier_1",
    5: "tier_2",
    8: "tier_3",
}


@dataclass(frozen=True)
class EscalationTarget:
    level: str
    channel: str
    recipient: str


def _env(name: str, default: str = "") -> str:
    return str(os.environ.get(name) or default).strip()


def _env_enabled(name: str, default: str = "true") -> bool:
    value = _env(name, default).lower()
    if value in FALSEY_ENV_VALUES:
        return False
    if value in TRUTHY_ENV_VALUES:
        return True
    return default.lower() in TRUTHY_ENV_VALUES


def _split(value: str) -> list[str]:
    items: list[str] = []
    for part in str(value or "").replace(";", ",").split(","):
        cleaned = part.strip()
        if cleaned and cleaned not in items:
            items.append(cleaned)
    return items


def escalation_enabled() -> bool:
    return _env_enabled("ALERT_ESCALATION_ENABLED", "true")


def escalation_failure_window_minutes() -> int:
    raw_value = _env("ALERT_ESCALATION_WINDOW_MINUTES", str(DEFAULT_FAILURE_WINDOW_MINUTES))
    try:
        minutes = int(raw_value)
    except Exception:
        minutes = DEFAULT_FAILURE_WINDOW_MINUTES
    return max(5, min(minutes, 1440))


def escalation_thresholds() -> dict[int, str]:
    raw_value = _env("ALERT_ESCALATION_THRESHOLDS")
    if not raw_value:
        return dict(DEFAULT_ESCALATION_THRESHOLDS)

    parsed: dict[int, str] = {}
    for entry in raw_value.split(","):
        if ":" not in entry:
            continue
        threshold_raw, level_raw = entry.split(":", 1)
        level = level_raw.strip().lower()
        try:
            threshold = int(threshold_raw.strip())
        except Exception:
            continue
        if threshold > 0 and level:
            parsed[threshold] = level

    return parsed or dict(DEFAULT_ESCALATION_THRESHOLDS)


def escalation_level_for_failure_count(failure_count: int) -> str:
    matched_level = ""
    for threshold, level in sorted(escalation_thresholds().items()):
        if failure_count >= threshold:
            matched_level = level
    return matched_level


def escalation_recipients(level: str) -> list[str]:
    normalized_level = str(level or "").strip().upper()
    if not normalized_level:
        return []
    return _split(_env(f"ALERT_ESCALATION_{normalized_level}_RECIPIENTS"))


def escalation_channels(level: str) -> list[str]:
    normalized_level = str(level or "").strip().upper()
    configured = _split(_env(f"ALERT_ESCALATION_{normalized_level}_CHANNELS"))
    channels = [channel.lower() for channel in configured if channel.lower() in {"email", "sms", "webhook"}]
    return channels or ["sms"]


def build_escalation_targets(level: str) -> list[EscalationTarget]:
    targets: list[EscalationTarget] = []
    recipients = escalation_recipients(level)
    channels = escalation_channels(level)

    for channel in channels:
        for recipient in recipients:
            targets.append(EscalationTarget(level=level, channel=channel, recipient=recipient))

    return targets


def escalation_summary() -> dict[str, Any]:
    thresholds = escalation_thresholds()
    return {
        "enabled": escalation_enabled(),
        "failure_window_minutes": escalation_failure_window_minutes(),
        "thresholds": thresholds,
        "levels": sorted(set(thresholds.values())),
    }
