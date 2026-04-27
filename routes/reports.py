from __future__ import annotations

from datetime import UTC, datetime, timedelta
from statistics import median
from zoneinfo import ZoneInfo

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_roles, require_shelter
from core.db import db_execute, db_fetchall
from core.kiosk_activity_categories import (
    VOLUNTEER_PARENT_ACTIVITY_KEY,
    load_kiosk_activity_categories_for_shelter,
)
from core.metrics_registry import PROGRAM_METRICS
from core.program_statistics import get_dashboard_statistics
from core.runtime import init_db

reports = Blueprint("reports", __name__)


_ALLOWED_SCOPES = {"total_program", "abba", "haven", "gratitude"}
_ALLOWED_POPULATIONS = {"active", "exited", "all"}
_ALLOWED_DATE_RANGES = {
    "this_month",
    "last_month",
    "this_quarter",
    "this_year",
    "last_year",
    "all_time",
    "custom",
}

_DASHBOARD_KEY = "demographics_dashboard"
_MAX_FAVORITES = 6
_ACTIVITY_REPORT_SHELTERS = [
    ("abba", "Abba House"),
    ("haven", "Haven House"),
    ("gratitude", "Gratitude House"),
]
_ACTIVITY_SORT_OPTIONS = {
    "shelter": "Shelter",
    "resident": "Resident",
    "this_week_hours": "This Week Hours",
    "last_week_hours": "Last Week Hours",
    "all_time_hours": "All Time Hours",
    "this_week_meetings": "This Week Meetings",
    "last_week_meetings": "Last Week Meetings",
    "all_time_meetings": "All Time Meetings",
    "volunteer_hours": "Volunteer Hours",
    "productive_hours": "Productive Hours",
    "work_hours": "Work Hours",
}

_DEFAULT_TOP_METRIC_KEYS = [
    "women_served",
    "active_residents",
    "women_admitted",
    "women_exited",
    "graduates",
    "avg_stay",
]

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _clean_scope(value: str | None) -> str:
    cleaned = (value or "total_program").strip().lower()
    if cleaned in _ALLOWED_SCOPES:
        return cleaned
    return "total_program"


def _clean_population(value: str | None) -> str:
    cleaned = (value or "all").strip().lower()
    if cleaned in _ALLOWED_POPULATIONS:
        return cleaned
    return "all"


def _clean_date_range(value: str | None) -> str:
    cleaned = (value or "all_time").strip().lower()
    if cleaned in _ALLOWED_DATE_RANGES:
        return cleaned
    return "all_time"


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


def _clean_activity_report_shelter(value: str | None) -> str:
    cleaned = (value or "all").strip().lower()
    if cleaned in {"all", "abba", "haven", "gratitude"}:
        return cleaned
    return "all"


def _clean_activity_report_sort(value: str | None) -> str:
    cleaned = (value or "shelter").strip().lower()
    if cleaned in _ACTIVITY_SORT_OPTIONS:
        return cleaned
    return "shelter"


def _activity_report_sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _current_staff_user_id() -> int | None:
    raw_value = session.get("staff_user_id")
    if raw_value is None:
        return None

    try:
        return int(raw_value)
    except Exception:
        return None


def _favorite_redirect_response():
    scope = _clean_scope(request.values.get("scope"))
    population = _clean_population(request.values.get("population"))
    date_range = _clean_date_range(request.values.get("date_range"))
    start_date = _clean_iso_date(request.values.get("start_date"))
    end_date = _clean_iso_date(request.values.get("end_date"))

    query_args: dict[str, str] = {
        "scope": scope,
        "population": population,
        "date_range": date_range,
    }

    if date_range == "custom":
        if start_date:
            query_args["start_date"] = start_date
        if end_date:
            query_args["end_date"] = end_date

    return redirect(url_for("reports.demographics_dashboard", **query_args))


def _get_saved_favorite_metric_keys(staff_user_id: int) -> list[str]:
    rows = db_fetchall(
        """
        SELECT metric_key
        FROM user_dashboard_favorites
        WHERE user_id = ?
          AND dashboard_key = ?
        ORDER BY display_order ASC, id ASC
        """,
        (staff_user_id, _DASHBOARD_KEY),
    )

    metric_keys: list[str] = []

    for row in rows:
        metric_key = row["metric_key"] if isinstance(row, dict) else row[0]
        metric_key = (metric_key or "").strip()

        if metric_key in PROGRAM_METRICS and metric_key not in metric_keys:
            metric_keys.append(metric_key)

    return metric_keys


def _get_display_top_metric_keys(staff_user_id: int | None) -> list[str]:
    if not staff_user_id:
        return list(_DEFAULT_TOP_METRIC_KEYS)

    saved_metric_keys = _get_saved_favorite_metric_keys(staff_user_id)
    if saved_metric_keys:
        return saved_metric_keys[:_MAX_FAVORITES]

    return list(_DEFAULT_TOP_METRIC_KEYS)


