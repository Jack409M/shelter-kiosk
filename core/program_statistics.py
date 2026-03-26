from __future__ import annotations

from typing import Any

from core.constants import EDUCATION_LEVEL_RANK
from core.db import db_fetchall, db_fetchone
from core.helpers import shelter_display
from core.report_filters import mask_small_counts
from core.stats.common import (
    base_enrollment_where,
    days_between,
    display_shelter_label,
    entry_window_clause,
    exit_window_clause,
    fetch_avg,
    fetch_count,
    fetch_grouped_rows,
    iso_today,
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
    normalize_shelter_value,
    row_get,
    scope_clause,
    shelter_expr,
    to_float,
    to_int,
    window_dates,
)
from core.stats.demographics import get_demographics
from core.stats.family import get_family_composition


_SHELTER_CAPACITY = {
    "abba": 10,
    "haven": 18,
    "gratitude": 34,
}

_EDUCATION_AVERAGE_LABELS = {
    1: "No High School",
    2: "Some High School",
    3: "High School Graduate / GED",
    4: "Vocational / Associates",
    5: "Bachelor",
    6: "Masters",
    7: "Doctorate",
}

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


def _education_rank_case(column_sql: str) -> str:
    parts = ["CASE"]
    for label, rank in EDUCATION_LEVEL_RANK.items():
        safe_label = label.replace("'", "''")
        parts.append(f"WHEN TRIM({column_sql}) = '{safe_label}' THEN {rank}")
    parts.append("ELSE NULL END")
    return " ".join(parts)


def _education_average_label(avg_value: float | None) -> str:
    if avg_value is None:
        return "Unknown"
    nearest_rank = max(1, min(7, int(round(avg_value))))
    return _EDUCATION_AVERAGE_LABELS.get(nearest_rank, "Unknown")


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
        value = to_int(row_get(row, "total", 1, 0), 0)
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


def get_recovery_and_sobriety(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = base_enrollment_where(
        normalize_scope(scope),
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    primary_substances = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(ia.drug_of_choice), ''), 'Unknown') AS label,
               COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(ia.drug_of_choice), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    avg_days_sober_at_entry = fetch_avg(
        f"""
        SELECT AVG(ia.days_sober_at_entry) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    return {
        "primary_substances": primary_substances,
        "average_days_sober_at_entry": round(avg_days_sober_at_entry, 1),
    }


def get_trauma_and_vulnerability(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = base_enrollment_where(
        normalize_scope(scope),
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    ace_avg = fetch_avg(
        f"""
        SELECT AVG(ia.ace_score) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    sexual_survivor = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.sexual_survivor = 1
        """,
        where_params,
    )

    dv_survivor = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.dv_survivor = 1
        """,
        where_params,
    )

    trafficking_survivor = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.human_trafficking_survivor = 1
        """,
        where_params,
    )

    return {
        "ace_score_average": round(ace_avg, 1),
        "sexual_survivor_count": sexual_survivor,
        "sexual_survivor_display": mask_small_counts(sexual_survivor),
        "dv_survivor_count": dv_survivor,
        "dv_survivor_display": mask_small_counts(dv_survivor),
        "human_trafficking_survivor_count": trafficking_survivor,
        "human_trafficking_survivor_display": mask_small_counts(trafficking_survivor),
    }


def get_barriers_to_stability(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = base_enrollment_where(
        normalize_scope(scope),
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    felony = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.entry_felony_conviction = 1
        """,
        where_params,
    )

    parole = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.entry_parole_probation = 1
        """,
        where_params,
    )

    drug_court = fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.drug_court = 1
        """,
        where_params,
    )

    return {
        "entry_felony_conviction_count": felony,
        "entry_felony_conviction_display": mask_small_counts(felony),
        "entry_parole_probation_count": parole,
        "entry_parole_probation_display": mask_small_counts(parole),
        "drug_court_count": drug_court,
        "drug_court_display": mask_small_counts(drug_court),
    }


