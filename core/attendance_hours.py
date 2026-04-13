from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from flask import g

from core.db import db_fetchall
from core.kiosk_activity_categories import load_kiosk_activity_categories_for_shelter
from core.pass_rules import pass_required_hours

CHICAGO_TZ = ZoneInfo("America/Chicago")
ATTENDANCE_LOOKBACK_WEEKS = 39
ATTENDANCE_WEIGHTED_PASS_PERCENT = 95.0


@dataclass
class AttendanceHourCategory:
    label: str
    counts_as_work: bool
    counts_as_productive: bool
    weekly_cap_hours: float | None
    requires_approved_pass: bool


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return value in {1, "1", "true", "True", "yes", "on"}


def _category_map_for_shelter(shelter: str) -> dict[str, AttendanceHourCategory]:
    rows = load_kiosk_activity_categories_for_shelter((shelter or "").strip().lower())
    category_map: dict[str, AttendanceHourCategory] = {}

    for row in rows or []:
        label = (row.get("activity_label") or "").strip()
        if not label:
            continue
        if not _as_bool(row.get("active", True)):
            continue

        weekly_cap_raw = row.get("weekly_cap_hours")
        weekly_cap: float | None = None
        if weekly_cap_raw not in {None, ""}:
            try:
                weekly_cap = float(weekly_cap_raw)
            except Exception:
                weekly_cap = None

        category_map[label] = AttendanceHourCategory(
            label=label,
            counts_as_work=_as_bool(row.get("counts_as_work_hours")),
            counts_as_productive=_as_bool(row.get("counts_as_productive_hours")),
            weekly_cap_hours=weekly_cap,
            requires_approved_pass=_as_bool(row.get("requires_approved_pass")),
        )

    return category_map


def _utc_iso_to_local(dt_iso: str | None) -> datetime | None:
    if not dt_iso:
        return None

    try:
        dt = datetime.fromisoformat(str(dt_iso))
    except Exception:
        return None

    try:
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.astimezone(CHICAGO_TZ)
    except Exception:
        return None


def _local_to_utc_iso(local_dt: datetime) -> str:
    return local_dt.astimezone(UTC).replace(tzinfo=None).isoformat(timespec="seconds")


