from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import g

from core.db import db_fetchall
from core.kiosk_activity_categories import load_kiosk_activity_categories_for_shelter


CHICAGO_TZ = ZoneInfo("America/Chicago")
PASS_REQUIRED_PRODUCTIVE_HOURS = 35.0
PASS_REQUIRED_WORK_HOURS = 29.0


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
    if value in {1, "1", "true", "True", "yes", "on"}:
        return True
    return False


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
        return datetime.fromisoformat(str(dt_iso)).replace(tzinfo=timezone.utc).astimezone(CHICAGO_TZ)
    except Exception:
        return None


def _local_to_utc_iso(local_dt: datetime) -> str:
    return (
        local_dt.astimezone(timezone.utc)
        .replace(tzinfo=None)
        .isoformat(timespec="seconds")
    )


def _start_of_current_week_local(now_local: datetime) -> datetime:
    return (now_local - timedelta(days=now_local.weekday())).replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0,
    )


def previous_full_week_window(now_local: datetime | None = None) -> dict[str, Any]:
    current_local = now_local or datetime.now(CHICAGO_TZ)
    current_week_start = _start_of_current_week_local(current_local)
    prior_week_start = current_week_start - timedelta(days=7)
    prior_week_end = current_week_start

    return {
        "start_local": prior_week_start,
        "end_local": prior_week_end,
        "start_utc_iso": _local_to_utc_iso(prior_week_start),
        "end_utc_iso": _local_to_utc_iso(prior_week_end),
        "label": f"Previous week Monday through Sunday ({prior_week_start.strftime('%b %d, %Y')} to {(prior_week_end - timedelta(seconds=1)).strftime('%b %d, %Y')})",
    }


def calculate_prior_week_attendance_hours(resident_id: int, shelter: str) -> dict[str, Any]:
    window = previous_full_week_window()
    category_map = _category_map_for_shelter(shelter)

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

    rows = db_fetchall(
        sql,
        (
            resident_id,
            shelter,
            "check_out",
            window["start_utc_iso"],
            window["end_utc_iso"],
        ),
    )

    by_category: dict[str, dict[str, Any]] = {}
    uncategorized_hours = 0.0

    for row in rows or []:
        destination = (row.get("destination") if isinstance(row, dict) else row[1]) or ""
        destination = destination.strip()

        start_iso = (row.get("obligation_start_time") if isinstance(row, dict) else row[2]) or ""
        planned_end_iso = (row.get("obligation_end_time") if isinstance(row, dict) else row[3]) or ""
        actual_end_iso = (row.get("actual_obligation_end_time") if isinstance(row, dict) else row[4]) or ""

        start_local = _utc_iso_to_local(start_iso)
        end_local = _utc_iso_to_local(actual_end_iso) or _utc_iso_to_local(planned_end_iso)

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

    productive_short = round(max(0.0, PASS_REQUIRED_PRODUCTIVE_HOURS - productive_total), 2)
    work_short = round(max(0.0, PASS_REQUIRED_WORK_HOURS - work_total), 2)
    meets_productive = productive_short == 0
    meets_work = work_short == 0
    passes_requirement = meets_productive and meets_work

    return {
        "week_label": window["label"],
        "week_start_local": window["start_local"],
        "week_end_local": window["end_local"],
        "productive_hours": productive_total,
        "work_hours": work_total,
        "productive_required_hours": PASS_REQUIRED_PRODUCTIVE_HOURS,
        "work_required_hours": PASS_REQUIRED_WORK_HOURS,
        "productive_short_hours": productive_short,
        "work_short_hours": work_short,
        "meets_productive_requirement": meets_productive,
        "meets_work_requirement": meets_work,
        "passes_requirement": passes_requirement,
        "status_label": "Pass" if passes_requirement else "Fail",
        "status_class": "pass" if passes_requirement else "fail",
        "breakdown": breakdown,
        "uncategorized_hours": round(uncategorized_hours, 2),
        "has_data": bool(breakdown or uncategorized_hours),
    }


def build_attendance_hours_snapshot(resident_id: int, shelter: str) -> dict[str, Any]:
    summary = calculate_prior_week_attendance_hours(resident_id, shelter)

    productive_ratio = 0.0
    work_ratio = 0.0

    if summary["productive_required_hours"] > 0:
        productive_ratio = min(summary["productive_hours"] / summary["productive_required_hours"], 1.0)

    if summary["work_required_hours"] > 0:
        work_ratio = min(summary["work_hours"] / summary["work_required_hours"], 1.0)

    percent_grade = round(((productive_ratio * 0.5) + (work_ratio * 0.5)) * 100.0, 1)

    if summary["passes_requirement"]:
        band_key = "green"
        band_label = "Pass"
        card_style = "background:#eef8f0; border:1px solid #9bc8a6;"
        value_style = "color:#1f6b33; font-weight:700;"
        pill_style = "display:inline-block; padding:4px 10px; border-radius:999px; background:#dcefe1; border:1px solid #9bc8a6; color:#1f6b33; font-weight:700;"
    elif percent_grade >= 80:
        band_key = "yellow"
        band_label = "Close"
        card_style = "background:#fff8df; border:1px solid #e0cd7a;"
        value_style = "color:#7a6500; font-weight:700;"
        pill_style = "display:inline-block; padding:4px 10px; border-radius:999px; background:#fff1b8; border:1px solid #e0cd7a; color:#7a6500; font-weight:700;"
    elif percent_grade >= 60:
        band_key = "orange"
        band_label = "Needs Work"
        card_style = "background:#fff0e4; border:1px solid #e2b27d;"
        value_style = "color:#9a4f00; font-weight:700;"
        pill_style = "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd8b0; border:1px solid #e2b27d; color:#9a4f00; font-weight:700;"
    else:
        band_key = "red"
        band_label = "Fail"
        card_style = "background:#fff0f0; border:1px solid #e2a0a0;"
        value_style = "color:#9a1f1f; font-weight:700;"
        pill_style = "display:inline-block; padding:4px 10px; border-radius:999px; background:#ffd6d6; border:1px solid #e2a0a0; color:#9a1f1f; font-weight:700;"

    return {
        "week_label": summary["week_label"],
        "productive_hours": summary["productive_hours"],
        "work_hours": summary["work_hours"],
        "productive_required_hours": summary["productive_required_hours"],
        "work_required_hours": summary["work_required_hours"],
        "productive_short_hours": summary["productive_short_hours"],
        "work_short_hours": summary["work_short_hours"],
        "passes_requirement": summary["passes_requirement"],
        "status_label": summary["status_label"],
        "status_class": summary["status_class"],
        "percent_grade": percent_grade,
        "percent_grade_display": f"{percent_grade:.1f}",
        "band_key": band_key,
        "band_label": band_label,
        "card_style": card_style,
        "value_style": value_style,
        "pill_style": pill_style,
        "uncategorized_hours": summary["uncategorized_hours"],
        "breakdown": summary["breakdown"],
        "has_data": summary["has_data"],
    }
