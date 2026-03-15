from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.db import db_fetchall, db_fetchone
from core.helpers import shelter_display
from core.report_filters import mask_small_counts, resolve_date_range


_SHELTER_CAPACITY = {
    "abba": 10,
    "haven": 18,
    "gratitude": 34,
}


def _row_get(row: Any, key: str, index: int | None = None, default: Any = None) -> Any:
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    if index is not None:
        try:
            return row[index]
        except Exception:
            return default
    try:
        return row[key]
    except Exception:
        return default


def _to_int(value: Any, default: int = 0) -> int:
    if value in (None, "", False):
        return default
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def _to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", False):
        return default
    try:
        return float(value)
    except Exception:
        return default


def _iso_today() -> str:
    return date.today().isoformat()


def _parse_iso_date(value: Any) -> date | None:
    if not value:
        return None

    text = str(value).strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except Exception:
            pass

    return None


def _days_between(start_value: Any, end_value: Any) -> int | None:
    start_date = _parse_iso_date(start_value)
    end_date = _parse_iso_date(end_value)
    if not start_date or not end_date:
        return None
    return (end_date - start_date).days


def _normalize_shelter_value(value: Any) -> str:
    raw = str(value or "").strip().lower()

    if raw in {"abba house", "abba_house"}:
        return "abba"
    if raw in {"haven house", "haven_house"}:
        return "haven"
    if raw in {"gratitude house", "gratitude_house"}:
        return "gratitude"

    return raw


def _display_shelter_label(value: Any) -> str:
    normalized = _normalize_shelter_value(value)

    if normalized in {"abba", "haven", "gratitude"}:
        return shelter_display(normalized)

    raw = str(value or "").strip()
    return raw or "Unknown"


def _shelter_expr(alias: str) -> str:
    return f"LOWER(TRIM(COALESCE({alias}.shelter, '')))"


def _normalize_scope(scope: str | None) -> str:
    value = _normalize_shelter_value(scope or "total_program")
    if value in {"abba", "haven", "gratitude", "total_program"}:
        return value
    return "total_program"


def _normalize_population(population: str | None) -> str:
    value = (population or "all").strip().lower()
    if value in {"active", "exited", "all"}:
        return value
    return "all"


def _normalize_date_range_key(date_range: str | None) -> str:
    value = (date_range or "all_time").strip().lower()
    allowed = {
        "this_month",
        "last_month",
        "this_quarter",
        "this_year",
        "last_year",
        "all_time",
        "custom",
    }
    if value in allowed:
        return value
    return "all_time"


def _scope_clause(alias: str, scope: str) -> tuple[str, list[Any]]:
    if scope == "total_program":
        return "", []
    return f" AND {_shelter_expr(alias)} IN (?, ?)", [scope, f"{scope} house"]


def _window_dates(date_range: str, start: str | None = None, end: str | None = None) -> tuple[str | None, str | None]:
    resolved_start, resolved_end = resolve_date_range(date_range, start, end)
    return (
        resolved_start.isoformat() if resolved_start else None,
        resolved_end.isoformat() if resolved_end else None,
    )


def _population_clause(
    alias: str,
    population: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, list[Any]]:
    if population == "active":
        effective_end = end_date or _iso_today()
        if start_date:
            return (
                f" AND {alias}.entry_date <= ? "
                f"AND ({alias}.exit_date IS NULL OR {alias}.exit_date = '' OR {alias}.exit_date >= ?)",
                [effective_end, start_date],
            )
        return (
            f" AND {alias}.entry_date <= ? "
            f"AND ({alias}.exit_date IS NULL OR {alias}.exit_date = '' OR {alias}.exit_date >= ?)",
            [effective_end, effective_end],
        )

    if population == "exited":
        if start_date and end_date:
            return (
                f" AND {alias}.exit_date IS NOT NULL "
                f"AND {alias}.exit_date <> '' "
                f"AND {alias}.exit_date >= ? "
                f"AND {alias}.exit_date <= ?",
                [start_date, end_date],
            )
        return (
            f" AND {alias}.exit_date IS NOT NULL "
            f"AND {alias}.exit_date <> ''",
            [],
        )

    if start_date and end_date:
        return (
            f" AND {alias}.entry_date <= ? "
            f"AND ({alias}.exit_date IS NULL OR {alias}.exit_date = '' OR {alias}.exit_date >= ?)",
            [end_date, start_date],
        )

    return "", []


