from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


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


def standard_pass_deadline_for_leave(leave_local_dt: datetime) -> datetime:
    monday = leave_local_dt.date() - timedelta(days=leave_local_dt.weekday())
    return datetime.combine(monday, time(hour=8, minute=0), tzinfo=CHICAGO_TZ)


def is_late_standard_pass_request(submitted_local_dt: datetime, leave_local_dt: datetime) -> bool:
    deadline = standard_pass_deadline_for_leave(leave_local_dt)
    return submitted_local_dt > deadline


def shared_pass_rule_box(level_value: str | None) -> dict:
    level_num = parse_level_number(level_value)
    lines: list[str] = [
        "Pass requests are due by Monday at 8:00 a.m.",
        "Passes are not automatic.",
        "Free time is handled as a normal Pass.",
    ]

    if level_num == 1:
        lines.extend(
            [
                "Level 1 residents do not get friend or family passes.",
                "Passes are not given until completion of RAD unless special circumstances exist.",
            ]
        )
    elif level_num == 2:
        lines.extend(
            [
                "Level 2 residents may have one weekly pass up to 4 hours.",
                "Normal passes require obligations to be met first.",
                "Normal passes require 29 work hours and 35 productive hours before approval.",
            ]
        )
    elif level_num == 3:
        lines.extend(
            [
                "Level 3 residents may request normal passes within shelter rules.",
                "Normal passes still depend on rules, behavior, and required hours.",
            ]
        )
    elif level_num == 4:
        lines.extend(
            [
                "Level 4 residents may request normal passes.",
                "Level 4 residents may have one overnight pass per month with approval.",
            ]
        )
    else:
        lines.append("Haven and Abba rules will be reviewed by staff for this request.")

    lines.extend(
        [
            "Special Pass is for funerals or similar serious situations.",
            "Special Pass requests are reviewed as exceptions.",
        ]
    )

    return {
        "title": "Pass Rules",
        "lines": lines,
    }


def gh_pass_rule_box(level_value: str | None) -> dict:
    level_num = parse_level_number(level_value)
    lines: list[str] = [
        "Pass requests are due by Monday at 8:00 a.m.",
        "Passes are not automatic.",
        "Free time is handled as a normal Pass.",
        "Special Pass is for funerals or similar serious situations.",
    ]

    if level_num == 5:
        lines.extend(
            [
                "No overnight passes during the first 30 days unless an exception is approved.",
                "Level 5 may have one overnight pass per month after the first 30 days.",
            ]
        )
    elif level_num == 6:
        lines.append("Level 6 may have two overnight passes per month.")
    elif level_num == 7:
        lines.append("Level 7 may have three overnight passes per month.")
    elif level_num == 8:
        lines.append("Level 8 may have three passes per month with permission.")
    else:
        lines.append("Gratitude House staff will review this request under GH rules.")

    lines.append("Special Pass does not depend on productive hours in the same way as a normal pass.")

    return {
        "title": "Gratitude House Pass Rules",
        "lines": lines,
    }
