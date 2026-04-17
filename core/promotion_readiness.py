from __future__ import annotations

from typing import Any


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

    days_on_level = snapshot.get("days_on_level") or 0

    total_meetings = snapshot.get("total_meetings", 0)
    meetings_this_week = snapshot.get("meetings_this_week", 0)
    completed_90 = snapshot.get("completed_90_in_90")
    completed_116 = snapshot.get("completed_116_meetings")
    completed_168 = snapshot.get("completed_168_meetings")

    sponsor_active = _bool(snapshot.get("sponsor_active"))
    step_active = _bool(snapshot.get("step_work_active"))

    monthly_income = snapshot.get("monthly_income")
    no_writeups_last_30_days = snapshot.get("no_writeups_last_30_days")
    writeups_last_30_days = snapshot.get("writeups_last_30_days", 0)

    rad_complete = _bool(snapshot.get("rad_complete"))

    checks = []

    def add(label, ok, detail=""):
        checks.append(
            {
                "label": label,
                "ok": ok,
                "detail": detail,
            }
        )

    if level == 1:
        add("30 Days in Program", days_on_level >= 30, f"{days_on_level} days")
        add("RAD Complete", rad_complete is True, "")
        add("Sponsor Active", sponsor_active is True, "")
        add("Step Work Active", step_active is True, "")
        add(
            "No Write Ups in 30 Days",
            no_writeups_last_30_days is True,
            f"{writeups_last_30_days} in last 30 days",
        )

        ready = all(c["ok"] for c in checks)

    elif level == 2:
        add("90 Meetings", completed_90 is True, f"{total_meetings}/90")
        add("Sponsor Active", sponsor_active is True, "")
        add("Step Work Active", step_active is True, "")
        add(
            "No Write Ups in 30 Days",
            no_writeups_last_30_days is True,
            f"{writeups_last_30_days} in last 30 days",
        )

        ready = all(c["ok"] for c in checks)

    elif level == 3:
        add("116 Meetings", completed_116 is True, f"{total_meetings}/116")
        add(
            "Weekly Meetings (6)",
            snapshot.get("weekly_requirement_met") is True,
            f"{meetings_this_week}/6",
        )
        add("Sponsor Active", sponsor_active is True, "")
        add("Step Work Active", step_active is True, "")
        add(
            "No Write Ups in 30 Days",
            no_writeups_last_30_days is True,
            f"{writeups_last_30_days} in last 30 days",
        )

        ready = all(c["ok"] for c in checks)

    elif level == 4:
        add("168 Meetings", completed_168 is True, f"{total_meetings}/168")
        add(
            "Weekly Meetings (5)",
            snapshot.get("weekly_requirement_met") is True,
            f"{meetings_this_week}/5",
        )
        add("Sponsor Active", sponsor_active is True, "")
        add("Step Work Active", step_active is True, "")
        add("Income Established", monthly_income not in (None, "", 0), "")
        add(
            "No Write Ups in 30 Days",
            no_writeups_last_30_days is True,
            f"{writeups_last_30_days} in last 30 days",
        )

        ready = all(c["ok"] for c in checks)

    else:
        ready = False

    blockers = [c["label"] for c in checks if not c["ok"]]

    return {
        "level": level,
        "checks": checks,
        "ready": ready,
        "blockers": blockers,
    }
