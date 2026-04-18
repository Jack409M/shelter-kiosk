from __future__ import annotations

from typing import Any

from core.promotion_policy import load_promotion_policy_for_level


def _bool(val):
    if val is None:
        return None
    return bool(val)


def _level_number(level_value: str | None) -> int:
    text = str(level_value or "").lower()
    digits = "".join(ch for ch in text if ch.isdigit())
    try:
        return int(digits)
    except Exception:
        return 0


def build_promotion_readiness(snapshot: dict[str, Any]) -> dict[str, Any]:
    level = _level_number(snapshot.get("program_level"))
    policy = load_promotion_policy_for_level(level)

    checks = []

    def add(label, ok, detail=""):
        checks.append(
            {
                "label": label,
                "ok": bool(ok),
                "detail": detail,
            }
        )

    if not policy:
        return {
            "level": level,
            "checks": [],
            "ready": False,
            "blockers": ["No promotion policy defined for this level."],
        }

    days_on_level = snapshot.get("days_on_level") or 0
    total_meetings = snapshot.get("total_meetings", 0)
    meetings_this_week = snapshot.get("meetings_this_week", 0)
    sponsor_active = _bool(snapshot.get("sponsor_active"))
    step_active = _bool(snapshot.get("step_work_active"))
    monthly_income = snapshot.get("monthly_income")
    no_writeups_last_30_days = snapshot.get("no_writeups_last_30_days")
    writeups_last_30_days = snapshot.get("writeups_last_30_days", 0)
    rad_complete = _bool(snapshot.get("rad_complete"))

    meets_work_requirement = snapshot.get("meets_work_requirement")
    meets_productive_requirement = snapshot.get("meets_productive_requirement")

    system_rules = policy.get("system_requirements", {})

    # Minimum days requirement
    min_days = policy.get("minimum_days_on_level")
    if min_days:
        add("Minimum Days on Level", days_on_level >= min_days, f"{days_on_level}/{min_days} days")

    # System rule checks
    if system_rules.get("rad_complete"):
        add("RAD Complete", rad_complete is True, "")

    if system_rules.get("sponsor_active"):
        add("Sponsor Active", sponsor_active is True, "")

    if system_rules.get("step_work_active"):
        add("Step Work Active", step_active is True, "")

    if system_rules.get("no_writeups_last_30_days"):
        add(
            "No Write Ups in 30 Days",
            no_writeups_last_30_days is True,
            f"{writeups_last_30_days} in last 30 days",
        )

    if system_rules.get("total_meetings_required"):
        required = system_rules.get("total_meetings_required")
        add(
            f"{required} Meetings",
            total_meetings >= required,
            f"{total_meetings}/{required}",
        )

    if system_rules.get("weekly_meetings_required"):
        required = system_rules.get("weekly_meetings_required")
        add(
            f"Weekly Meetings ({required})",
            meetings_this_week >= required,
            f"{meetings_this_week}/{required}",
        )

    if system_rules.get("income_required"):
        add("Income Established", monthly_income not in (None, "", 0), "")

    if system_rules.get("work_hours_required"):
        add(
            "Weekly Work Hours Requirement",
            meets_work_requirement is True,
            "",
        )

    if system_rules.get("productive_hours_required"):
        add(
            "Weekly Productive Hours Requirement",
            meets_productive_requirement is True,
            "",
        )

    ready = all(c["ok"] for c in checks) if checks else False

    blockers = [c["label"] for c in checks if not c["ok"]]

    return {
        "level": level,
        "checks": checks,
        "ready": ready,
        "blockers": blockers,
        "policy_title": policy.get("title"),
        "manual_requirements": policy.get("manual_requirements", []),
    }