def _entry_window_clause(alias: str, start_date: str | None, end_date: str | None) -> tuple[str, list[Any]]:
    if start_date and end_date:
        return f" AND {alias}.entry_date >= ? AND {alias}.entry_date <= ?", [start_date, end_date]
    return "", []


def _exit_window_clause(alias: str, start_date: str | None, end_date: str | None) -> tuple[str, list[Any]]:
    if start_date and end_date:
        return (
            f" AND {alias}.exit_date IS NOT NULL "
            f"AND {alias}.exit_date <> '' "
            f"AND {alias}.exit_date >= ? "
            f"AND {alias}.exit_date <= ?",
            [start_date, end_date],
        )
    return (
        f" AND {alias}.exit_date IS NOT NULL "
        f"AND {alias}.exit_date <> ''",
        [],
    )


def _base_enrollment_where(
    scope: str,
    population: str,
    date_range: str,
    start: str | None = None,
    end: str | None = None,
    alias: str = "pe",
) -> tuple[str, list[Any], str | None, str | None]:
    start_date, end_date = _window_dates(date_range, start, end)

    where = " WHERE 1=1"
    params: list[Any] = []

    scope_sql, scope_params = _scope_clause(alias, scope)
    pop_sql, pop_params = _population_clause(alias, population, start_date, end_date)

    where += scope_sql + pop_sql
    params.extend(scope_params)
    params.extend(pop_params)

    return where, params, start_date, end_date


def _fetch_count(sql: str, params: list[Any]) -> int:
    row = db_fetchone(sql, tuple(params))
    return _to_int(_row_get(row, "total", 0, 0), 0)


def _fetch_avg(sql: str, params: list[Any], key: str = "avg_value") -> float:
    row = db_fetchone(sql, tuple(params))
    return _to_float(_row_get(row, key, 0, 0.0), 0.0)


