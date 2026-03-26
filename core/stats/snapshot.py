from __future__ import annotations

from typing import Any

from core.db import db_fetchall
from core.helpers import shelter_display
from core.report_filters import mask_small_counts
from core.stats.common import (
    base_enrollment_where,
    display_shelter_label,
    entry_window_clause,
    exit_window_clause,
    fetch_count,
    iso_today,
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
    normalize_shelter_value,
    row_get,
    scope_clause,
    shelter_expr,
    window_dates,
    days_between,
)


_SHELTER_CAPACITY = {
    "abba": 10,
    "haven": 18,
    "gratitude": 34,
}


def _get_filtered_served_total(
    scope: str,
    population: str,
    date_range: str,
    start: str | None = None,
    end: str | None = None,
) -> int:
    where_sql, where_params, _, _ = base_enrollment_where(
        normalize_scope(scope),
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    return fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        """,
        where_params,
    )


def _get_current_active_count_for_scope(scope: str) -> int:
    normalized_scope = normalize_scope(scope)
    scope_sql, scope_params = scope_clause("pe", normalized_scope)

    return fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        AND pe.entry_date <= ?
        AND (pe.exit_date IS NULL OR pe.exit_date = '' OR pe.exit_date >= ?)
        """,
        scope_params + [iso_today(), iso_today()],
    )


def get_capacity_snapshot() -> dict[str, Any]:
    shelters: list[dict[str, Any]] = []
    total_capacity = sum(_SHELTER_CAPACITY.values())
    total_occupied = 0

    for shelter_key in ("abba", "haven", "gratitude"):
        capacity = _SHELTER_CAPACITY[shelter_key]
        occupied = _get_current_active_count_for_scope(shelter_key)
        open_spaces = max(capacity - occupied, 0)
        occupancy_rate = round((occupied / capacity) * 100, 1) if capacity else 0.0

        shelters.append(
            {
                "key": shelter_key,
                "label": shelter_display(shelter_key),
                "capacity": capacity,
                "occupied": occupied,
                "occupied_display": mask_small_counts(occupied),
                "open_spaces": open_spaces,
                "open_spaces_display": mask_small_counts(open_spaces) if open_spaces else "0",
                "occupancy_rate": occupancy_rate,
            }
        )
        total_occupied += occupied

    total_open = max(total_capacity - total_occupied, 0)
    total_rate = round((total_occupied / total_capacity) * 100, 1) if total_capacity else 0.0

    return {
        "total_capacity": total_capacity,
        "total_occupied": total_occupied,
        "total_occupied_display": mask_small_counts(total_occupied),
        "total_open_spaces": total_open,
        "total_open_spaces_display": mask_small_counts(total_open) if total_open else "0",
        "total_occupancy_rate": total_rate,
        "shelters": shelters,
    }


