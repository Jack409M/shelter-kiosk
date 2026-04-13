from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from flask import g

from core.db import db_fetchall, db_fetchone
from core.pass_rules import (
    gh_pass_rule_box,
    load_pass_settings_for_shelter,
    pass_required_hours,
    pass_type_label,
    shared_pass_rule_box,
    standard_pass_deadline_for_leave,
    use_gh_pass_form,
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def resident_value(row, key: str, index: int, default=""):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def load_resident_pass_profile(resident_id: int):
    return db_fetchone(
        """
        SELECT
            id,
            shelter,
            program_level,
            sponsor_name,
            sponsor_active,
            step_current,
            step_work_active,
            monthly_income,
            date_entered
        FROM residents
        WHERE id = %s
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            id,
            shelter,
            program_level,
            sponsor_name,
            sponsor_active,
            step_current,
            step_work_active,
            monthly_income,
            date_entered
        FROM residents
        WHERE id = ?
        LIMIT 1
        """,
        (resident_id,),
    )


def _deadline_detail_text(deadline_local, settings: dict) -> str:
    weekday_lookup = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }
    weekday_name = weekday_lookup.get(settings.get("pass_deadline_weekday", 0), "Monday")
    time_label = deadline_local.strftime("%I:%M %p").lstrip("0")
    return f"Configured deadline is {weekday_name} at {time_label}. Actual deadline for this pass was {deadline_local.strftime('%B %d, %Y %I:%M %p')}."


def _parse_level_number(value: str | None) -> int | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    digits = "".join(ch for ch in text if ch.isdigit())
    if not digits:
        return None
    try:
        return int(digits)
    except Exception:
        return None


def _meeting_status_class_for_summary(meeting_summary: dict | None) -> str:
    if not meeting_summary:
        return "fail"
    if meeting_summary.get("completed_90_in_90"):
        return "pass"
    if meeting_summary.get("status_label") == "On Pace for 90 in 90":
        return "pass"
    return "fail"


def _today_chicago_date() -> date:
    return datetime.now(CHICAGO_TZ).date()


def _parse_date_only(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text[:10]).date()
    except Exception:
        return None


def _status_is_open_for_discipline(value: str | None) -> bool:
    return str(value or "").strip().lower() == "open"


def _load_active_writeup_restrictions(resident_id: int) -> list[dict]:
    rows = db_fetchall(
        """
        SELECT
            id,
            incident_date,
            category,
            severity,
            summary,
            status,
            disciplinary_outcome,
            probation_start_date,
            probation_end_date,
            pre_termination_date,
            blocks_passes
        FROM resident_writeups
        WHERE resident_id = %s
          AND blocks_passes IS TRUE
        ORDER BY incident_date DESC, id DESC
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            id,
            incident_date,
            category,
            severity,
            summary,
            status,
            disciplinary_outcome,
            probation_start_date,
            probation_end_date,
            pre_termination_date,
            blocks_passes
        FROM resident_writeups
        WHERE resident_id = ?
          AND COALESCE(blocks_passes, 0) = 1
        ORDER BY incident_date DESC, id DESC
        """,
        (resident_id,),
    )

    today = _today_chicago_date()
    active: list[dict] = []

    for row in rows:
        item = dict(row)
        outcome = str(item.get("disciplinary_outcome") or "").strip().lower()
        status = str(item.get("status") or "").strip()
        is_open = _status_is_open_for_discipline(status)

        if outcome == "program_probation":
            start_date = _parse_date_only(item.get("probation_start_date"))
            end_date = _parse_date_only(item.get("probation_end_date"))
            is_active = bool(
                is_open and start_date and end_date and start_date <= today <= end_date
            )
            if is_active:
                item["restriction_label"] = "Program Probation"
                item["restriction_detail"] = (
                    f"{item.get('probation_start_date') or '—'} to {item.get('probation_end_date') or '—'}"
                )
                active.append(item)

        elif outcome == "pre_termination":
            scheduled_date = _parse_date_only(item.get("pre_termination_date"))
            is_active = bool(is_open and scheduled_date and today <= scheduled_date)
            if is_active:
                item["restriction_label"] = "Pre Termination Scheduled"
                item["restriction_detail"] = (
                    f"Scheduled for {item.get('pre_termination_date') or '—'}"
                )
                active.append(item)

    return active


def has_active_pass_block(resident_id: int) -> tuple[bool, list[dict]]:
    restrictions = _load_active_writeup_restrictions(resident_id)
    return (len(restrictions) > 0, restrictions)