def _format_metric_value(raw_value, metric: dict) -> str:
    if raw_value is None:
        return "-"

    if metric.get("currency"):
        try:
            return f"${float(raw_value):,.2f}"
        except Exception:
            return str(raw_value)

    if isinstance(raw_value, float):
        text = f"{raw_value:.1f}"
        if text.endswith(".0"):
            text = text[:-2]
    else:
        text = str(raw_value)

    suffix = metric.get("suffix", "")
    return f"{text}{suffix}"


def _build_metrics_values(stats: dict) -> dict[str, str]:
    metrics_values: dict[str, str] = {}

    for metric_key, metric in PROGRAM_METRICS.items():
        section_name = metric.get("section")
        field_name = metric.get("field")

        if not section_name or not field_name:
            metrics_values[metric_key] = "-"
            continue

        section_data = stats.get(section_name, {}) or {}
        raw_value = section_data.get(field_name)
        metrics_values[metric_key] = _format_metric_value(raw_value, metric)

    return metrics_values


def _build_top_stats(
    metric_keys: list[str],
    saved_metric_keys: list[str],
    metrics_values: dict[str, str],
) -> list[dict]:
    top_stats: list[dict] = []

    for metric_key in metric_keys:
        metric = PROGRAM_METRICS.get(metric_key)
        if not metric:
            continue

        top_stats.append(
            {
                "key": metric_key,
                "label": metric.get("label", metric_key),
                "value": metrics_values.get(metric_key, "-"),
                "is_favorite": metric_key in saved_metric_keys,
            }
        )

    return top_stats


def _resequence_favorites(staff_user_id: int) -> None:
    rows = db_fetchall(
        """
        SELECT id
        FROM user_dashboard_favorites
        WHERE user_id = ?
          AND dashboard_key = ?
        ORDER BY display_order ASC, id ASC
        """,
        (staff_user_id, _DASHBOARD_KEY),
    )

    for index, row in enumerate(rows, start=1):
        favorite_id = row["id"] if isinstance(row, dict) else row[0]
        db_execute(
            """
            UPDATE user_dashboard_favorites
            SET display_order = ?
            WHERE id = ?
            """,
            (index, favorite_id),
        )


def _parse_reorder_payload(payload) -> list[dict[str, int | str]]:
    if not isinstance(payload, dict):
        return []

    ordered_metrics = payload.get("ordered_metrics")
    if not isinstance(ordered_metrics, list):
        return []

    cleaned_items: list[dict[str, int | str]] = []
    seen_metric_keys: set[str] = set()

    for item in ordered_metrics:
        if not isinstance(item, dict):
            continue

        metric_key = str(item.get("metric_key") or "").strip()
        if not metric_key:
            continue

        if metric_key in seen_metric_keys:
            continue

        if metric_key not in PROGRAM_METRICS:
            continue

        seen_metric_keys.add(metric_key)
        cleaned_items.append(
            {
                "metric_key": metric_key,
                "display_order": len(cleaned_items) + 1,
            }
        )

    return cleaned_items


def _fmt_currency(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def _fmt_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "—"
    return f"{(numerator / denominator) * 100:.1f}%"


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return float(median(values))


def _average_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _income_band_for_value(value: float | None) -> str:
    if value is None:
        return "Unknown"
    if value < 1200:
        return "Under $1,200"
    if value < 1600:
        return "$1,200 to $1,599"
    if value < 2000:
        return "$1,600 to $1,999"
    return "$2,000 and above"


def _sort_income_band_key(label: str) -> int:
    order = {
        "Under $1,200": 1,
        "$1,200 to $1,599": 2,
        "$1,600 to $1,999": 3,
        "$2,000 and above": 4,
        "Unknown": 5,
    }
    return order.get(label, 99)


def _normalize_shelter_key(value: str | None) -> str:
    return (value or "").strip().lower()


def _activity_report_shelter_label(value: str | None) -> str:
    key = _normalize_shelter_key(value)
    for shelter_key, shelter_label in _ACTIVITY_REPORT_SHELTERS:
        if key == shelter_key:
            return shelter_label
    return (value or "").strip() or "Unknown"


def _utc_iso_to_local(dt_iso: str | None) -> datetime | None:
    raw_value = (dt_iso or "").strip()
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value)
    except Exception:
        return None

    try:
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed.astimezone(CHICAGO_TZ)
    except Exception:
        return None


