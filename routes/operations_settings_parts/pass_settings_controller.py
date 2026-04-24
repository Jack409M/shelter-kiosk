from __future__ import annotations

from core.db import db_execute
from core.helpers import utcnow_iso

from .parsing import _merge_bool, _merge_int, _merge_text
from .settings_store import (
    _default_pass_gh_rules_text,
    _default_pass_level_rules_text,
    _default_pass_shared_rules_text,
    _placeholder,
)


def _bool_db(value: bool, is_pg: bool):
    return value if is_pg else (1 if value else 0)


def save_pass_settings(shelter: str, row: dict, form) -> None:
    now = utcnow_iso()
    is_pg = _placeholder() == "%s"

    pass_deadline_weekday = min(
        max(
            _merge_int(
                "pass_deadline_weekday",
                form,
                row.get("pass_deadline_weekday"),
                0,
            ),
            0,
        ),
        6,
    )
    pass_deadline_hour = min(
        max(
            _merge_int(
                "pass_deadline_hour",
                form,
                row.get("pass_deadline_hour"),
                8,
            ),
            0,
        ),
        23,
    )
    pass_deadline_minute = min(
        max(
            _merge_int(
                "pass_deadline_minute",
                form,
                row.get("pass_deadline_minute"),
                0,
            ),
            0,
        ),
        59,
    )
    pass_late_submission_block_enabled = _merge_bool(
        "pass_late_submission_block_enabled",
        form,
        row.get("pass_late_submission_block_enabled"),
        True,
    )
    pass_work_required_hours = max(
        _merge_int(
            "pass_work_required_hours",
            form,
            row.get("pass_work_required_hours"),
            29,
        ),
        0,
    )
    pass_productive_required_hours = max(
        _merge_int(
            "pass_productive_required_hours",
            form,
            row.get("pass_productive_required_hours"),
            35,
        ),
        0,
    )
    special_pass_bypass_hours_enabled = _merge_bool(
        "special_pass_bypass_hours_enabled",
        form,
        row.get("special_pass_bypass_hours_enabled"),
        True,
    )

    pass_shared_rules_text = (
        _merge_text(
            "pass_shared_rules_text",
            form,
            row.get("pass_shared_rules_text"),
            _default_pass_shared_rules_text(),
        )
        or _default_pass_shared_rules_text()
    )

    pass_gh_rules_text = (
        _merge_text(
            "pass_gh_rules_text",
            form,
            row.get("pass_gh_rules_text"),
            _default_pass_gh_rules_text(),
        )
        or _default_pass_gh_rules_text()
    )

    pass_level_1_rules_text = _merge_text(
        "pass_level_1_rules_text",
        form,
        row.get("pass_level_1_rules_text"),
        _default_pass_level_rules_text("pass_level_1_rules_text"),
    ) or _default_pass_level_rules_text("pass_level_1_rules_text")

    pass_level_2_rules_text = _merge_text(
        "pass_level_2_rules_text",
        form,
        row.get("pass_level_2_rules_text"),
        _default_pass_level_rules_text("pass_level_2_rules_text"),
    ) or _default_pass_level_rules_text("pass_level_2_rules_text")

    pass_level_3_rules_text = _merge_text(
        "pass_level_3_rules_text",
        form,
        row.get("pass_level_3_rules_text"),
        _default_pass_level_rules_text("pass_level_3_rules_text"),
    ) or _default_pass_level_rules_text("pass_level_3_rules_text")

    pass_level_4_rules_text = _merge_text(
        "pass_level_4_rules_text",
        form,
        row.get("pass_level_4_rules_text"),
        _default_pass_level_rules_text("pass_level_4_rules_text"),
    ) or _default_pass_level_rules_text("pass_level_4_rules_text")

    pass_gh_level_5_rules_text = _merge_text(
        "pass_gh_level_5_rules_text",
        form,
        row.get("pass_gh_level_5_rules_text"),
        _default_pass_level_rules_text("pass_gh_level_5_rules_text"),
    ) or _default_pass_level_rules_text("pass_gh_level_5_rules_text")

    pass_gh_level_6_rules_text = _merge_text(
        "pass_gh_level_6_rules_text",
        form,
        row.get("pass_gh_level_6_rules_text"),
        _default_pass_level_rules_text("pass_gh_level_6_rules_text"),
    ) or _default_pass_level_rules_text("pass_gh_level_6_rules_text")

    pass_gh_level_7_rules_text = _merge_text(
        "pass_gh_level_7_rules_text",
        form,
        row.get("pass_gh_level_7_rules_text"),
        _default_pass_level_rules_text("pass_gh_level_7_rules_text"),
    ) or _default_pass_level_rules_text("pass_gh_level_7_rules_text")

    pass_gh_level_8_rules_text = _merge_text(
        "pass_gh_level_8_rules_text",
        form,
        row.get("pass_gh_level_8_rules_text"),
        _default_pass_level_rules_text("pass_gh_level_8_rules_text"),
    ) or _default_pass_level_rules_text("pass_gh_level_8_rules_text")

    db_execute(
        """
        UPDATE shelter_operation_settings
        SET pass_deadline_weekday = %s,
            pass_deadline_hour = %s,
            pass_deadline_minute = %s,
            pass_late_submission_block_enabled = %s,
            pass_work_required_hours = %s,
            pass_productive_required_hours = %s,
            special_pass_bypass_hours_enabled = %s,
            pass_shared_rules_text = %s,
            pass_gh_rules_text = %s,
            pass_level_1_rules_text = %s,
            pass_level_2_rules_text = %s,
            pass_level_3_rules_text = %s,
            pass_level_4_rules_text = %s,
            pass_gh_level_5_rules_text = %s,
            pass_gh_level_6_rules_text = %s,
            pass_gh_level_7_rules_text = %s,
            pass_gh_level_8_rules_text = %s,
            updated_at = %s
        WHERE LOWER(COALESCE(shelter, '')) = %s
        """
        if is_pg
        else """
        UPDATE shelter_operation_settings
        SET pass_deadline_weekday = ?,
            pass_deadline_hour = ?,
            pass_deadline_minute = ?,
            pass_late_submission_block_enabled = ?,
            pass_work_required_hours = ?,
            pass_productive_required_hours = ?,
            special_pass_bypass_hours_enabled = ?,
            pass_shared_rules_text = ?,
            pass_gh_rules_text = ?,
            pass_level_1_rules_text = ?,
            pass_level_2_rules_text = ?,
            pass_level_3_rules_text = ?,
            pass_level_4_rules_text = ?,
            pass_gh_level_5_rules_text = ?,
            pass_gh_level_6_rules_text = ?,
            pass_gh_level_7_rules_text = ?,
            pass_gh_level_8_rules_text = ?,
            updated_at = ?
        WHERE LOWER(COALESCE(shelter, '')) = ?
        """,
        (
            pass_deadline_weekday,
            pass_deadline_hour,
            pass_deadline_minute,
            _bool_db(pass_late_submission_block_enabled, is_pg),
            pass_work_required_hours,
            pass_productive_required_hours,
            _bool_db(special_pass_bypass_hours_enabled, is_pg),
            pass_shared_rules_text,
            pass_gh_rules_text,
            pass_level_1_rules_text,
            pass_level_2_rules_text,
            pass_level_3_rules_text,
            pass_level_4_rules_text,
            pass_gh_level_5_rules_text,
            pass_gh_level_6_rules_text,
            pass_gh_level_7_rules_text,
            pass_gh_level_8_rules_text,
            now,
            shelter,
        ),
    )
