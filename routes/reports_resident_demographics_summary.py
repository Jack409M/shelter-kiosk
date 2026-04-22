from __future__ import annotations

from datetime import datetime

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchone
from core.runtime import init_db
from core.stats.common import (
    base_enrollment_where,
    fetch_grouped_rows,
    normalize_population,
    normalize_scope,
)

reports_resident_demographics_summary = Blueprint(
    "reports_resident_demographics_summary",
    __name__,
)

_ALLOWED_DATE_RANGES = {
    "this_month",
    "last_month",
    "this_quarter",
    "this_year",
    "last_year",
    "all_time",
    "custom",
}


def _clean_iso_date(value: str | None) -> str | None:
    text = (value or "").strip()
    if not text:
        return None

    parts = text.split("-")
    if len(parts) != 3:
        return None

    year, month, day = parts
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return None

    if len(year) != 4 or len(month) != 2 or len(day) != 2:
        return None

    return text


def _clean_scope(value: str | None) -> str:
    return normalize_scope(value)


def _clean_population(value: str | None) -> str:
    return normalize_population(value)


def _clean_date_range(value: str | None) -> str:
    cleaned = (value or "all_time").strip().lower()
    if cleaned in _ALLOWED_DATE_RANGES:
        return cleaned
    return "all_time"