def _start_of_week_local(any_local_dt: datetime) -> datetime:
    return (any_local_dt - timedelta(days=any_local_dt.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def _parse_entry_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw).date()
    except Exception:
        try:
            return datetime.strptime(raw[:10], "%Y-%m-%d").date()
        except Exception:
            return None


def _completed_week_windows(
    lookback_weeks: int = ATTENDANCE_LOOKBACK_WEEKS,
) -> list[dict[str, Any]]:
    now_local = datetime.now(CHICAGO_TZ)
    current_week_start = _start_of_week_local(now_local)

    weeks: list[dict[str, Any]] = []

    for offset in range(1, lookback_weeks + 1):
        week_start = current_week_start - timedelta(days=7 * offset)
        week_end = week_start + timedelta(days=7)
        week_end_display = week_end - timedelta(seconds=1)

        weeks.append(
            {
                "week_start_local": week_start,
                "week_end_local_exclusive": week_end,
                "week_label": f"{week_start.strftime('%b %d, %Y')} to {week_end_display.strftime('%b %d, %Y')}",
                "week_key": week_start.date().isoformat(),
            }
        )

    return weeks


def previous_full_week_window(now_local: datetime | None = None) -> dict[str, Any]:
    current_local = now_local or datetime.now(CHICAGO_TZ)
    current_week_start = _start_of_week_local(current_local)
    prior_week_start = current_week_start - timedelta(days=7)
    prior_week_end = current_week_start

    return {
        "start_local": prior_week_start,
        "end_local": prior_week_end,
        "start_utc_iso": _local_to_utc_iso(prior_week_start),
        "end_utc_iso": _local_to_utc_iso(prior_week_end),
        "label": f"Previous week Monday through Sunday ({prior_week_start.strftime('%b %d, %Y')} to {(prior_week_end - timedelta(seconds=1)).strftime('%b %d, %Y')})",
    }


def _summarize_rows(
    rows: list[dict[str, Any]],
    category_map: dict[str, AttendanceHourCategory],
    productive_required_hours: float,
    work_required_hours: float,
) -> dict[str, Any]:
    by_category: dict[str, dict[str, Any]] = {}
    uncategorized_hours = 0.0

    for row in rows or []:
        destination = (row.get("destination") or "").strip()

        start_local = row.get("obligation_start_local")
        planned_end_local = row.get("obligation_end_local")
        actual_end_local = row.get("actual_obligation_end_local")
        end_local = actual_end_local or planned_end_local

        if not start_local or not end_local:
            continue
        if end_local <= start_local:
            continue

        duration_hours = round((end_local - start_local).total_seconds() / 3600.0, 4)
        if duration_hours <= 0:
            continue

        category = category_map.get(destination)
        if not category:
            uncategorized_hours += duration_hours
            continue

        bucket = by_category.setdefault(
            destination,
            {
                "label": destination,
                "raw_hours": 0.0,
                "credited_hours": 0.0,
                "counts_as_work": category.counts_as_work,
                "counts_as_productive": category.counts_as_productive,
                "weekly_cap_hours": category.weekly_cap_hours,
                "requires_approved_pass": category.requires_approved_pass,
            },
        )
        bucket["raw_hours"] += duration_hours

    productive_total = 0.0
    work_total = 0.0
    breakdown: list[dict[str, Any]] = []

    for _label, bucket in by_category.items():
        raw_hours = round(bucket["raw_hours"], 2)
        cap_hours = bucket["weekly_cap_hours"]
        credited_hours = raw_hours

        if cap_hours is not None:
            credited_hours = min(raw_hours, float(cap_hours))

        credited_hours = round(credited_hours, 2)
        capped_hours_lost = round(max(0.0, raw_hours - credited_hours), 2)

        bucket["raw_hours"] = raw_hours
        bucket["credited_hours"] = credited_hours
        bucket["capped_hours_lost"] = capped_hours_lost

        if bucket["counts_as_productive"]:
            productive_total += credited_hours
        if bucket["counts_as_work"]:
            work_total += credited_hours

        breakdown.append(bucket)

    breakdown.sort(key=lambda item: item["label"].lower())

    productive_total = round(productive_total, 2)
    work_total = round(work_total, 2)

    productive_short = round(max(0.0, float(productive_required_hours) - productive_total), 2)
    work_short = round(max(0.0, float(work_required_hours) - work_total), 2)
    meets_productive = productive_short == 0
    meets_work = work_short == 0
    passes_requirement = meets_productive and meets_work

    productive_ratio = 0.0
    work_ratio = 0.0

    if productive_required_hours > 0:
        productive_ratio = min(productive_total / float(productive_required_hours), 1.0)
    if work_required_hours > 0:
        work_ratio = min(work_total / float(work_required_hours), 1.0)

    percent_grade = round(((productive_ratio * 0.5) + (work_ratio * 0.5)) * 100.0, 1)

    return {
        "productive_hours": productive_total,
        "work_hours": work_total,
        "productive_required_hours": round(float(productive_required_hours), 2),
        "work_required_hours": round(float(work_required_hours), 2),
        "productive_short_hours": productive_short,
        "work_short_hours": work_short,
        "meets_productive_requirement": meets_productive,
        "meets_work_requirement": meets_work,
        "passes_requirement": passes_requirement,
        "status_label": "Pass" if passes_requirement else "Fail",
        "status_class": "pass" if passes_requirement else "fail",
        "percent_grade": percent_grade,
        "percent_grade_display": f"{percent_grade:.1f}%",
        "breakdown": breakdown,
        "uncategorized_hours": round(uncategorized_hours, 2),
        "has_data": bool(breakdown or uncategorized_hours),
    }


def _fetch_attendance_rows_for_window(
    resident_id: int,
    shelter: str,
    start_utc_iso: str,
    end_utc_iso: str,
) -> list[dict[str, Any]]:
    sql = (
        """
        SELECT
            id,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = %s
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
          AND event_type = %s
          AND obligation_start_time IS NOT NULL
          AND obligation_start_time >= %s
          AND obligation_start_time < %s
        ORDER BY obligation_start_time ASC, id ASC
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            id,
            destination,
            obligation_start_time,
            obligation_end_time,
            actual_obligation_end_time
        FROM attendance_events
        WHERE resident_id = ?
          AND LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
          AND event_type = ?
          AND obligation_start_time IS NOT NULL
          AND obligation_start_time >= ?
          AND obligation_start_time < ?
        ORDER BY obligation_start_time ASC, id ASC
        """
    )

    raw_rows = db_fetchall(
        sql,
        (
            resident_id,
            shelter,
            "check_out",
            start_utc_iso,
            end_utc_iso,
        ),
    )

    rows: list[dict[str, Any]] = []
    for row in raw_rows or []:
        if isinstance(row, dict):
            normalized = dict(row)
        else:
            normalized = {
                "id": row[0],
                "destination": row[1],
                "obligation_start_time": row[2],
                "obligation_end_time": row[3],
                "actual_obligation_end_time": row[4],
            }

        normalized["obligation_start_local"] = _utc_iso_to_local(
            normalized.get("obligation_start_time")
        )
        normalized["obligation_end_local"] = _utc_iso_to_local(
            normalized.get("obligation_end_time")
        )
        normalized["actual_obligation_end_local"] = _utc_iso_to_local(
            normalized.get("actual_obligation_end_time")
        )
        rows.append(normalized)

    return rows


def calculate_prior_week_attendance_hours(resident_id: int, shelter: str) -> dict[str, Any]:
    window = previous_full_week_window()
    category_map = _category_map_for_shelter(shelter)
    required_hours = pass_required_hours(shelter)

    rows = _fetch_attendance_rows_for_window(
        resident_id=resident_id,
        shelter=shelter,
        start_utc_iso=window["start_utc_iso"],
        end_utc_iso=window["end_utc_iso"],
    )

    summary = _summarize_rows(
        rows,
        category_map,
        productive_required_hours=float(required_hours.get("productive_required_hours", 35)),
        work_required_hours=float(required_hours.get("work_required_hours", 29)),
    )
    summary["week_label"] = window["label"]
    summary["week_start_local"] = window["start_local"]
    summary["week_end_local"] = window["end_local"]
    return summary


def build_attendance_hours_snapshot(
    resident_id: int,
    shelter: str,
    enrollment_entry_date: str | None = None,
    lookback_weeks: int = ATTENDANCE_LOOKBACK_WEEKS,
) -> dict[str, Any]:
    completed_weeks = _completed_week_windows(lookback_weeks=lookback_weeks)
    if not completed_weeks:
        return {
            "average_percent": 0.0,
            "average_percent_display": "0.0%",
            "weighted_passes": False,
            "weighted_pass_threshold": ATTENDANCE_WEIGHTED_PASS_PERCENT,
            "band_label": "Fail",
            "card_style": "background:#fff0f0; border:1px solid #e2a0a0;",
            "value_style": "color:#9a1f1f; font-weight:700;",
            "pill_style": "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd6d6; border:1px solid #e2a0a0; color:#9a1f1f; font-weight:700;",
            "eligible_weeks_count": 0,
            "excluded_pre_entry_weeks_count": 0,
            "current_week_status_label": "—",
            "weekly_rows": [],
            "average_label": "No completed attendance weeks available.",
        }

    oldest_week = completed_weeks[-1]
    newest_week = completed_weeks[0]

    overall_start_utc = _local_to_utc_iso(oldest_week["week_start_local"])
    overall_end_utc = _local_to_utc_iso(newest_week["week_end_local_exclusive"])

    category_map = _category_map_for_shelter(shelter)
    required_hours = pass_required_hours(shelter)
    productive_required_hours = float(required_hours.get("productive_required_hours", 35))
    work_required_hours = float(required_hours.get("work_required_hours", 29))

    all_rows = _fetch_attendance_rows_for_window(
        resident_id=resident_id,
        shelter=shelter,
        start_utc_iso=overall_start_utc,
        end_utc_iso=overall_end_utc,
    )

    rows_by_week: dict[str, list[dict[str, Any]]] = {}
    for row in all_rows:
        start_local = row.get("obligation_start_local")
        if not start_local:
            continue
        week_key = _start_of_week_local(start_local).date().isoformat()
        rows_by_week.setdefault(week_key, []).append(row)

    entry_date = _parse_entry_date(enrollment_entry_date)

    weekly_rows: list[dict[str, Any]] = []
    eligible_percent_values: list[float] = []
    excluded_pre_entry_weeks_count = 0

    for week in completed_weeks:
        week_key = week["week_key"]
        week_rows = rows_by_week.get(week_key, [])
        week_summary = _summarize_rows(
            week_rows,
            category_map,
            productive_required_hours=productive_required_hours,
            work_required_hours=work_required_hours,
        )

        included_in_average = True
        if entry_date and week["week_start_local"].date() < entry_date:
            included_in_average = False
            excluded_pre_entry_weeks_count += 1

        if included_in_average:
            eligible_percent_values.append(week_summary["percent_grade"])

        short_text = ""
        if not week_summary["passes_requirement"]:
            short_text = (
                f"Short by {week_summary['productive_short_hours']} productive "
                f"and {week_summary['work_short_hours']} work hours."
            )

        weekly_rows.append(
            {
                "week_label": week["week_label"],
                "week_key": week_key,
                "included_in_average": included_in_average,
                "productive_hours": week_summary["productive_hours"],
                "work_hours": week_summary["work_hours"],
                "productive_required_hours": week_summary["productive_required_hours"],
                "work_required_hours": week_summary["work_required_hours"],
                "productive_short_hours": week_summary["productive_short_hours"],
                "work_short_hours": week_summary["work_short_hours"],
                "passes_requirement": week_summary["passes_requirement"],
                "status_label": week_summary["status_label"],
                "status_class": week_summary["status_class"],
                "percent_grade": week_summary["percent_grade"],
                "percent_grade_display": week_summary["percent_grade_display"],
                "short_text": short_text,
            }
        )

    average_percent = (
        round(
            sum(eligible_percent_values) / len(eligible_percent_values),
            1,
        )
        if eligible_percent_values
        else 0.0
    )

    weighted_passes = average_percent >= ATTENDANCE_WEIGHTED_PASS_PERCENT

    if weighted_passes:
        band_label = "Pass"
        card_style = "background:#eef8f0; border:1px solid #9bc8a6;"
        value_style = "color:#1f6b33; font-weight:700;"
        pill_style = "display:inline-block; padding:4px 10px; border-radius:999px; background:#dcefe1; border:1px solid #9bc8a6; color:#1f6b33; font-weight:700;"
    else:
        band_label = "Fail"
        card_style = "background:#fff0f0; border:1px solid #e2a0a0;"
        value_style = "color:#9a1f1f; font-weight:700;"
        pill_style = "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd6d6; border:1px solid #e2a0a0; color:#9a1f1f; font-weight:700;"

    latest_included_week = next((row for row in weekly_rows if row["included_in_average"]), None)

    return {
        "average_percent": average_percent,
        "average_percent_display": f"{average_percent:.1f}%",
        "weighted_passes": weighted_passes,
        "weighted_pass_threshold": ATTENDANCE_WEIGHTED_PASS_PERCENT,
        "band_label": band_label,
        "card_style": card_style,
        "value_style": value_style,
        "pill_style": pill_style,
        "eligible_weeks_count": len(eligible_percent_values),
        "excluded_pre_entry_weeks_count": excluded_pre_entry_weeks_count,
        "current_week_status_label": latest_included_week["status_label"]
        if latest_included_week
        else "—",
        "current_week_percent_display": latest_included_week["percent_grade_display"]
        if latest_included_week
        else "—",
        "current_week_label": latest_included_week["week_label"] if latest_included_week else "",
        "weekly_rows": weekly_rows,
        "average_label": (
            "9 month weighted average using completed program weeks only. "
            "Weeks before entry are excluded."
        ),
    }
