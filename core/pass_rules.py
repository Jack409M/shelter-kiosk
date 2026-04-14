from __future__ import annotations

from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import g

from core.db import db_fetchone

CHICAGO_TZ = ZoneInfo("America/Chicago")


def normalize_shelter(value: str | None) -> str:
    return (value or "").strip().lower()


def parse_level_number(value: str | None) -> int | None:
    text = (value or "").strip().lower()
    if not text:
        return None

    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None

    try:
        return int(digits)
    except Exception:
        return None


def is_gh_level(level_value: str | None) -> bool:
    level_num = parse_level_number(level_value)
    return bool(level_num and level_num >= 5)


def use_gh_pass_form(shelter: str | None, level_value: str | None) -> bool:
    shelter_key = normalize_shelter(shelter)
    if shelter_key == "gratitude":
        return True
    return is_gh_level(level_value)


def pass_type_options() -> list[tuple[str, str]]:
    return [
        ("pass", "Pass"),
        ("overnight", "Overnight Pass"),
        ("special", "Special Pass"),
    ]


def pass_type_label(value: str | None) -> str:
    lookup = dict(pass_type_options())
    return lookup.get((value or "").strip().lower(), (value or "").strip() or "Pass")


def _db_placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


def _row_value(row, key: str, default=None):
    if not row:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _default_pass_settings() -> dict:
    return {
        "pass_deadline_weekday": 0,
        "pass_deadline_hour": 8,
        "pass_deadline_minute": 0,
        "pass_late_submission_block_enabled": True,
        "pass_work_required_hours": 29,
        "pass_productive_required_hours": 35,
        "special_pass_bypass_hours_enabled": True,
        "pass_shared_rules_text": "\n".join(
            [
                "Pass requests are due by Monday at 8:00 a.m.",
                "Passes are not automatic.",
                "Free time is handled as a normal Pass.",
                "Special Pass is for funerals or similar serious situations.",
                "Special Pass requests are reviewed as exceptions.",
            ]
        ),
        "pass_gh_rules_text": "\n".join(
            [
                "Pass requests are due by Monday at 8:00 a.m.",
                "Passes are not automatic.",
                "Free time is handled as a normal Pass.",
                "Special Pass is for funerals or similar serious situations.",
                "Special Pass requests are reviewed as exceptions.",
                "Special Pass does not depend on productive hours in the same way as a normal pass.",
            ]
        ),
        "pass_level_1_rules_text": "\n".join(
            [
                "Level 1 residents do not get friend or family passes.",
                "Passes are not given until completion of RAD unless special circumstances exist.",
            ]
        ),
        "pass_level_2_rules_text": "\n".join(
            [
                "Level 2 residents may have one weekly pass up to 4 hours.",
                "Normal passes require obligations to be met first.",
                "Normal passes require 29 work hours and 35 productive hours before approval.",
            ]
        ),
        "pass_level_3_rules_text": "\n".join(
            [
                "Level 3 residents may request normal passes within shelter rules.",
                "Normal passes still depend on rules, behavior, and required hours.",
            ]
        ),
        "pass_level_4_rules_text": "\n".join(
            [
                "Level 4 residents may request normal passes.",
                "Level 4 residents may have one overnight pass per month with approval.",
            ]
        ),
        "pass_gh_level_5_rules_text": "\n".join(
            [
                "No overnight passes during the first 30 days unless an exception is approved.",
                "Level 5 may have one overnight pass per month after the first 30 days.",
            ]
        ),
        "pass_gh_level_6_rules_text": "Level 6 may have two overnight passes per month.",
        "pass_gh_level_7_rules_text": "Level 7 may have three overnight passes per month.",
        "pass_gh_level_8_rules_text": "Level 8 may have three passes per month with permission.",
    }