def build_policy_check(
    pass_row: dict, pass_detail: dict | None, hour_summary, meeting_summary=None
):
    resident_id = int(pass_row.get("resident_id") or 0)
    resident_profile = load_resident_pass_profile(resident_id) if resident_id else None

    resident_level = ""
    if pass_detail and pass_detail.get("resident_level"):
        resident_level = str(pass_detail.get("resident_level") or "").strip()
    elif resident_profile:
        resident_level = str(resident_value(resident_profile, "program_level", 2, "") or "").strip()

    shelter = str(pass_row.get("shelter") or "").strip()
    settings = load_pass_settings_for_shelter(shelter)
    required_hours = pass_required_hours(shelter)
    use_gh = use_gh_pass_form(shelter, resident_level)

    rule_box = (
        gh_pass_rule_box(shelter, resident_level)
        if use_gh
        else shared_pass_rule_box(shelter, resident_level)
    )
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()
    pass_type_text = pass_type_label(pass_type_key)

    checks: list[dict] = []

    has_block, restriction_rows = has_active_pass_block(resident_id)
    if has_block:
        for restriction in restriction_rows:
            checks.append(
                {
                    "label": restriction.get("restriction_label") or "Disciplinary Restriction",
                    "value": "Passes denied",
                    "status_class": "fail",
                    "detail": restriction.get("restriction_detail")
                    or restriction.get("summary")
                    or "",
                }
            )

    if pass_type_key in {"pass", "overnight"}:
        start_local = pass_row.get("start_at_local")
        if start_local:
            deadline_local = standard_pass_deadline_for_leave(start_local, shelter=shelter)
            created_local = pass_row.get("created_at_local")
            submitted_on_time = bool(created_local and created_local <= deadline_local)

            checks.append(
                {
                    "label": "Deadline",
                    "value": "On time" if submitted_on_time else "Late",
                    "status_class": "pass" if submitted_on_time else "fail",
                    "detail": _deadline_detail_text(deadline_local, settings),
                }
            )

        if pass_type_key == "pass":
            same_day = bool(
                pass_row.get("start_at_local")
                and pass_row.get("end_at_local")
                and pass_row["start_at_local"].date() == pass_row["end_at_local"].date()
            )
            checks.append(
                {
                    "label": "Pass timing",
                    "value": "Same day" if same_day else "Not same day",
                    "status_class": "pass" if same_day else "fail",
                    "detail": "Pass should leave and return on the same day.",
                }
            )

        if pass_type_key == "overnight":
            overnight_ok = bool(
                pass_row.get("start_at_local")
                and pass_row.get("end_at_local")
                and pass_row["end_at_local"].date() > pass_row["start_at_local"].date()
            )
            checks.append(
                {
                    "label": "Overnight timing",
                    "value": "Overnight" if overnight_ok else "Not overnight",
                    "status_class": "pass" if overnight_ok else "fail",
                    "detail": "Overnight Pass should return on a later day.",
                }
            )

        requirements_ack = (pass_detail or {}).get("requirements_acknowledged")
        if requirements_ack:
            checks.append(
                {
                    "label": "Resident said obligations will be met",
                    "value": "Yes" if requirements_ack == "yes" else "No",
                    "status_class": "pass" if requirements_ack == "yes" else "fail",
                    "detail": (pass_detail or {}).get("requirements_not_met_explanation") or "",
                }
            )

        if hour_summary:
            productive_required = required_hours.get("productive_required_hours", 35)
            work_required = required_hours.get("work_required_hours", 29)
            productive_hours = hour_summary.get("productive_hours", 0)
            work_hours = hour_summary.get("work_hours", 0)

            meets_hours = (productive_hours >= productive_required) and (
                work_hours >= work_required
            )

            checks.append(
                {
                    "label": "Previous week hours",
                    "value": "Meets configured hours" if meets_hours else "Below configured hours",
                    "status_class": "pass" if meets_hours else "fail",
                    "detail": (
                        f"Productive {productive_hours} / {productive_required}"
                        f" • Work {work_hours} / {work_required}"
                    ),
                }
            )

        if meeting_summary:
            level_num = _parse_level_number(resident_level)
            shelter_key = shelter.strip().lower()

            if shelter_key == "haven":
                if not meeting_summary.get("completed_90_in_90"):
                    checks.append(
                        {
                            "label": "90 in 90",
                            "value": meeting_summary.get("status_label") or "Not Started",
                            "status_class": _meeting_status_class_for_summary(meeting_summary),
                            "detail": (
                                f"Meetings {meeting_summary.get('total_meetings', 0)} / 90"
                                f" • Days in program {meeting_summary.get('days_in_program', 0)}"
                                f" • Pace {meeting_summary.get('pace_percent_display', '0.0%')}"
                            ),
                        }
                    )
                else:
                    checks.append(
                        {
                            "label": "90 in 90",
                            "value": "Complete",
                            "status_class": "pass",
                            "detail": (
                                f"Meetings completed: {meeting_summary.get('total_meetings', 0)}"
                            ),
                        }
                    )

                if level_num == 3:
                    weekly_met = meeting_summary.get("weekly_requirement_met")
                    checks.append(
                        {
                            "label": "Weekly meeting requirement",
                            "value": "Meets Level 3 weekly requirement"
                            if weekly_met
                            else "Below Level 3 weekly requirement",
                            "status_class": "pass" if weekly_met else "fail",
                            "detail": (
                                f"This week {meeting_summary.get('meetings_this_week', 0)} / 6 meetings"
                            ),
                        }
                    )

                if level_num == 4:
                    weekly_met = meeting_summary.get("weekly_requirement_met")
                    checks.append(
                        {
                            "label": "Weekly meeting requirement",
                            "value": "Meets Level 4 weekly requirement"
                            if weekly_met
                            else "Below Level 4 weekly requirement",
                            "status_class": "pass" if weekly_met else "fail",
                            "detail": (
                                f"This week {meeting_summary.get('meetings_this_week', 0)} / 5 meetings"
                            ),
                        }
                    )

    if pass_type_key == "special":
        checks.append(
            {
                "label": "Special pass handling",
                "value": "Exception review",
                "status_class": "pass",
                "detail": "Special Pass is reviewed under the configured special pass rules.",
            }
        )

    title = "Gratitude House Policy Check" if use_gh else "Pass Policy Check"

    return {
        "title": title,
        "resident_level": resident_level or "Not Set",
        "pass_type_label": pass_type_text,
        "rule_lines": rule_box.get("lines", []),
        "checks": checks,
        "has_disciplinary_block": has_block,
        "disciplinary_restrictions": restriction_rows,
    }
