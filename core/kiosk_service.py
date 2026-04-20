from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from datetime import date as date_cls
from datetime import time as time_cls
from typing import Any, Final
from zoneinfo import ZoneInfo

from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import utcnow_iso

CHICAGO_TZ: Final[ZoneInfo] = ZoneInfo("America/Chicago")
UTC: Final[timezone] = UTC


@dataclass(slots=True)
class CheckinResult:
    success: bool
    status_code: int
    errors: list[str] = field(default_factory=list)
    actual_end_required: bool = False
    prior_activity_label: str = ""
    resident_id: int | None = None
    log_note: str = ""
    needs_actual_end_prompt: bool = False


@dataclass(slots=True)
class CheckoutResult:
    success: bool
    status_code: int
    errors: list[str] = field(default_factory=list)
    resident_id: int | None = None
    destination_value: str = ""
    selected_activity_key: str = ""
    aa_na_meeting_1: str = ""
    aa_na_meeting_2: str = ""
    meeting_count: int = 0
    is_recovery_meeting_value: int = 0
    volunteer_community_service_option: str = ""
    child_option_value: str = ""
    obligation_start_value: str | None = None
    obligation_end_value: str | None = None
    expected_back_value: str | None = None

# ... unchanged code above ...

    if is_aa_na_meeting:
        if not aa_na_meeting_1:
            errors.append("Meeting 1 is required for AA or NA Meeting.")
        elif aa_na_meeting_1 not in selected_child_option_labels:
            errors.append("Please select a valid Meeting 1 option.")

        if aa_na_meeting_2 and aa_na_meeting_2 not in selected_child_option_labels:
            errors.append("Please select a valid Meeting 2 option.")

        if aa_na_meeting_1 and aa_na_meeting_2 and aa_na_meeting_1 == aa_na_meeting_2:
            errors.append("Meeting 1 and Meeting 2 cannot be the same.")

    elif has_generic_child_options and not is_volunteer_community_service:
        if not normalized_child_option_value:
            errors.append("Activity detail is required.")
        elif normalized_child_option_value not in selected_child_option_labels:
            errors.append("Please select a valid activity detail option.")

# ... rest unchanged ...
