from __future__ import annotations

from typing import Any

PROMOTION_POLICY: dict[int, dict[str, Any]] = {
    1: {
        "title": "Level 1 to Level 2",
        "program": "Haven House",
        "next_level": 2,
        "minimum_days_on_level": 60,
        "system_requirements": {
            "rad_complete": True,
            "sponsor_active": True,
            "step_work_active": True,
            "no_writeups_last_30_days": True,
            "work_hours_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Staff believes resident is ready for Level 2.",
            "Resident is actively attending required meetings.",
        ],
    },
    2: {
        "title": "Level 2 to Level 3",
        "program": "Haven House",
        "next_level": 3,
        "minimum_days_on_level": 60,
        "system_requirements": {
            "total_meetings_required": 90,
            "sponsor_active": True,
            "step_work_active": True,
            "no_writeups_last_30_days": True,
            "work_hours_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Staff believes resident is ready for Level 3.",
            "Resident is actively following a budget plan.",
            "Resident is actively paying rent on time.",
            "Resident demonstrates behavioral growth.",
        ],
    },
    3: {
        "title": "Level 3 to Level 4",
        "program": "Haven House",
        "next_level": 4,
        "minimum_days_on_level": 60,
        "system_requirements": {
            "total_meetings_required": 116,
            "weekly_meetings_required": 6,
            "sponsor_active": True,
            "step_work_active": True,
            "no_writeups_last_30_days": True,
            "work_hours_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Staff believes resident is ready for Level 4.",
            "Resident shows leadership and mentors new residents.",
            "Resident demonstrates behavioral growth.",
            "Resident has steady employment.",
            "Resident is saving money.",
        ],
    },
    4: {
        "title": "Level 4 to Level 5",
        "program": "Haven House to Gratitude House transition",
        "next_level": 5,
        "minimum_days_on_level": 90,
        "system_requirements": {
            "total_meetings_required": 168,
            "weekly_meetings_required": 5,
            "sponsor_active": True,
            "step_work_active": True,
            "no_writeups_last_30_days": True,
            "income_required": True,
            "work_hours_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Staff believes resident is ready for Level 5.",
            "Resident has the financial ability to move to Gratitude House.",
            "Resident is actively following a budget plan.",
            "Resident is saving money.",
            "Resident shows leadership and mentors new residents.",
            "Gratitude House has an apartment available.",
        ],
    },
    5: {
        "title": "Level 5 to Level 6",
        "program": "Gratitude House",
        "next_level": 6,
        "minimum_days_on_level": 90,
        "system_requirements": {
            "weekly_meetings_required": 4,
            "sponsor_active": True,
            "step_work_active": True,
            "income_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Resident meets individual goals set for Level 6.",
            "Case manager confirms apartment rules and adjustment expectations are being met.",
        ],
    },
    6: {
        "title": "Level 6 to Level 7",
        "program": "Gratitude House",
        "next_level": 7,
        "minimum_days_on_level": 90,
        "system_requirements": {
            "weekly_meetings_required": 4,
            "sponsor_active": True,
            "step_work_active": True,
            "income_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Resident meets individual goals set for Level 7.",
            "Case manager confirms continued compliance with Gratitude House expectations.",
        ],
    },
    7: {
        "title": "Level 7 to Level 8",
        "program": "Gratitude House graduation to Transitional Housing",
        "next_level": 8,
        "system_requirements": {
            "weekly_meetings_required": 4,
            "sponsor_active": True,
            "step_work_active": True,
            "income_required": True,
            "productive_hours_required": True,
        },
        "manual_requirements": [
            "Resident meets individual goals to graduate from the DWC Recovery Program.",
            "Case managers and program director agree the resident is ready to graduate.",
        ],
    },
    8: {
        "title": "Level 8 Transitional Housing continuation",
        "program": "Gratitude House Transitional Housing",
        "next_level": 9,
        "system_requirements": {
            "weekly_meetings_required": 3,
            "sponsor_active": True,
            "step_work_active": True,
            "income_required": True,
        },
        "manual_requirements": [
            "Resident continues to meet transitional housing program requirements.",
            "Case manager confirms rent, housing, and personal stability expectations are being met.",
        ],
    },
    9: {
        "title": "Level 9 Permanent Housing supportive services",
        "program": "Permanent Housing with DWC supportive services",
        "next_level": None,
        "system_requirements": {
            "weekly_meetings_required": 2,
            "income_required": True,
        },
        "manual_requirements": [
            "Resident completes monthly case manager home visit.",
            "Resident completes monthly budget with case manager.",
            "Resident completes and follows the individual service plan.",
            "Resident maintains lease and utilities without interruption.",
            "Resident passes random drug screenings.",
        ],
    },
}


def load_promotion_policy_for_level(level: int) -> dict[str, Any]:
    return dict(PROMOTION_POLICY.get(int(level or 0), {}))