def _percentage(value: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((value / total) * 100, 1)


def _with_percentages(rows: list[dict], total: int) -> list[dict]:
    output: list[dict] = []
    for row in rows:
        item = dict(row)
        value = int(item.get("value") or 0)
        item["percentage"] = _percentage(value, total)
        output.append(item)
    return output


def _fetch_single_total(sql: str, params: list) -> int:
    row = db_fetchone(sql, tuple(params))
    if not row:
        return 0
    if isinstance(row, dict):
        return int(row.get("total") or 0)
    return int(row[0] or 0)


def _build_resident_demographics_summary(
    scope: str,
    population: str,
    date_range: str,
    start_date: str | None,
    end_date: str | None,
) -> dict:
    normalized_scope = _clean_scope(scope)
    normalized_population = _clean_population(population)
    normalized_date_range = _clean_date_range(date_range)

    where_sql, where_params, resolved_start, resolved_end = base_enrollment_where(
        normalized_scope,
        normalized_population,
        normalized_date_range,
        start_date,
        end_date,
        alias="pe",
    )

    total_residents = _fetch_single_total(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        """,
        where_params,
    )

    gender_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(r.gender), ''), 'Unknown') AS label,
               COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
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
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(r.race), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    ethnicity_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(r.ethnicity), ''), 'Unknown') AS label,
               COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(r.ethnicity), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    shelter_rows = fetch_grouped_rows(
        f"""
        SELECT
            CASE
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('abba', 'abba house') THEN 'Abba House'
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('haven', 'haven house') THEN 'Haven House'
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('gratitude', 'gratitude house') THEN 'Gratitude House'
                ELSE COALESCE(NULLIF(TRIM(pe.shelter), ''), 'Unknown')
            END AS label,
            COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        GROUP BY
            CASE
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('abba', 'abba house') THEN 'Abba House'
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('haven', 'haven house') THEN 'Haven House'
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('gratitude', 'gratitude house') THEN 'Gratitude House'
                ELSE COALESCE(NULLIF(TRIM(pe.shelter), ''), 'Unknown')
            END
        ORDER BY total DESC, label
        """,
        where_params,
    )

    veteran_yes = _fetch_single_total(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
          AND COALESCE(r.veteran, 0) = 1
        """,
        where_params,
    )

    disability_yes = _fetch_single_total(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
          AND COALESCE(r.disability, 0) = 1
        """,
        where_params,
    )

    current_year = datetime.now().year

    age_rows = fetch_grouped_rows(
        f"""
        SELECT
            CASE
                WHEN r.birth_year IS NULL OR r.birth_year = 0 THEN 'Unknown'
                WHEN r.birth_year > {current_year - 18} THEN 'Under 18'
                WHEN r.birth_year BETWEEN {current_year - 24} AND {current_year - 18} THEN '18 to 24'
                WHEN r.birth_year BETWEEN {current_year - 34} AND {current_year - 25} THEN '25 to 34'
                WHEN r.birth_year BETWEEN {current_year - 44} AND {current_year - 35} THEN '35 to 44'
                WHEN r.birth_year BETWEEN {current_year - 54} AND {current_year - 45} THEN '45 to 54'
                WHEN r.birth_year BETWEEN {current_year - 64} AND {current_year - 55} THEN '55 to 64'
                ELSE '65 and older'
            END AS label,
            COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
        GROUP BY
            CASE
                WHEN r.birth_year IS NULL OR r.birth_year = 0 THEN 'Unknown'
                WHEN r.birth_year > {current_year - 18} THEN 'Under 18'
                WHEN r.birth_year BETWEEN {current_year - 24} AND {current_year - 18} THEN '18 to 24'
                WHEN r.birth_year BETWEEN {current_year - 34} AND {current_year - 25} THEN '25 to 34'
                WHEN r.birth_year BETWEEN {current_year - 44} AND {current_year - 35} THEN '35 to 44'
                WHEN r.birth_year BETWEEN {current_year - 54} AND {current_year - 45} THEN '45 to 54'
                WHEN r.birth_year BETWEEN {current_year - 64} AND {current_year - 55} THEN '55 to 64'
                ELSE '65 and older'
            END
        ORDER BY total DESC, label
        """,
        where_params,
    )

    veteran_no = max(total_residents - veteran_yes, 0)
    disability_no = max(total_residents - disability_yes, 0)

    return {
        "scope": normalized_scope,
        "population": normalized_population,
        "date_range": normalized_date_range,
        "start_date": resolved_start or "",
        "end_date": resolved_end or "",
        "total_residents": total_residents,
        "veteran_yes": veteran_yes,
        "veteran_no": veteran_no,
        "veteran_yes_percentage": _percentage(veteran_yes, total_residents),
        "disability_yes": disability_yes,
        "disability_no": disability_no,
        "disability_yes_percentage": _percentage(disability_yes, total_residents),
        "gender_rows": _with_percentages(gender_rows, total_residents),
        "race_rows": _with_percentages(race_rows, total_residents),
        "ethnicity_rows": _with_percentages(ethnicity_rows, total_residents),
        "shelter_rows": _with_percentages(shelter_rows, total_residents),
        "age_rows": _with_percentages(age_rows, total_residents),
        "scope_options": [
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        "population_options": [
            {"value": "active", "label": "Active Residents"},
            {"value": "exited", "label": "Exited Residents"},
            {"value": "all", "label": "All Residents"},
        ],
        "date_range_options": [
            {"value": "this_month", "label": "This Month"},
            {"value": "last_month", "label": "Last Month"},
            {"value": "this_quarter", "label": "This Quarter"},
            {"value": "this_year", "label": "This Year"},
            {"value": "last_year", "label": "Last Year"},
            {"value": "all_time", "label": "All Time"},
            {"value": "custom", "label": "Custom Range"},
        ],
    }


@reports_resident_demographics_summary.route(
    "/staff/reports/resident-demographics-summary",
    methods=["GET"],
)
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def resident_demographics_summary_report():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    population = _clean_population(request.args.get("population"))
    date_range = _clean_date_range(request.args.get("date_range"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))

    if date_range != "custom":
        start_date = None
        end_date = None

    report = _build_resident_demographics_summary(
        scope=scope,
        population=population,
        date_range=date_range,
        start_date=start_date,
        end_date=end_date,
    )

    return render_template(
        "reports/resident_demographics_summary.html",
        title="Resident Demographics Summary",
        report=report,
    )
