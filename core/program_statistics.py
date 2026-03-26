from __future__ import annotations

from core.constants import EDUCATION_LEVEL_RANK
from core.db import db_fetchone
from core.report_filters import mask_small_counts
from core.stats.common import (
    base_enrollment_where,
    fetch_avg,
    fetch_count,
    fetch_grouped_rows,
    normalize_date_range_key,
    normalize_population,
    normalize_scope,
    row_get,
    to_float,
    window_dates,
)
from core.stats.demographics import get_demographics
from core.stats.family import get_family_composition
from core.stats.outcomes import get_exit_outcomes
from core.stats.recovery import (
    get_recovery_and_sobriety,
    get_trauma_and_vulnerability,
)
from core.stats.snapshot import (
    get_capacity_snapshot,
    get_program_snapshot,
    get_scope_comparison,
    get_shelter_distribution,
)


_EDUCATION_AVERAGE_LABELS = {
    1: "No High School",
    2: "Some High School",
    3: "High School Graduate / GED",
    4: "Vocational / Associates",
    5: "Bachelor",
    6: "Masters",
    7: "Doctorate",
}


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


def get_barriers_to_stability(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
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
) -> dict[str, object]:
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


def get_dashboard_statistics(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, object]:
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
