from __future__ import annotations

from typing import Any

from core.report_filters import mask_small_counts
from core.stats.common import (
    base_enrollment_where,
    fetch_avg,
    fetch_count,
    fetch_grouped_rows,
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
)


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