def get_scope_comparison(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    normalized_scope = normalize_scope(scope)

    total_program_served = _get_filtered_served_total(
        "total_program",
        population,
        date_range,
        start,
        end,
    )

    shelter_rows: list[dict[str, Any]] = []

    for shelter_key in ("abba", "haven", "gratitude"):
        value = _get_filtered_served_total(
            shelter_key,
            population,
            date_range,
            start,
            end,
        )
        share = round((value / total_program_served) * 100, 1) if total_program_served else 0.0
        shelter_rows.append(
            {
                "key": shelter_key,
                "label": shelter_display(shelter_key),
                "value": value,
                "display_value": mask_small_counts(value),
                "share_of_program": share,
            }
        )

    selected_value = total_program_served if normalized_scope == "total_program" else _get_filtered_served_total(
        normalized_scope,
        population,
        date_range,
        start,
        end,
    )

    selected_share = 100.0 if normalized_scope == "total_program" else (
        round((selected_value / total_program_served) * 100, 1) if total_program_served else 0.0
    )

    selected_label = "Total Program" if normalized_scope == "total_program" else shelter_display(normalized_scope)

    return {
        "selected_scope_label": selected_label,
        "selected_scope_value": selected_value,
        "selected_scope_display": mask_small_counts(selected_value),
        "selected_scope_share_of_program": selected_share,
        "total_program_value": total_program_served,
        "total_program_display": mask_small_counts(total_program_served),
        "shelters": shelter_rows,
    }


def get_program_snapshot(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    normalized_scope = normalize_scope(scope)
    normalized_population = normalize_population(population)
    normalized_date_range = normalize_date_range_key(date_range)

    where_sql, where_params, start_date, end_date = base_enrollment_where(
        normalized_scope,
        normalized_population,
        normalized_date_range,
        start,
        end,
        alias="pe",
    )

    women_served = fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        """,
        where_params,
    )

    scope_sql, scope_params = scope_clause("pe", normalized_scope)

    entry_sql, entry_params = entry_window_clause("pe", start_date, end_date)
    women_admitted = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        {entry_sql}
        """,
        scope_params + entry_params,
    )

    exit_sql, exit_params = exit_window_clause("pe", start_date, end_date)
    women_exited = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        {exit_sql}
        """,
        scope_params + exit_params,
    )

    graduates = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM exit_assessments ea
        JOIN program_enrollments pe ON pe.id = ea.enrollment_id
        WHERE 1=1
        {scope_sql}
        AND ea.graduate_dwc = 1
        {("AND ea.date_exit_dwc >= ? AND ea.date_exit_dwc <= ?" if start_date and end_date else "")}
        """,
        scope_params + ([start_date, end_date] if start_date and end_date else []),
    )

    graduation_rate = round((graduates / women_exited) * 100, 1) if women_exited else 0.0

    exited_rows = db_fetchall(
        f"""
        SELECT pe.entry_date, pe.exit_date
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        {exit_sql}
        """,
        tuple(scope_params + exit_params),
    ) or []

    stay_lengths: list[int] = []
    for row in exited_rows:
        days = days_between(row_get(row, "entry_date", 0), row_get(row, "exit_date", 1))
        if days is not None and days >= 0:
            stay_lengths.append(days)

    average_length_of_stay_days = round(sum(stay_lengths) / len(stay_lengths), 1) if stay_lengths else 0.0

    current_active = fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        AND pe.entry_date <= ?
        AND (pe.exit_date IS NULL OR pe.exit_date = '' OR pe.exit_date >= ?)
        """,
        scope_params + [iso_today(), iso_today()],
    )

    return {
        "women_served": women_served,
        "women_served_display": mask_small_counts(women_served),
        "women_admitted": women_admitted,
        "women_admitted_display": mask_small_counts(women_admitted),
        "women_exited": women_exited,
        "women_exited_display": mask_small_counts(women_exited),
        "graduates": graduates,
        "graduates_display": mask_small_counts(graduates),
        "graduation_rate": graduation_rate,
        "active_residents_current": current_active,
        "active_residents_current_display": mask_small_counts(current_active),
        "average_length_of_stay_days": average_length_of_stay_days,
    }


def get_shelter_distribution(
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> list[dict[str, Any]]:
    where_sql, where_params, _, _ = base_enrollment_where(
        "total_program",
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    rows = db_fetchall(
        f"""
        SELECT {shelter_expr('pe')} AS shelter_key, COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        GROUP BY {shelter_expr('pe')}
        ORDER BY total DESC, shelter_key
        """,
        tuple(where_params),
    ) or []

    merged: dict[str, int] = {}
    for row in rows:
        raw_key = row_get(row, "shelter_key", 0, "")
        normalized_key = normalize_shelter_value(raw_key)
        value = int(row_get(row, "total", 1, 0) or 0)
        merged[normalized_key] = merged.get(normalized_key, 0) + value

    total = sum(merged.values()) or 0
    output: list[dict[str, Any]] = []

    for shelter_key in sorted(merged.keys()):
        value = merged[shelter_key]
        pct = round((value / total) * 100, 1) if total else 0.0
        output.append(
            {
                "label": display_shelter_label(shelter_key),
                "value": value,
                "display_value": mask_small_counts(value),
                "percentage": pct,
            }
        )

    output.sort(key=lambda item: (-item["value"], item["label"]))
    return output
