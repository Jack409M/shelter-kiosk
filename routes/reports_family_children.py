from __future__ import annotations

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall, db_fetchone
from core.runtime import init_db
from core.stats.common import (
    base_enrollment_where,
    fetch_grouped_rows,
    normalize_population,
    normalize_scope,
)
from core.stats.family import get_family_composition

reports_family_children = Blueprint("reports_family_children", __name__)

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


def _fetch_single_total(sql: str, params: list) -> int:
    row = db_fetchone(sql, tuple(params))
    if not row:
        return 0
    if isinstance(row, dict):
        return int(row.get("total") or 0)
    return int(row[0] or 0)


def _build_family_children_report(
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

    summary = get_family_composition(
        scope=normalized_scope,
        population=normalized_population,
        date_range=normalized_date_range,
        start=start_date,
        end=end_date,
    )

    children_total = int(summary.get("children_in_shelter") or 0)
    families_total = int(summary.get("residents_with_children") or 0)

    survivor_benefit_children = _fetch_single_total(
        f"""
        SELECT COUNT(DISTINCT rc.id) AS total
        FROM resident_children rc
        JOIN program_enrollments pe ON pe.resident_id = rc.resident_id
        {where_sql}
          AND COALESCE(rc.is_active, TRUE) IS TRUE
          AND COALESCE(rc.receives_survivor_benefit, FALSE) IS TRUE
        """,
        where_params,
    )

    relationship_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(rc.relationship), ''), 'Unknown') AS label,
               COUNT(DISTINCT rc.id) AS total
        FROM resident_children rc
        JOIN program_enrollments pe ON pe.resident_id = rc.resident_id
        {where_sql}
          AND COALESCE(rc.is_active, TRUE) IS TRUE
        GROUP BY COALESCE(NULLIF(TRIM(rc.relationship), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    living_status_rows = fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(rc.living_status), ''), 'Unknown') AS label,
               COUNT(DISTINCT rc.id) AS total
        FROM resident_children rc
        JOIN program_enrollments pe ON pe.resident_id = rc.resident_id
        {where_sql}
          AND COALESCE(rc.is_active, TRUE) IS TRUE
        GROUP BY COALESCE(NULLIF(TRIM(rc.living_status), ''), 'Unknown')
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
        FROM resident_children rc
        JOIN program_enrollments pe ON pe.resident_id = rc.resident_id
        {where_sql}
          AND COALESCE(rc.is_active, TRUE) IS TRUE
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

    roster_rows = [
        dict(row)
        for row in (
            db_fetchall(
                f"""
        SELECT
            COALESCE(NULLIF(TRIM(r.first_name || ' ' || r.last_name), ''), 'Unknown Resident') AS resident_name,
            COALESCE(NULLIF(TRIM(r.resident_code), ''), NULLIF(TRIM(r.resident_identifier), ''), CAST(r.id AS TEXT)) AS resident_display_id,
            CASE
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('abba', 'abba house') THEN 'Abba House'
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('haven', 'haven house') THEN 'Haven House'
                WHEN LOWER(TRIM(COALESCE(pe.shelter, ''))) IN ('gratitude', 'gratitude house') THEN 'Gratitude House'
                ELSE COALESCE(NULLIF(TRIM(pe.shelter), ''), 'Unknown')
            END AS shelter_label,
            COALESCE(NULLIF(TRIM(rc.child_name), ''), 'Unnamed Child') AS child_name,
            COALESCE(NULLIF(TRIM(rc.relationship), ''), 'Unknown') AS relationship,
            COALESCE(NULLIF(TRIM(rc.living_status), ''), 'Unknown') AS living_status,
            rc.birth_year,
            COALESCE(rc.receives_survivor_benefit, FALSE) AS receives_survivor_benefit
        FROM resident_children rc
        JOIN residents r ON r.id = rc.resident_id
        JOIN program_enrollments pe ON pe.resident_id = rc.resident_id
        {where_sql}
          AND COALESCE(rc.is_active, TRUE) IS TRUE
        ORDER BY shelter_label, resident_name, child_name, rc.id
        """,
                tuple(where_params),
            )
            or []
        )
    ]

    average_children_per_family = (
        round((children_total / families_total), 2) if families_total else 0.0
    )

    return {
        "scope": normalized_scope,
        "population": normalized_population,
        "date_range": normalized_date_range,
        "start_date": resolved_start or "",
        "end_date": resolved_end or "",
        "summary": summary,
        "survivor_benefit_children": survivor_benefit_children,
        "average_children_per_family": average_children_per_family,
        "relationship_rows": relationship_rows,
        "living_status_rows": living_status_rows,
        "shelter_rows": shelter_rows,
        "roster_rows": roster_rows,
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


@reports_family_children.route("/staff/reports/family-and-children", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def family_and_children_report():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    population = _clean_population(request.args.get("population"))
    date_range = _clean_date_range(request.args.get("date_range"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))

    if date_range != "custom":
        start_date = None
        end_date = None

    report = _build_family_children_report(scope, population, date_range, start_date, end_date)

    return render_template(
        "reports/family_and_children.html",
        title="Family And Children Report",
        report=report,
    )
