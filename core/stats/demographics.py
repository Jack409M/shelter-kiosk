from __future__ import annotations

from typing import Any

from core.report_filters import mask_small_counts
from core.stats.common import (
    base_enrollment_where,
    fetch_count,
    fetch_grouped_rows,
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
)


def get_demographics(
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

    gender_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(r.gender), ''), 'Unknown') AS label,
               COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(r.gender), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    race_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(r.race), ''), 'Unknown') AS label,
               COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(r.race), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    marital_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(ia.marital_status), ''), 'Unknown') AS label,
               COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(ia.marital_status), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    veteran_yes = fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.veteran = 1
        """,
        where_params,
    )

    disability_yes = fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.disability IS NOT NULL
        AND TRIM(ia.disability) <> ''
        """,
        where_params,
    )

    return {
        "gender": gender_rows,
        "race": race_rows,
        "marital_status": marital_rows,
        "veteran_yes": veteran_yes,
        "veteran_yes_display": mask_small_counts(veteran_yes),
        "disability_yes": disability_yes,
        "disability_yes_display": mask_small_counts(disability_yes),
    }