def get_education_and_income(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = base_enrollment_where(
        normalize_scope(scope),
        normalize_population(population),
        normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    avg_income_at_entry = fetch_avg(
        f"""
        SELECT AVG(ia.income_at_entry) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    avg_income_at_exit = fetch_avg(
        f"""
        SELECT AVG(ea.income_at_exit) AS avg_value
        FROM program_enrollments pe
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    improvement_row = db_fetchone(
        f"""
        SELECT AVG(ea.income_at_exit - ia.income_at_entry) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        {where_sql}
        AND ia.income_at_entry IS NOT NULL
        AND ea.income_at_exit IS NOT NULL
        """,
        tuple(where_params),
    )
    avg_improvement = to_float(row_get(improvement_row, "avg_value", 0, 0.0), 0.0)

    education_entry = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(ia.education_at_entry), ''), 'Unknown') AS label,
               COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(ia.education_at_entry), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    education_exit = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(ea.education_at_exit), ''), 'Unknown') AS label,
               COUNT(*) AS total
        FROM program_enrollments pe
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(ea.education_at_exit), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    entry_rank_case = _education_rank_case("ia.education_at_entry")
    exit_rank_case = _education_rank_case("ea.education_at_exit")

    avg_education_at_entry = fetch_avg(
        f"""
        SELECT AVG({entry_rank_case}) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    avg_education_at_exit = fetch_avg(
        f"""
        SELECT AVG({exit_rank_case}) AS avg_value
        FROM program_enrollments pe
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    avg_education_improvement_row = db_fetchone(
        f"""
        SELECT AVG(({exit_rank_case}) - ({entry_rank_case})) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        {where_sql}
        AND ({entry_rank_case}) IS NOT NULL
        AND ({exit_rank_case}) IS NOT NULL
        """,
        tuple(where_params),
    )
    avg_education_improvement = to_float(
        row_get(avg_education_improvement_row, "avg_value", 0, 0.0),
        0.0,
    )

    return {
        "average_income_at_entry": round(avg_income_at_entry, 2),
        "average_income_at_exit": round(avg_income_at_exit, 2),
        "average_income_improvement": round(avg_improvement, 2),
        "average_education_at_entry": round(avg_education_at_entry, 2),
        "average_education_at_entry_label": _education_average_label(
            round(avg_education_at_entry, 2) if avg_education_at_entry else None
        ),
        "average_education_at_exit": round(avg_education_at_exit, 2),
        "average_education_at_exit_label": _education_average_label(
            round(avg_education_at_exit, 2) if avg_education_at_exit else None
        ),
        "average_education_improvement": round(avg_education_improvement, 2),
        "education_at_entry": education_entry,
        "education_at_exit": education_exit,
    }


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


def get_dashboard_statistics(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    normalized_scope = normalize_scope(scope)
    normalized_population = normalize_population(population)
    normalized_date_range = normalize_date_range_key(date_range)
    start_date, end_date = window_dates(normalized_date_range, start, end)

    return {
        "filters": {
            "scope": normalized_scope,
            "population": normalized_population,
            "date_range": normalized_date_range,
            "start_date": start_date,
            "end_date": end_date,
        },
        "program_snapshot": get_program_snapshot(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "scope_comparison": get_scope_comparison(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "capacity_snapshot": get_capacity_snapshot(),
        "shelter_distribution": get_shelter_distribution(
            normalized_population, normalized_date_range, start, end
        ),
        "demographics": get_demographics(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "family_composition": get_family_composition(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "recovery_and_sobriety": get_recovery_and_sobriety(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "trauma_and_vulnerability": get_trauma_and_vulnerability(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "barriers_to_stability": get_barriers_to_stability(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "education_and_income": get_education_and_income(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
        "exit_outcomes": get_exit_outcomes(
            normalized_scope, normalized_population, normalized_date_range, start, end
        ),
    }