def _fetch_grouped_rows(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    rows = db_fetchall(sql, tuple(params)) or []
    output: list[dict[str, Any]] = []

    for row in rows:
        label = _row_get(row, "label", 0, "Unknown")
        total = _to_int(_row_get(row, "total", 1, 0), 0)
        output.append(
            {
                "label": label or "Unknown",
                "value": total,
                "display_value": mask_small_counts(total),
            }
        )

    return output


def _get_filtered_served_total(
    scope: str,
    population: str,
    date_range: str,
    start: str | None = None,
    end: str | None = None,
) -> int:
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    return _fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        """,
        where_params,
    )


def _get_current_active_count_for_scope(scope: str) -> int:
    normalized_scope = _normalize_scope(scope)
    scope_sql, scope_params = _scope_clause("pe", normalized_scope)

    return _fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        AND pe.entry_date <= ?
        AND (pe.exit_date IS NULL OR pe.exit_date = '' OR pe.exit_date >= ?)
        """,
        scope_params + [_iso_today(), _iso_today()],
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
    normalized_scope = _normalize_scope(scope)

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
    normalized_scope = _normalize_scope(scope)
    normalized_population = _normalize_population(population)
    normalized_date_range = _normalize_date_range_key(date_range)

    where_sql, where_params, start_date, end_date = _base_enrollment_where(
        normalized_scope,
        normalized_population,
        normalized_date_range,
        start,
        end,
        alias="pe",
    )

    women_served = _fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        """,
        where_params,
    )

    scope_sql, scope_params = _scope_clause("pe", normalized_scope)

    entry_sql, entry_params = _entry_window_clause("pe", start_date, end_date)
    women_admitted = _fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        {entry_sql}
        """,
        scope_params + entry_params,
    )

    exit_sql, exit_params = _exit_window_clause("pe", start_date, end_date)
    women_exited = _fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        {exit_sql}
        """,
        scope_params + exit_params,
    )

    graduates = _fetch_count(
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
        days = _days_between(_row_get(row, "entry_date", 0), _row_get(row, "exit_date", 1))
        if days is not None and days >= 0:
            stay_lengths.append(days)

    average_length_of_stay_days = round(sum(stay_lengths) / len(stay_lengths), 1) if stay_lengths else 0.0

    current_active = _fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        WHERE 1=1
        {scope_sql}
        AND pe.entry_date <= ?
        AND (pe.exit_date IS NULL OR pe.exit_date = '' OR pe.exit_date >= ?)
        """,
        scope_params + [_iso_today(), _iso_today()],
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
    where_sql, where_params, _, _ = _base_enrollment_where(
        "total_program",
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    rows = db_fetchall(
        f"""
        SELECT {_shelter_expr('pe')} AS shelter_key, COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        {where_sql}
        GROUP BY {_shelter_expr('pe')}
        ORDER BY total DESC, shelter_key
        """,
        tuple(where_params),
    ) or []

    merged: dict[str, int] = {}
    for row in rows:
        raw_key = _row_get(row, "shelter_key", 0, "")
        normalized_key = _normalize_shelter_value(raw_key)
        value = _to_int(_row_get(row, "total", 1, 0), 0)
        merged[normalized_key] = merged.get(normalized_key, 0) + value

    total = sum(merged.values()) or 0
    output: list[dict[str, Any]] = []

    for shelter_key in sorted(merged.keys()):
        value = merged[shelter_key]
        pct = round((value / total) * 100, 1) if total else 0.0
        output.append(
            {
                "label": _display_shelter_label(shelter_key),
                "value": value,
                "display_value": mask_small_counts(value),
                "percentage": pct,
            }
        )

    output.sort(key=lambda item: (-item["value"], item["label"]))
    return output


def get_demographics(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    gender_rows = _fetch_grouped_rows(
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

    race_rows = _fetch_grouped_rows(
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

    marital_rows = _fetch_grouped_rows(
        f"""
        SELECT COALESCE(NULLIF(TRIM(r.marital_status), ''), 'Unknown') AS label,
               COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        {where_sql}
        GROUP BY COALESCE(NULLIF(TRIM(r.marital_status), ''), 'Unknown')
        ORDER BY total DESC, label
        """,
        where_params,
    )

    veteran_yes = _fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.veteran = 1
        """,
        where_params,
    )

    disability_yes = _fetch_count(
        f"""
        SELECT COUNT(DISTINCT pe.resident_id) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.disability = 1
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


def get_family_composition(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    family_row = db_fetchone(
        f"""
        SELECT
            COUNT(DISTINCT CASE
                WHEN COALESCE(fs.kids_at_dwc, 0) > 0
                  OR COALESCE(fs.kids_served_outside_under_18, 0) > 0
                THEN pe.resident_id
            END) AS residents_with_children,
            COALESCE(SUM(fs.kids_at_dwc), 0) AS children_in_shelter,
            COALESCE(SUM(fs.kids_served_outside_under_18), 0) AS children_out_of_shelter,
            COALESCE(SUM(fs.kids_ages_0_5), 0) AS ages_0_5,
            COALESCE(SUM(fs.kids_ages_6_11), 0) AS ages_6_11,
            COALESCE(SUM(fs.kids_ages_12_17), 0) AS ages_12_17,
            COALESCE(SUM(fs.kids_reunited_while_in_program), 0) AS reunited,
            COALESCE(SUM(fs.healthy_babies_born_at_dwc), 0) AS babies_born
        FROM program_enrollments pe
        LEFT JOIN family_snapshots fs ON fs.enrollment_id = pe.id
        {where_sql}
        """,
        tuple(where_params),
    )

    residents_with_children = _to_int(_row_get(family_row, "residents_with_children", 0, 0), 0)
    children_in_shelter = _to_int(_row_get(family_row, "children_in_shelter", 1, 0), 0)
    children_out_of_shelter = _to_int(_row_get(family_row, "children_out_of_shelter", 2, 0), 0)
    ages_0_5 = _to_int(_row_get(family_row, "ages_0_5", 3, 0), 0)
    ages_6_11 = _to_int(_row_get(family_row, "ages_6_11", 4, 0), 0)
    ages_12_17 = _to_int(_row_get(family_row, "ages_12_17", 5, 0), 0)
    reunited = _to_int(_row_get(family_row, "reunited", 6, 0), 0)
    babies_born = _to_int(_row_get(family_row, "babies_born", 7, 0), 0)

    return {
        "residents_with_children": residents_with_children,
        "residents_with_children_display": mask_small_counts(residents_with_children),
        "children_in_shelter": children_in_shelter,
        "children_in_shelter_display": mask_small_counts(children_in_shelter),
        "children_out_of_shelter": children_out_of_shelter,
        "children_out_of_shelter_display": mask_small_counts(children_out_of_shelter),
        "child_age_groups": [
            {"label": "Ages 0 to 5", "value": ages_0_5, "display_value": mask_small_counts(ages_0_5)},
            {"label": "Ages 6 to 11", "value": ages_6_11, "display_value": mask_small_counts(ages_6_11)},
            {"label": "Ages 12 to 17", "value": ages_12_17, "display_value": mask_small_counts(ages_12_17)},
        ],
        "children_reunited": reunited,
        "children_reunited_display": mask_small_counts(reunited),
        "healthy_babies_born": babies_born,
        "healthy_babies_born_display": mask_small_counts(babies_born),
    }


def get_recovery_and_sobriety(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    primary_substances = _fetch_grouped_rows(
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

    avg_days_sober_at_entry = _fetch_avg(
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
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    ace_avg = _fetch_avg(
        f"""
        SELECT AVG(ia.ace_score) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    sexual_survivor = _fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.sexual_survivor = 1
        """,
        where_params,
    )

    dv_survivor = _fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.dv_survivor = 1
        """,
        where_params,
    )

    trafficking_survivor = _fetch_count(
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
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    felony = _fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.entry_felony_conviction = 1
        """,
        where_params,
    )

    parole = _fetch_count(
        f"""
        SELECT COUNT(*) AS total
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        AND ia.entry_parole_probation = 1
        """,
        where_params,
    )

    drug_court = _fetch_count(
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
    where_sql, where_params, _, _ = _base_enrollment_where(
        _normalize_scope(scope),
        _normalize_population(population),
        _normalize_date_range_key(date_range),
        start,
        end,
        alias="pe",
    )

    avg_income_at_entry = _fetch_avg(
        f"""
        SELECT AVG(ia.income_at_entry) AS avg_value
        FROM program_enrollments pe
        JOIN intake_assessments ia ON ia.enrollment_id = pe.id
        {where_sql}
        """,
        where_params,
    )

    avg_income_at_exit = _fetch_avg(
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
    avg_improvement = _to_float(_row_get(improvement_row, "avg_value", 0, 0.0), 0.0)

    education_entry = _fetch_grouped_rows(
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

    education_exit = _fetch_grouped_rows(
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

    return {
        "average_income_at_entry": round(avg_income_at_entry, 2),
        "average_income_at_exit": round(avg_income_at_exit, 2),
        "average_income_improvement": round(avg_improvement, 2),
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
    normalized_scope = _normalize_scope(scope)
    start_date, end_date = _window_dates(_normalize_date_range_key(date_range), start, end)
    scope_sql, scope_params = _scope_clause("pe", normalized_scope)

    exit_window_sql = ""
    exit_window_params: list[Any] = []
    if start_date and end_date:
        exit_window_sql = " AND ea.date_exit_dwc >= ? AND ea.date_exit_dwc <= ?"
        exit_window_params = [start_date, end_date]

    graduates = _fetch_count(
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

    leave_ama = _fetch_count(
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

    exit_reasons = _fetch_grouped_rows(
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

    total_exits = sum(item["value"] for item in exit_reasons)

    return {
        "graduates": graduates,
        "graduates_display": mask_small_counts(graduates),
        "leave_ama": leave_ama,
        "leave_ama_display": mask_small_counts(leave_ama),
        "total_exit_records": total_exits,
        "total_exit_records_display": mask_small_counts(total_exits),
        "exit_reasons": exit_reasons,
    }


def get_dashboard_statistics(
    scope: str = "total_program",
    population: str = "all",
    date_range: str = "all_time",
    start: str | None = None,
    end: str | None = None,
) -> dict[str, Any]:
    normalized_scope = _normalize_scope(scope)
    normalized_population = _normalize_population(population)
    normalized_date_range = _normalize_date_range_key(date_range)
    start_date, end_date = _window_dates(normalized_date_range, start, end)

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
