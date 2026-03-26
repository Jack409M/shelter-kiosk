from __future__ import annotations

from datetime import date, datetime
from typing import Any

from core.db import db_fetchall, db_fetchone
from core.helpers import shelter_display
from core.report_filters import mask_small_counts, resolve_date_range


def row_get(row: Any, key: str, index: int | None = None, default: Any = None) -> Any:
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


def to_int(value: Any, default: int = 0) -> int:
    if value in (None, "", False):
        return default
    try:
        return int(value)
    except Exception:
        try:
            return int(float(value))
        except Exception:
            return default


def to_float(value: Any, default: float = 0.0) -> float:
    if value in (None, "", False):
        return default
    try:
        return float(value)
    except Exception:
        return default


def iso_today() -> str:
    return date.today().isoformat()


def parse_iso_date(value: Any) -> date | None:
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


def days_between(start_value: Any, end_value: Any) -> int | None:
    start_date = parse_iso_date(start_value)
    end_date = parse_iso_date(end_value)
    if not start_date or not end_date:
        return None
    return (end_date - start_date).days


def normalize_shelter_value(value: Any) -> str:
    raw = str(value or "").strip().lower()

    if raw in {"abba house", "abba_house"}:
        return "abba"
    if raw in {"haven house", "haven_house"}:
        return "haven"
    if raw in {"gratitude house", "gratitude_house"}:
        return "gratitude"

    return raw


def display_shelter_label(value: Any) -> str:
    normalized = normalize_shelter_value(value)

    if normalized in {"abba", "haven", "gratitude"}:
        return shelter_display(normalized)

    raw = str(value or "").strip()
    return raw or "Unknown"


def shelter_expr(alias: str) -> str:
    return f"LOWER(TRIM(COALESCE({alias}.shelter, '')))"


def normalize_scope(scope: str | None) -> str:
    value = normalize_shelter_value(scope or "total_program")
    if value in {"abba", "haven", "gratitude", "total_program"}:
        return value
    return "total_program"


def normalize_population(population: str | None) -> str:
    value = (population or "all").strip().lower()
    if value in {"active", "exited", "all"}:
        return value
    return "all"


def normalize_date_range_key(date_range: str | None) -> str:
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


def scope_clause(alias: str, scope: str) -> tuple[str, list[Any]]:
    if scope == "total_program":
        return "", []
    return f" AND {shelter_expr(alias)} IN (?, ?)", [scope, f"{scope} house"]


def window_dates(date_range: str, start: str | None = None, end: str | None = None) -> tuple[str | None, str | None]:
    resolved_start, resolved_end = resolve_date_range(date_range, start, end)
    return (
        resolved_start.isoformat() if resolved_start else None,
        resolved_end.isoformat() if resolved_end else None,
    )


def population_clause(
    alias: str,
    population: str,
    start_date: str | None,
    end_date: str | None,
) -> tuple[str, list[Any]]:
    if population == "active":
        effective_end = end_date or iso_today()
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


def entry_window_clause(alias: str, start_date: str | None, end_date: str | None) -> tuple[str, list[Any]]:
    if start_date and end_date:
        return f" AND {alias}.entry_date >= ? AND {alias}.entry_date <= ?", [start_date, end_date]
    return "", []


def exit_window_clause(alias: str, start_date: str | None, end_date: str | None) -> tuple[str, list[Any]]:
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


def base_enrollment_where(
    scope: str,
    population: str,
    date_range: str,
    start: str | None = None,
    end: str | None = None,
    alias: str = "pe",
) -> tuple[str, list[Any], str | None, str | None]:
    start_date, end_date = window_dates(date_range, start, end)

    where = " WHERE 1=1"
    params: list[Any] = []

    scope_sql, scope_params = scope_clause(alias, scope)
    pop_sql, pop_params = population_clause(alias, population, start_date, end_date)

    where += scope_sql + pop_sql
    params.extend(scope_params)
    params.extend(pop_params)

    return where, params, start_date, end_date


def fetch_count(sql: str, params: list[Any]) -> int:
    row = db_fetchone(sql, tuple(params))
    return to_int(row_get(row, "total", 0, 0), 0)


def fetch_avg(sql: str, params: list[Any], key: str = "avg_value") -> float:
    row = db_fetchone(sql, tuple(params))
    return to_float(row_get(row, key, 0, 0.0), 0.0)


def fetch_grouped_rows(sql: str, params: list[Any]) -> list[dict[str, Any]]:
    rows = db_fetchall(sql, tuple(params)) or []
    output: list[dict[str, Any]] = []

    for row in rows:
        label = row_get(row, "label", 0, "Unknown")
        total = to_int(row_get(row, "total", 1, 0), 0)
        output.append(
            {
                "label": label or "Unknown",
                "value": total,
                "display_value": mask_small_counts(total),
            }
        )

    return output
