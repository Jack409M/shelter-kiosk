from __future__ import annotations

from statistics import median

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall
from core.runtime import init_db
from core.stats.common import days_between, display_shelter_label, normalize_shelter_value

reports_length_of_stay = Blueprint("reports_length_of_stay", __name__)

_ALLOWED_SCOPES = {"total_program", "abba", "haven", "gratitude"}

_BUCKETS = [
    ("0 to 30 days", 0, 30),
    ("31 to 60 days", 31, 60),
    ("61 to 90 days", 61, 90),
    ("91 to 180 days", 91, 180),
    ("181 days and above", 181, None),
]


def _clean_scope(value: str | None) -> str:
    cleaned = (value or "total_program").strip().lower()
    if cleaned in _ALLOWED_SCOPES:
        return cleaned
    return "total_program"


def _clean_iso_date(value: str | None) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    parts = text.split("-")
    if len(parts) != 3:
        return ""
    year, month, day = parts
    if not (year.isdigit() and month.isdigit() and day.isdigit()):
        return ""
    if len(year) != 4 or len(month) != 2 or len(day) != 2:
        return ""
    return text


def _bucket_label(days_value: int) -> str:
    for label, minimum, maximum in _BUCKETS:
        if maximum is None and days_value >= minimum:
            return label
        if minimum <= days_value <= int(maximum):
            return label
    return "Unknown"


def _build_length_of_stay_report(scope: str, start_date: str, end_date: str) -> dict:
    normalized_scope = _clean_scope(scope)

    params: list[str] = []
    filters: list[str] = ["pe.exit_date IS NOT NULL", "pe.exit_date <> ''"]

    if normalized_scope != "total_program":
        filters.append("LOWER(TRIM(COALESCE(pe.shelter, ''))) IN (?, ?)")
        params.extend([normalized_scope, f"{normalized_scope} house"])

    if start_date:
        filters.append("pe.exit_date >= ?")
        params.append(start_date)

    if end_date:
        filters.append("pe.exit_date <= ?")
        params.append(end_date)

    where_sql = "WHERE " + " AND ".join(filters)

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
            r.resident_code,
            r.resident_identifier
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
        ORDER BY pe.exit_date DESC,
                 LOWER(TRIM(COALESCE(r.last_name, ''))),
                 LOWER(TRIM(COALESCE(r.first_name, '')))
        """,
        tuple(params),
    ) or []

    detail_rows: list[dict] = []
    shelter_rollup: dict[str, dict] = {}
    bucket_counts: dict[str, int] = {label: 0 for label, _min, _max in _BUCKETS}
    stay_values: list[int] = []

    for raw_row in rows:
        row = dict(raw_row)
        shelter_key = normalize_shelter_value(row.get("shelter"))
        shelter_label = display_shelter_label(shelter_key or row.get("shelter"))
        stay_days = days_between(row.get("entry_date"), row.get("exit_date"))
        if stay_days is None or stay_days < 0:
            continue

        stay_values.append(stay_days)
        bucket = _bucket_label(stay_days)
        bucket_counts[bucket] = bucket_counts.get(bucket, 0) + 1

        shelter_bucket = shelter_rollup.setdefault(
            shelter_key or shelter_label.lower(),
            {
                "shelter_label": shelter_label,
                "resident_count": 0,
                "stay_values": [],
            },
        )
        shelter_bucket["resident_count"] += 1
        shelter_bucket["stay_values"].append(stay_days)

        detail_rows.append(
            {
                "resident_name": " ".join(
                    part for part in [row.get("first_name"), row.get("last_name")] if part
                ).strip() or "Unknown Resident",
                "resident_display_id": row.get("resident_code") or row.get("resident_identifier") or str(row.get("resident_id") or ""),
                "shelter_label": shelter_label,
                "entry_date": row.get("entry_date") or "",
                "exit_date": row.get("exit_date") or "",
                "stay_days": stay_days,
                "bucket_label": bucket,
            }
        )

    total_exits = len(detail_rows)
    average_stay = round(sum(stay_values) / len(stay_values), 1) if stay_values else 0.0
    median_stay = round(float(median(stay_values)), 1) if stay_values else 0.0
    longest_stay = max(stay_values) if stay_values else 0
    shortest_stay = min(stay_values) if stay_values else 0

    bucket_rows = [
        {
            "label": label,
            "count": bucket_counts.get(label, 0),
            "percent": f"{((bucket_counts.get(label, 0) / total_exits) * 100):.1f}%" if total_exits else "0.0%",
        }
        for label, _minimum, _maximum in _BUCKETS
    ]

    shelter_rows = []
    for shelter_data in shelter_rollup.values():
        shelter_values = list(shelter_data["stay_values"])
        shelter_rows.append(
            {
                "shelter_label": shelter_data["shelter_label"],
                "resident_count": shelter_data["resident_count"],
                "average_stay": round(sum(shelter_values) / len(shelter_values), 1) if shelter_values else 0.0,
                "median_stay": round(float(median(shelter_values)), 1) if shelter_values else 0.0,
                "longest_stay": max(shelter_values) if shelter_values else 0,
            }
        )

    shelter_rows.sort(key=lambda item: item["shelter_label"].lower())

    selected_scope_label = "Total Program" if normalized_scope == "total_program" else display_shelter_label(normalized_scope)

    return {
        "scope": normalized_scope,
        "scope_label": selected_scope_label,
        "start_date": start_date,
        "end_date": end_date,
        "total_exits": total_exits,
        "average_stay": average_stay,
        "median_stay": median_stay,
        "longest_stay": longest_stay,
        "shortest_stay": shortest_stay,
        "bucket_rows": bucket_rows,
        "shelter_rows": shelter_rows,
        "detail_rows": detail_rows,
        "scope_options": [
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
    }


@reports_length_of_stay.route("/staff/reports/length-of-stay", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def length_of_stay_report():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))
    report = _build_length_of_stay_report(scope=scope, start_date=start_date, end_date=end_date)

    return render_template(
        "reports/length_of_stay.html",
        title="Length Of Stay Report",
        report=report,
    )