def _coerce_bool(value, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _coerce_int(value, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
    try:
        number = int(value)
    except Exception:
        number = default

    if minimum is not None and number < minimum:
        number = minimum
    if maximum is not None and number > maximum:
        number = maximum
    return number


def _split_rule_text(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def load_pass_settings_for_shelter(shelter: str | None) -> dict:
    defaults = _default_pass_settings()
    shelter_key = normalize_shelter(shelter)
    if not shelter_key:
        return defaults

    ph = _db_placeholder()
    try:
        row = db_fetchone(
            f"""
            SELECT
                pass_deadline_weekday,
                pass_deadline_hour,
                pass_deadline_minute,
                pass_late_submission_block_enabled,
                pass_work_required_hours,
                pass_productive_required_hours,
                special_pass_bypass_hours_enabled,
                pass_shared_rules_text,
                pass_gh_rules_text,
                pass_level_1_rules_text,
                pass_level_2_rules_text,
                pass_level_3_rules_text,
                pass_level_4_rules_text,
                pass_gh_level_5_rules_text,
                pass_gh_level_6_rules_text,
                pass_gh_level_7_rules_text,
                pass_gh_level_8_rules_text
            FROM shelter_operation_settings
            WHERE LOWER(COALESCE(shelter, '')) = {ph}
            LIMIT 1
            """,
            (shelter_key,),
        )
    except Exception:
        return defaults

    if not row:
        return defaults

    merged = dict(defaults)
    merged["pass_deadline_weekday"] = _coerce_int(
        _row_value(row, "pass_deadline_weekday", defaults["pass_deadline_weekday"]),
        defaults["pass_deadline_weekday"],
        0,
        6,
    )
    merged["pass_deadline_hour"] = _coerce_int(
        _row_value(row, "pass_deadline_hour", defaults["pass_deadline_hour"]),
        defaults["pass_deadline_hour"],
        0,
        23,
    )
    merged["pass_deadline_minute"] = _coerce_int(
        _row_value(row, "pass_deadline_minute", defaults["pass_deadline_minute"]),
        defaults["pass_deadline_minute"],
        0,
        59,
    )
    merged["pass_late_submission_block_enabled"] = _coerce_bool(
        _row_value(
            row,
            "pass_late_submission_block_enabled",
            defaults["pass_late_submission_block_enabled"],
        ),
        defaults["pass_late_submission_block_enabled"],
    )
    merged["pass_work_required_hours"] = _coerce_int(
        _row_value(row, "pass_work_required_hours", defaults["pass_work_required_hours"]),
        defaults["pass_work_required_hours"],
        0,
        None,
    )
    merged["pass_productive_required_hours"] = _coerce_int(
        _row_value(
            row, "pass_productive_required_hours", defaults["pass_productive_required_hours"]
        ),
        defaults["pass_productive_required_hours"],
        0,
        None,
    )
    merged["special_pass_bypass_hours_enabled"] = _coerce_bool(
        _row_value(
            row, "special_pass_bypass_hours_enabled", defaults["special_pass_bypass_hours_enabled"]
        ),
        defaults["special_pass_bypass_hours_enabled"],
    )

    text_keys = [
        "pass_shared_rules_text",
        "pass_gh_rules_text",
        "pass_level_1_rules_text",
        "pass_level_2_rules_text",
        "pass_level_3_rules_text",
        "pass_level_4_rules_text",
        "pass_gh_level_5_rules_text",
        "pass_gh_level_6_rules_text",
        "pass_gh_level_7_rules_text",
        "pass_gh_level_8_rules_text",
    ]
    for key in text_keys:
        raw_value = _row_value(row, key, defaults[key])
        merged[key] = (raw_value or defaults[key] or "").strip()

    return merged


def standard_pass_deadline_for_leave(
    leave_local_dt: datetime, shelter: str | None = None
) -> datetime:
    settings = load_pass_settings_for_shelter(shelter)
    target_weekday = settings["pass_deadline_weekday"]
    delta_days = leave_local_dt.weekday() - target_weekday
    deadline_date = leave_local_dt.date() - timedelta(days=delta_days)
    return datetime.combine(
        deadline_date,
        time(
            hour=settings["pass_deadline_hour"],
            minute=settings["pass_deadline_minute"],
        ),
        tzinfo=CHICAGO_TZ,
    )


def is_late_standard_pass_request(
    submitted_local_dt: datetime,
    leave_local_dt: datetime,
    shelter: str | None = None,
) -> bool:
    deadline = standard_pass_deadline_for_leave(leave_local_dt, shelter=shelter)
    return submitted_local_dt > deadline


def pass_late_submission_block_enabled(shelter: str | None = None) -> bool:
    settings = load_pass_settings_for_shelter(shelter)
    return bool(settings["pass_late_submission_block_enabled"])


def pass_required_hours(shelter: str | None = None) -> dict:
    settings = load_pass_settings_for_shelter(shelter)
    return {
        "work_required_hours": settings["pass_work_required_hours"],
        "productive_required_hours": settings["pass_productive_required_hours"],
    }


def special_pass_bypass_hours_enabled(shelter: str | None = None) -> bool:
    settings = load_pass_settings_for_shelter(shelter)
    return bool(settings["special_pass_bypass_hours_enabled"])


def shared_pass_rule_box(shelter: str | None, level_value: str | None) -> dict:
    settings = load_pass_settings_for_shelter(shelter)
    level_num = parse_level_number(level_value)

    lines: list[str] = []
    lines.extend(_split_rule_text(settings["pass_shared_rules_text"]))

    if level_num == 1:
        lines.extend(_split_rule_text(settings["pass_level_1_rules_text"]))
    elif level_num == 2:
        lines.extend(_split_rule_text(settings["pass_level_2_rules_text"]))
    elif level_num == 3:
        lines.extend(_split_rule_text(settings["pass_level_3_rules_text"]))
    elif level_num == 4:
        lines.extend(_split_rule_text(settings["pass_level_4_rules_text"]))
    else:
        lines.append("Haven and Abba rules will be reviewed by staff for this request.")

    return {
        "title": "Pass Rules",
        "lines": lines,
    }


def gh_pass_rule_box(shelter: str | None, level_value: str | None) -> dict:
    settings = load_pass_settings_for_shelter(shelter)
    level_num = parse_level_number(level_value)

    lines: list[str] = []
    lines.extend(_split_rule_text(settings["pass_gh_rules_text"]))

    if level_num == 5:
        lines.extend(_split_rule_text(settings["pass_gh_level_5_rules_text"]))
    elif level_num == 6:
        lines.extend(_split_rule_text(settings["pass_gh_level_6_rules_text"]))
    elif level_num == 7:
        lines.extend(_split_rule_text(settings["pass_gh_level_7_rules_text"]))
    elif level_num == 8:
        lines.extend(_split_rule_text(settings["pass_gh_level_8_rules_text"]))
    else:
        lines.append("Gratitude House staff will review this request under GH rules.")

    return {
        "title": "Gratitude House Pass Rules",
        "lines": lines,
    }
