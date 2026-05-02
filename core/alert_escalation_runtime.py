from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

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
    return utc_naive_iso(cutoff)


def _cooldown_minutes() -> int:
    raw_value = str(os.environ.get("ALERT_ESCALATION_COOLDOWN_MINUTES") or DEFAULT_ESCALATION_COOLDOWN_MINUTES).strip()
    try:
        minutes = int(raw_value)
    except Exception:
        minutes = DEFAULT_ESCALATION_COOLDOWN_MINUTES
    return max(1, min(minutes, 1440))


def _cooldown_cutoff() -> str:
    cutoff = datetime.now(UTC) - timedelta(minutes=_cooldown_minutes())
    return utc_naive_iso(cutoff)

# rest unchanged