def _start_of_week_local(any_local_dt: datetime) -> datetime:
    return (any_local_dt - timedelta(days=any_local_dt.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _safe_float(value) -> float | None:
    try:
        parsed = float(value)
    except Exception:
        return None
    if parsed <= 0:
        return None
    return parsed


def _normalized_hours_for_activity_row(row: dict) -> float | None:
    logged_hours = _safe_float(row.get("logged_hours"))
    if logged_hours is not None:
        return round(logged_hours, 4)

    start_local = row.get("obligation_start_local")
    planned_end_local = row.get("obligation_end_local")
    actual_end_local = row.get("actual_obligation_end_local")
    end_local = actual_end_local or planned_end_local

    if not start_local or not end_local:
        return None
    if end_local <= start_local:
        return None

    duration_hours = round((end_local - start_local).total_seconds() / 3600.0, 4)
    if duration_hours <= 0:
        return None

    return duration_hours


def _row_week_anchor_local(row: dict) -> datetime | None:
    return row.get("obligation_start_local") or row.get("event_time_local")


def _empty_activity_metrics() -> dict[str, float | int]:
    return {
        "this_week_hours": 0.0,
        "last_week_hours": 0.0,
        "all_time_hours": 0.0,
        "this_week_meetings": 0,
        "last_week_meetings": 0,
        "all_time_meetings": 0,
        "volunteer_hours": 0.0,
        "productive_hours": 0.0,
        "work_hours": 0.0,
    }


def _merge_activity_metrics(
    target: dict, hours: float, meetings: int, bucket_key: str, meta: dict
) -> None:
    target["all_time_hours"] += hours
    target["all_time_meetings"] += meetings

    if bucket_key == "this_week":
        target["this_week_hours"] += hours
        target["this_week_meetings"] += meetings
    elif bucket_key == "last_week":
        target["last_week_hours"] += hours
        target["last_week_meetings"] += meetings

    if meta.get("is_volunteer"):
        target["volunteer_hours"] += hours
    if meta.get("counts_as_productive"):
        target["productive_hours"] += hours
    if meta.get("counts_as_work"):
        target["work_hours"] += hours


def _finalize_activity_metrics(target: dict) -> None:
    for key in [
        "this_week_hours",
        "last_week_hours",
        "all_time_hours",
        "volunteer_hours",
        "productive_hours",
        "work_hours",
    ]:
        target[key] = round(float(target.get(key, 0.0) or 0.0), 2)

    for key in [
        "this_week_meetings",
        "last_week_meetings",
        "all_time_meetings",
    ]:
        target[key] = int(target.get(key, 0) or 0)


def _load_activity_category_registry() -> dict[str, dict[str, dict]]:
    registry: dict[str, dict[str, dict]] = {}

    for shelter_key, _shelter_label in _ACTIVITY_REPORT_SHELTERS:
        rows = load_kiosk_activity_categories_for_shelter(shelter_key)
        shelter_registry: dict[str, dict] = {}

        for row in rows or []:
            activity_label = (row.get("activity_label") or "").strip()
            if not activity_label:
                continue
            if not row.get("active"):
                continue

            shelter_registry[activity_label] = {
                "counts_as_work": bool(row.get("counts_as_work_hours")),
                "counts_as_productive": bool(row.get("counts_as_productive_hours")),
                "is_volunteer": (row.get("activity_key") or "").strip()
                == VOLUNTEER_PARENT_ACTIVITY_KEY,
            }

        registry[shelter_key] = shelter_registry

    return registry


def _parse_activity_note_value(note_text: str, prefixes: list[str]) -> str:
    for segment in (note_text or "").split(" | "):
        cleaned = segment.strip()
        if not cleaned:
            continue
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                return cleaned[len(prefix) :].strip()
    return ""


def _activity_source_label(event_type: str) -> str:
    if (event_type or "").strip() == "resident_daily_log":
        return "Resident Daily Log"
    return "Kiosk Check Out"


def _activity_detail_label(row: dict) -> str:
    note_text = str(row.get("note") or "")
    destination = (row.get("destination") or "").strip() or "Uncategorized"
    meeting_1 = _parse_activity_note_value(note_text, ["Meeting 1:"])
    meeting_2 = _parse_activity_note_value(note_text, ["Meeting 2:"])
    volunteer_detail = _parse_activity_note_value(note_text, ["Volunteer or Community Service:"])
    generic_detail = _parse_activity_note_value(note_text, ["Activity Detail:"])

    if meeting_1 and meeting_2:
        return f"{meeting_1} + {meeting_2}"
    if meeting_1:
        return meeting_1
    if volunteer_detail:
        return volunteer_detail
    if generic_detail:
        return generic_detail
    return destination


def _fetch_activity_report_rows() -> list[dict]:
    rows = db_fetchall(
        _activity_report_sql(
            """
            SELECT
                ae.id,
                ae.resident_id,
                ae.shelter,
                ae.event_type,
                ae.event_time,
                ae.destination,
                ae.note,
                ae.obligation_start_time,
                ae.obligation_end_time,
                ae.actual_obligation_end_time,
                ae.logged_hours,
                ae.meeting_count,
                r.first_name,
                r.last_name,
                r.is_active
            FROM attendance_events ae
            LEFT JOIN residents r
              ON r.id = ae.resident_id
            WHERE ae.event_type IN (%s, %s)
            ORDER BY ae.event_time DESC, ae.id DESC
            """,
            """
            SELECT
                ae.id,
                ae.resident_id,
                ae.shelter,
                ae.event_type,
                ae.event_time,
                ae.destination,
                ae.note,
                ae.obligation_start_time,
                ae.obligation_end_time,
                ae.actual_obligation_end_time,
                ae.logged_hours,
                ae.meeting_count,
                r.first_name,
                r.last_name,
                r.is_active
            FROM attendance_events ae
            LEFT JOIN residents r
              ON r.id = ae.resident_id
            WHERE ae.event_type IN (?, ?)
            ORDER BY ae.event_time DESC, ae.id DESC
            """,
        ),
        ("check_out", "resident_daily_log"),
    )

    normalized_rows: list[dict] = []
    for row in rows or []:
        item = dict(row)
        item["shelter_key"] = _normalize_shelter_key(item.get("shelter"))
        item["event_time_local"] = _utc_iso_to_local(item.get("event_time"))
        item["obligation_start_local"] = _utc_iso_to_local(item.get("obligation_start_time"))
        item["obligation_end_local"] = _utc_iso_to_local(item.get("obligation_end_time"))
        item["actual_obligation_end_local"] = _utc_iso_to_local(
            item.get("actual_obligation_end_time")
        )
        item["source_label"] = _activity_source_label(str(item.get("event_type") or ""))
        item["detail_label"] = _activity_detail_label(item)
        normalized_rows.append(item)

    return normalized_rows


def _sorted_activity_rows(rows: list[dict], sort_by: str, default_label_key: str) -> list[dict]:
    if sort_by in {"shelter", "resident"}:
        return sorted(
            rows,
            key=lambda item: (
                str(item.get(default_label_key) or "").lower(),
                str(item.get("shelter_label") or "").lower(),
            ),
        )

    return sorted(
        rows,
        key=lambda item: (
            -(float(item.get(sort_by, 0.0) or 0.0)),
            str(item.get(default_label_key) or "").lower(),
        ),
    )


def _build_activity_engagement_report(selected_shelter: str, sort_by: str) -> dict:
    category_registry = _load_activity_category_registry()
    attendance_rows = _fetch_activity_report_rows()

    now_local = datetime.now(CHICAGO_TZ)
    this_week_start = _start_of_week_local(now_local)
    last_week_start = this_week_start - timedelta(days=7)

    shelter_rows: dict[str, dict] = {}
    resident_rows: dict[tuple[str, int], dict] = {}
    category_rows: dict[tuple[str, str], dict] = {}
    source_rows: dict[str, dict] = {}
    detail_rows: dict[tuple[str, str, str], dict] = {}
    recent_activity_rows: list[dict] = []

    for row in attendance_rows:
        shelter_key = row.get("shelter_key") or ""
        if shelter_key not in {item[0] for item in _ACTIVITY_REPORT_SHELTERS}:
            continue
        if selected_shelter != "all" and shelter_key != selected_shelter:
            continue

        week_anchor = _row_week_anchor_local(row)
        if not week_anchor:
            continue

        if week_anchor >= this_week_start:
            bucket_key = "this_week"
        elif week_anchor >= last_week_start:
            bucket_key = "last_week"
        else:
            bucket_key = "older"

        category_label = (row.get("destination") or "").strip() or "Uncategorized"
        detail_label = (row.get("detail_label") or "").strip() or category_label
        source_label = (row.get("source_label") or "").strip() or "Unknown"
        category_meta = category_registry.get(shelter_key, {}).get(
            category_label,
            {
                "counts_as_work": False,
                "counts_as_productive": False,
                "is_volunteer": False,
            },
        )

        hours = _normalized_hours_for_activity_row(row) or 0.0
        meetings = int(row.get("meeting_count") or 0)

        shelter_bucket = shelter_rows.setdefault(
            shelter_key,
            {
                "shelter_key": shelter_key,
                "shelter_label": _activity_report_shelter_label(shelter_key),
                **_empty_activity_metrics(),
            },
        )
        _merge_activity_metrics(shelter_bucket, hours, meetings, bucket_key, category_meta)

        resident_id = int(row.get("resident_id") or 0)
        resident_name = (
            " ".join(part for part in [row.get("first_name"), row.get("last_name")] if part).strip()
            or f"Resident {resident_id}"
        )
        resident_bucket = resident_rows.setdefault(
            (shelter_key, resident_id),
            {
                "resident_id": resident_id,
                "resident_name": resident_name,
                "shelter_key": shelter_key,
                "shelter_label": _activity_report_shelter_label(shelter_key),
                **_empty_activity_metrics(),
            },
        )
        _merge_activity_metrics(resident_bucket, hours, meetings, bucket_key, category_meta)

        category_bucket = category_rows.setdefault(
            (shelter_key, category_label),
            {
                "category_label": category_label,
                "shelter_key": shelter_key,
                "shelter_label": _activity_report_shelter_label(shelter_key),
                **_empty_activity_metrics(),
            },
        )
        _merge_activity_metrics(category_bucket, hours, meetings, bucket_key, category_meta)

        source_bucket = source_rows.setdefault(
            source_label,
            {
                "source_label": source_label,
                **_empty_activity_metrics(),
            },
        )
        _merge_activity_metrics(source_bucket, hours, meetings, bucket_key, category_meta)

        detail_bucket = detail_rows.setdefault(
            (shelter_key, category_label, detail_label),
            {
                "detail_label": detail_label,
                "category_label": category_label,
                "shelter_key": shelter_key,
                "shelter_label": _activity_report_shelter_label(shelter_key),
                "source_label": source_label,
                **_empty_activity_metrics(),
            },
        )
        _merge_activity_metrics(detail_bucket, hours, meetings, bucket_key, category_meta)

        recent_activity_rows.append(
            {
                "resident_name": resident_name,
                "shelter_label": _activity_report_shelter_label(shelter_key),
                "source_label": source_label,
                "category_label": category_label,
                "detail_label": detail_label,
                "event_time_local": row.get("event_time_local"),
                "event_time_label": row.get("event_time_local").strftime("%b %d, %Y %I:%M %p")
                if row.get("event_time_local")
                else "",
                "hours": round(hours, 2),
                "meetings": meetings,
            }
        )

    for bucket in shelter_rows.values():
        _finalize_activity_metrics(bucket)
    for bucket in resident_rows.values():
        _finalize_activity_metrics(bucket)
    for bucket in category_rows.values():
        _finalize_activity_metrics(bucket)
    for bucket in source_rows.values():
        _finalize_activity_metrics(bucket)
    for bucket in detail_rows.values():
        _finalize_activity_metrics(bucket)

    shelter_summary_rows = _sorted_activity_rows(
        list(shelter_rows.values()), sort_by, "shelter_label"
    )
    resident_detail_rows = _sorted_activity_rows(
        list(resident_rows.values()), sort_by, "resident_name"
    )
    category_detail_rows = sorted(
        list(category_rows.values()),
        key=lambda item: (
            str(item.get("shelter_label") or "").lower(),
            str(item.get("category_label") or "").lower(),
        ),
    )
    source_summary_rows = sorted(
        list(source_rows.values()),
        key=lambda item: str(item.get("source_label") or "").lower(),
    )
    detail_breakdown_rows = sorted(
        list(detail_rows.values()),
        key=lambda item: (
            str(item.get("shelter_label") or "").lower(),
            str(item.get("category_label") or "").lower(),
            str(item.get("detail_label") or "").lower(),
        ),
    )
    recent_activity_rows = sorted(
        recent_activity_rows,
        key=lambda item: item.get("event_time_local") or datetime.min.replace(tzinfo=CHICAGO_TZ),
        reverse=True,
    )[:50]

    grand_totals = {
        "shelter_count": len(shelter_summary_rows),
        "resident_count": len(resident_detail_rows),
        "category_count": len(category_detail_rows),
        "detail_count": len(detail_breakdown_rows),
        "source_count": len(source_summary_rows),
        **_empty_activity_metrics(),
    }

    for row in shelter_summary_rows:
        for metric_key in _empty_activity_metrics():
            grand_totals[metric_key] += row.get(metric_key, 0)

    _finalize_activity_metrics(grand_totals)

    return {
        "selected_shelter": selected_shelter,
        "selected_shelter_label": "All Shelters"
        if selected_shelter == "all"
        else _activity_report_shelter_label(selected_shelter),
        "sort_by": sort_by,
        "sort_options": [
            {"value": key, "label": label} for key, label in _ACTIVITY_SORT_OPTIONS.items()
        ],
        "shelter_options": [
            {"value": "all", "label": "All Shelters"},
            *[
                {"value": shelter_key, "label": shelter_label}
                for shelter_key, shelter_label in _ACTIVITY_REPORT_SHELTERS
            ],
        ],
        "shelter_summary_rows": shelter_summary_rows,
        "resident_detail_rows": resident_detail_rows,
        "category_detail_rows": category_detail_rows,
        "source_summary_rows": source_summary_rows,
        "detail_breakdown_rows": detail_breakdown_rows,
        "recent_activity_rows": recent_activity_rows,
        "grand_totals": grand_totals,
        "current_week_label": f"This Week So Far ({this_week_start.strftime('%b %d, %Y')} through today)",
        "last_week_label": f"Last Week ({last_week_start.strftime('%b %d, %Y')} to {(this_week_start - timedelta(days=1)).strftime('%b %d, %Y')})",
    }


def _fetch_graduation_income_study_rows(
    scope: str, start_date: str | None, end_date: str | None
) -> list[dict]:
    scope_filter_sql = ""
    params: list = []

    if scope != "total_program":
        scope_filter_sql += " AND LOWER(COALESCE(pe.shelter, '')) = ?"
        params.append(scope)

    if start_date:
        scope_filter_sql += " AND COALESCE(ea.date_graduated, ea.date_exit_dwc, '') >= ?"
        params.append(start_date)

    if end_date:
        scope_filter_sql += " AND COALESCE(ea.date_graduated, ea.date_exit_dwc, '') <= ?"
        params.append(end_date)

    rows = db_fetchall(
        f"""
        SELECT
            pe.id AS enrollment_id,
            pe.resident_id,
            pe.shelter,
            pe.entry_date,
            pe.exit_date,
            r.first_name,
            r.last_name,
            r.resident_identifier,
            r.resident_code,
            ea.date_graduated,
            ea.date_exit_dwc,
            ea.exit_category,
            ea.exit_reason,
            ea.graduate_dwc,
            ea.income_at_exit,
            ea.graduation_income_snapshot,
            f.followup_type,
            f.followup_date,
            f.income_at_followup,
            f.sober_at_followup
        FROM program_enrollments pe
        JOIN residents r ON r.id = pe.resident_id
        JOIN exit_assessments ea ON ea.enrollment_id = pe.id
        LEFT JOIN followups f ON f.enrollment_id = pe.id
        WHERE COALESCE(ea.exit_category, '') = 'Successful Completion'
          AND COALESCE(ea.exit_reason, '') = 'Program Graduated'
          AND COALESCE(ea.graduate_dwc, 0) = 1
          {scope_filter_sql}
        ORDER BY COALESCE(ea.date_graduated, ea.date_exit_dwc, '') DESC, pe.id DESC
        """,
        tuple(params),
    )
    return [dict(row) for row in rows]


def _build_graduation_income_study(
    scope: str, start_date: str | None, end_date: str | None
) -> dict:
    raw_rows = _fetch_graduation_income_study_rows(scope, start_date, end_date)

    graduates: dict[int, dict] = {}

    for row in raw_rows:
        enrollment_id = row["enrollment_id"]
        graduate = graduates.get(enrollment_id)
        if not graduate:
            snapshot_income = row.get("graduation_income_snapshot")
            if snapshot_income in (None, ""):
                snapshot_income = row.get("income_at_exit")

            graduate = {
                "enrollment_id": enrollment_id,
                "resident_id": row.get("resident_id"),
                "resident_name": " ".join(
                    part for part in [row.get("first_name"), row.get("last_name")] if part
                ).strip(),
                "resident_display_id": row.get("resident_identifier")
                or row.get("resident_code")
                or str(row.get("resident_id") or ""),
                "shelter": row.get("shelter"),
                "date_graduated": row.get("date_graduated") or row.get("date_exit_dwc"),
                "graduation_income_snapshot": float(snapshot_income)
                if snapshot_income not in (None, "")
                else None,
                "followups": {},
            }
            graduates[enrollment_id] = graduate

        followup_type = (row.get("followup_type") or "").strip()
        if followup_type not in {"6_month", "1_year"}:
            continue

        existing = graduate["followups"].get(followup_type)
        current_date = row.get("followup_date") or ""
        existing_date = existing.get("followup_date") if existing else ""

        if existing and existing_date >= current_date:
            continue

        graduate["followups"][followup_type] = {
            "followup_date": current_date,
            "income_at_followup": float(row["income_at_followup"])
            if row.get("income_at_followup") not in (None, "")
            else None,
            "sober_at_followup": bool(int(row.get("sober_at_followup") or 0)),
        }

    graduate_rows = list(graduates.values())

    six_month_sober_incomes: list[float] = []
    six_month_not_sober_incomes: list[float] = []
    one_year_sober_incomes: list[float] = []
    one_year_not_sober_incomes: list[float] = []

    band_rollup: dict[str, dict] = {}

    six_month_count = 0
    one_year_count = 0
    six_month_sober_count = 0
    one_year_sober_count = 0

    detail_rows: list[dict] = []

    for graduate in graduate_rows:
        grad_income = graduate["graduation_income_snapshot"]
        band_label = _income_band_for_value(grad_income)

        if band_label not in band_rollup:
            band_rollup[band_label] = {
                "band_label": band_label,
                "graduates": 0,
                "six_month_with_followup": 0,
                "six_month_sober": 0,
                "one_year_with_followup": 0,
                "one_year_sober": 0,
            }

        band_rollup[band_label]["graduates"] += 1

        six_month = graduate["followups"].get("6_month")
        one_year = graduate["followups"].get("1_year")

        detail_row = {
            "resident_name": graduate["resident_name"],
            "resident_display_id": graduate["resident_display_id"],
            "shelter": graduate["shelter"],
            "date_graduated": graduate["date_graduated"],
            "graduation_income_snapshot": grad_income,
            "income_band": band_label,
            "six_month_date": six_month.get("followup_date") if six_month else "",
            "six_month_sober": six_month.get("sober_at_followup") if six_month else None,
            "one_year_date": one_year.get("followup_date") if one_year else "",
            "one_year_sober": one_year.get("sober_at_followup") if one_year else None,
        }
        detail_rows.append(detail_row)

        if six_month:
            six_month_count += 1
            band_rollup[band_label]["six_month_with_followup"] += 1
            if six_month["sober_at_followup"]:
                six_month_sober_count += 1
                band_rollup[band_label]["six_month_sober"] += 1
                if grad_income is not None:
                    six_month_sober_incomes.append(grad_income)
            else:
                if grad_income is not None:
                    six_month_not_sober_incomes.append(grad_income)

        if one_year:
            one_year_count += 1
            band_rollup[band_label]["one_year_with_followup"] += 1
            if one_year["sober_at_followup"]:
                one_year_sober_count += 1
                band_rollup[band_label]["one_year_sober"] += 1
                if grad_income is not None:
                    one_year_sober_incomes.append(grad_income)
            else:
                if grad_income is not None:
                    one_year_not_sober_incomes.append(grad_income)

    band_rows = []
    for band_label in sorted(band_rollup.keys(), key=_sort_income_band_key):
        band = band_rollup[band_label]
        band_rows.append(
            {
                **band,
                "six_month_sober_rate": _fmt_percent(
                    band["six_month_sober"], band["six_month_with_followup"]
                ),
                "one_year_sober_rate": _fmt_percent(
                    band["one_year_sober"], band["one_year_with_followup"]
                ),
            }
        )

    detail_rows.sort(
        key=lambda row: (
            row["date_graduated"] or "",
            row["resident_name"] or "",
        ),
        reverse=True,
    )

    return {
        "scope": scope,
        "start_date": start_date,
        "end_date": end_date,
        "graduate_count": len(graduate_rows),
        "six_month_followup_count": six_month_count,
        "one_year_followup_count": one_year_count,
        "six_month_sober_count": six_month_sober_count,
        "one_year_sober_count": one_year_sober_count,
        "six_month_sober_rate": _fmt_percent(six_month_sober_count, six_month_count),
        "one_year_sober_rate": _fmt_percent(one_year_sober_count, one_year_count),
        "avg_income_six_month_sober": _average_or_none(six_month_sober_incomes),
        "avg_income_six_month_not_sober": _average_or_none(six_month_not_sober_incomes),
        "avg_income_one_year_sober": _average_or_none(one_year_sober_incomes),
        "avg_income_one_year_not_sober": _average_or_none(one_year_not_sober_incomes),
        "median_income_six_month_sober": _median_or_none(six_month_sober_incomes),
        "median_income_six_month_not_sober": _median_or_none(six_month_not_sober_incomes),
        "median_income_one_year_sober": _median_or_none(one_year_sober_incomes),
        "median_income_one_year_not_sober": _median_or_none(one_year_not_sober_incomes),
        "band_rows": band_rows,
        "detail_rows": detail_rows,
        "fmt_currency": _fmt_currency,
    }


@reports.route("/staff/reports", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def reports_index():
    return render_template(
        "reports/index.html",
        title="Reports",
    )


@reports.route("/staff/reports/activity-engagement", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def activity_engagement_report():
    init_db()

    selected_shelter = _clean_activity_report_shelter(request.args.get("shelter"))
    sort_by = _clean_activity_report_sort(request.args.get("sort_by"))
    report = _build_activity_engagement_report(selected_shelter=selected_shelter, sort_by=sort_by)

    return render_template(
        "reports/activity_engagement.html",
        title="Activity Engagement Report",
        report=report,
    )


@reports.route("/staff/reports/demographics/favorites/toggle", methods=["POST"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def toggle_demographics_favorite():
    init_db()

    staff_user_id = _current_staff_user_id()
    if not staff_user_id:
        flash("Unable to save favorite stats for this session.", "error")
        return _favorite_redirect_response()

    metric_key = (request.form.get("metric_key") or "").strip()

    if metric_key not in PROGRAM_METRICS:
        flash("That metric cannot be pinned.", "error")
        return _favorite_redirect_response()

    existing_metric_keys = _get_saved_favorite_metric_keys(staff_user_id)

    if metric_key in existing_metric_keys:
        db_execute(
            """
            DELETE FROM user_dashboard_favorites
            WHERE user_id = ?
              AND dashboard_key = ?
              AND metric_key = ?
            """,
            (staff_user_id, _DASHBOARD_KEY, metric_key),
        )

        _resequence_favorites(staff_user_id)

        log_action(
            "dashboard_favorite",
            None,
            session.get("shelter"),
            staff_user_id,
            "favorite_removed",
            f"dashboard_key={_DASHBOARD_KEY} metric_key={metric_key}",
        )

        return _favorite_redirect_response()

    if len(existing_metric_keys) >= _MAX_FAVORITES:
        flash("You can pin up to six stats.", "error")
        return _favorite_redirect_response()

    next_display_order = len(existing_metric_keys) + 1

    db_execute(
        """
        INSERT INTO user_dashboard_favorites (
            user_id,
            dashboard_key,
            metric_key,
            display_order,
            created_at
        )
        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        """,
        (staff_user_id, _DASHBOARD_KEY, metric_key, next_display_order),
    )

    log_action(
        "dashboard_favorite",
        None,
        session.get("shelter"),
        staff_user_id,
        "favorite_added",
        f"dashboard_key={_DASHBOARD_KEY} metric_key={metric_key} display_order={next_display_order}",
    )

    return _favorite_redirect_response()


@reports.route("/staff/reports/demographics/favorites/order", methods=["POST"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def update_demographics_favorite_order():
    init_db()

    staff_user_id = _current_staff_user_id()
    if not staff_user_id:
        return {"ok": False, "error": "missing_staff_user"}, 400

    saved_metric_keys = _get_saved_favorite_metric_keys(staff_user_id)
    if not saved_metric_keys:
        return {"ok": False, "error": "no_saved_favorites"}, 400

    payload = request.get_json(silent=True) or {}
    ordered_items = _parse_reorder_payload(payload)

    if not ordered_items:
        return {"ok": False, "error": "invalid_payload"}, 400

    ordered_metric_keys = [item["metric_key"] for item in ordered_items]
    saved_metric_key_set = set(saved_metric_keys)
    ordered_metric_key_set = set(ordered_metric_keys)

    if ordered_metric_key_set != saved_metric_key_set:
        return {"ok": False, "error": "favorites_mismatch"}, 400

    for item in ordered_items:
        db_execute(
            """
            UPDATE user_dashboard_favorites
            SET display_order = ?
            WHERE user_id = ?
              AND dashboard_key = ?
              AND metric_key = ?
            """,
            (
                item["display_order"],
                staff_user_id,
                _DASHBOARD_KEY,
                item["metric_key"],
            ),
        )

    _resequence_favorites(staff_user_id)

    log_action(
        "dashboard_favorite",
        None,
        session.get("shelter"),
        staff_user_id,
        "favorite_reordered",
        f"dashboard_key={_DASHBOARD_KEY} metric_keys={','.join(ordered_metric_keys)}",
    )

    return {"ok": True}


@reports.route("/staff/reports/demographics", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def demographics_dashboard():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    population = _clean_population(request.args.get("population"))
    date_range = _clean_date_range(request.args.get("date_range"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))

    if date_range != "custom":
        start_date = None
        end_date = None

    stats = get_dashboard_statistics(
        scope=scope,
        population=population,
        date_range=date_range,
        start=start_date,
        end=end_date,
    )

    stat_errors: dict[str, str] = {}

    for key, value in list(stats.items()):
        if key == "filters":
            continue
        if isinstance(value, dict) and "ok" in value and "data" in value:
            if not value.get("ok") and value.get("error"):
                stat_errors[key] = value["error"]
            stats[key] = value.get("data", {})

    staff_user_id = _current_staff_user_id()
    saved_favorite_metric_keys = (
        _get_saved_favorite_metric_keys(staff_user_id) if staff_user_id else []
    )
    display_top_metric_keys = _get_display_top_metric_keys(staff_user_id)
    metrics_values = _build_metrics_values(stats)
    top_stats = _build_top_stats(
        display_top_metric_keys,
        saved_favorite_metric_keys,
        metrics_values,
    )

    return render_template(
        "reports/demographics.html",
        title="78 Column Report",
        filters=stats["filters"],
        top_stats=top_stats,
        favorite_metric_keys=saved_favorite_metric_keys,
        stat_errors=stat_errors,
        program_snapshot=stats["program_snapshot"],
        scope_comparison=stats["scope_comparison"],
        capacity_snapshot=stats["capacity_snapshot"],
        shelter_distribution=stats["shelter_distribution"],
        demographics=stats["demographics"],
        family_composition=stats["family_composition"],
        recovery_and_sobriety=stats["recovery_and_sobriety"],
        trauma_and_vulnerability=stats["trauma_and_vulnerability"],
        barriers_to_stability=stats["barriers_to_stability"],
        education_and_income=stats["education_and_income"],
        exit_outcomes=stats["exit_outcomes"],
        scope_options=[
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        population_options=[
            {"value": "active", "label": "Active Residents"},
            {"value": "exited", "label": "Exited Residents"},
            {"value": "all", "label": "All Residents"},
        ],
        date_range_options=[
            {"value": "this_month", "label": "This Month"},
            {"value": "last_month", "label": "Last Month"},
            {"value": "this_quarter", "label": "This Quarter"},
            {"value": "this_year", "label": "This Year"},
            {"value": "last_year", "label": "Last Year"},
            {"value": "all_time", "label": "All Time"},
            {"value": "custom", "label": "Custom Range"},
        ],
    )


@reports.route("/staff/reports/studies/graduation-income-sobriety", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def graduation_income_sobriety_study():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))

    study = _build_graduation_income_study(scope=scope, start_date=start_date, end_date=end_date)

    return render_template(
        "reports/graduation_income_sobriety_study.html",
        title="Graduation Income And Sobriety Outcome Study",
        study=study,
        scope=scope,
        start_date=start_date or "",
        end_date=end_date or "",
        scope_options=[
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        fmt_currency=_fmt_currency,
    )
