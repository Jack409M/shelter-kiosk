from __future__ import annotations

from typing import Any

from core.report_filters import mask_small_counts
from core.stats.common import (
    fetch_count,
    fetch_grouped_rows,
    normalize_date_range_key,
    normalize_scope,
    row_get,
    scope_clause,
    to_int,
    window_dates,
)
from core.db import db_fetchone


_EXIT_REASON_TO_CATEGORY = {
    "Program Graduated": "Successful Completion",
    "Permanent Housing": "Positive Exit",
    "Family Placement": "Positive Exit",
    "Health Placement": "Positive Exit",
    "Transferred to Another Program": "Neutral Exit",
    "Unknown / Lost Contact": "Neutral Exit",
    "Relapse": "Negative Exit",
    "Behavioral Conflict": "Negative Exit",
    "Rules Violation": "Negative Exit",
    "Non Compliance with Program": "Negative Exit",
    "Left Without Notice": "Negative Exit",
    "Incarceration": "Administrative Exit",
    "Medical Discharge": "Administrative Exit",
    "Safety Removal": "Administrative Exit",
    "Left by Choice": "Administrative Exit",
}

_EXIT_CATEGORY_ORDER = [
    "Successful Completion",
    "Positive Exit",
    "Neutral Exit",
    "Negative Exit",
    "Administrative Exit",
    "Unknown",
]


def get_exit_outcomes(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    normalized_scope = normalize_scope(scope)
    start_date, end_date = window_dates(normalize_date_range_key(date_range), start, end)
    scope_sql, scope_params = scope_clause("pe", normalized_scope)

    exit_window_sql = ""
    exit_window_params: list[Any] = []
    if start_date and end_date:
        exit_window_sql = " AND ea.date_exit_dwc >= ? AND ea.date_exit_dwc <= ?"
        exit_window_params = [start_date, end_date]

    graduates = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM exit_assessments ea
        JOIN program_enrollments pe ON pe.id = ea.enrollment_id
        WHERE 1=1
        {scope_sql}
        AND ea.graduate_dwc = 1
        {exit_window_sql}
        """,
        scope_params + exit_window_params,
    )

    leave_ama = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM exit_assessments ea
        JOIN program_enrollments pe ON pe.id = ea.enrollment_id
        WHERE 1=1
        {scope_sql}
        AND ea.leave_ama = 1
        {exit_window_sql}
        """,
        scope_params + exit_window_params,
    )

    exit_reasons = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(ea.exit_reason), ''), 'Unknown') AS label,
               COUNT(*) AS total
        FROM exit_assessments ea
        JOIN program_enrollments pe ON pe.id = ea.enrollment_id
        WHERE 1=1
        {scope_sql}
        {exit_window_sql}
        GROUP BY COALESCE(NULLIF(TRIM(ea.exit_reason), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        scope_params + exit_window_params,
    )

    local_outcomes_row = db_fetchone(
        f"""
        SELECT
            SUM(CASE WHEN ea.leave_ama = 0 THEN 1 ELSE 0 END) AS stayed,
            SUM(CASE WHEN ea.leave_ama = 1 THEN 1 ELSE 0 END) AS left_program_city,
            SUM(CASE WHEN ea.leave_ama IS NULL THEN 1 ELSE 0 END) AS unknown
        FROM exit_assessments ea
        JOIN program_enrollments pe ON pe.id = ea.enrollment_id
        WHERE 1=1
        {scope_sql}
        {exit_window_sql}
        """,
        tuple(scope_params + exit_window_params),
    )

    local_outcomes = {
        "stayed": to_int(row_get(local_outcomes_row, "stayed", 0, 0), 0),
        "left": to_int(row_get(local_outcomes_row, "left_program_city", 1, 0), 0),
        "unknown": to_int(row_get(local_outcomes_row, "unknown", 2, 0), 0),
    }

    exit_category_counts: dict[str, int] = {category: 0 for category in _EXIT_CATEGORY_ORDER}

    for item in exit_reasons:
        reason = item["label"]
        category = _EXIT_REASON_TO_CATEGORY.get(reason, "Unknown")
        exit_category_counts[category] = exit_category_counts.get(category, 0) + item["value"]

    total_categorized_exits = sum(exit_category_counts.values())

    exit_category_percentages: list[dict[str, Any]] = []
    for category in _EXIT_CATEGORY_ORDER:
        count = exit_category_counts.get(category, 0)
        percent = round((count / total_categorized_exits) * 100, 1) if total_categorized_exits else 0.0
        exit_category_percentages.append(
            {
                "label": category,
                "value": count,
                "display_value": mask_small_counts(count),
                "percent": percent,
            }
        )

    total_exits = sum(item["value"] for item in exit_reasons)

    return {
        "graduates": graduates,
        "graduates_display": mask_small_counts(graduates),
        "leave_ama": leave_ama,
        "leave_ama_display": mask_small_counts(leave_ama),
        "total_exit_records": total_exits,
        "total_exit_records_display": mask_small_counts(total_exits),
        "exit_reasons": exit_reasons,
        "exit_category_percentages": exit_category_percentages,
        "local_outcomes": {
            "stayed": local_outcomes["stayed"],
            "stayed_display": mask_small_counts(local_outcomes["stayed"]),
            "left": local_outcomes["left"],
            "left_display": mask_small_counts(local_outcomes["left"]),
            "unknown": local_outcomes["unknown"],
            "unknown_display": mask_small_counts(local_outcomes["unknown"]),
        },
    }
