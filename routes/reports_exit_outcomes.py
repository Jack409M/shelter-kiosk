from __future__ import annotations

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall
from core.runtime import init_db
from core.stats.common import days_between, display_shelter_label, normalize_shelter_value

reports_exit_outcomes = Blueprint("reports_exit_outcomes", __name__)

_ALLOWED_SCOPES = {"total_program", "abba", "haven", "gratitude"}


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


def _fmt_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def _build_exit_outcomes_report(scope: str, start_date: str, end_date: str) -> dict:
    normalized_scope = _clean_scope(scope)

    params: list[str] = []
    filters: list[str] = []

    if normalized_scope != "total_program":
        filters.append("LOWER(TRIM(COALESCE(pe.shelter, ''))) IN (?, ?)")
        params.extend([normalized_scope, f"{normalized_scope} house"])

    if start_date:
        filters.append(
            "COALESCE(NULLIF(TRIM(ea.date_exit_dwc), ''), NULLIF(TRIM(pe.exit_date), ''), NULLIF(TRIM(ea.date_graduated), '')) >= ?"
        )
        params.append(start_date)

    if end_date:
        filters.append(
            "COALESCE(NULLIF(TRIM(ea.date_exit_dwc), ''), NULLIF(TRIM(pe.exit_date), ''), NULLIF(TRIM(ea.date_graduated), '')) <= ?"
        )
        params.append(end_date)

    where_sql = ""
    if filters:
        where_sql = "WHERE " + " AND ".join(filters)

    rows = (
        db_fetchall(
            f"""
        SELECT
            pe.id AS enrollment_id,
            pe.resident_id,
            pe.shelter,
            pe.entry_date,
            pe.exit_date AS enrollment_exit_date,
            r.first_name,
            r.last_name,
            r.resident_code,
            r.resident_identifier,
            ea.date_graduated,
            ea.date_exit_dwc,
            ea.exit_category,
            ea.exit_reason,
            ea.graduate_dwc,
            ea.leave_ama,
            COALESCE(
                NULLIF(TRIM(ea.date_exit_dwc), ''),
                NULLIF(TRIM(pe.exit_date), ''),
                NULLIF(TRIM(ea.date_graduated), '')
            ) AS effective_exit_date
        FROM exit_assessments ea
        JOIN program_enrollments pe
          ON pe.id = ea.enrollment_id
        JOIN residents r
          ON r.id = pe.resident_id
        {where_sql}
        ORDER BY
          COALESCE(
            NULLIF(TRIM(ea.date_exit_dwc), ''),
            NULLIF(TRIM(pe.exit_date), ''),
            NULLIF(TRIM(ea.date_graduated), '')
          ) DESC,
          LOWER(TRIM(COALESCE(r.last_name, ''))),
          LOWER(TRIM(COALESCE(r.first_name, '')))
        """,
            tuple(params),
        )
        or []
    )

    category_counts: dict[str, int] = {}
    reason_counts: dict[str, int] = {}
    shelter_counts: dict[str, dict[str, int | str]] = {}
    detail_rows: list[dict] = []

    graduate_count = 0
    leave_ama_count = 0
    days_values: list[int] = []

    for raw_row in rows:
        row = dict(raw_row)
        shelter_key = normalize_shelter_value(row.get("shelter"))
        shelter_label = display_shelter_label(shelter_key or row.get("shelter"))
        effective_exit_date = row.get("effective_exit_date") or ""
        category_label = (row.get("exit_category") or "").strip() or "Unspecified"
        reason_label = (row.get("exit_reason") or "").strip() or "Unspecified"
        graduated = bool(int(row.get("graduate_dwc") or 0))
        leave_ama = bool(int(row.get("leave_ama") or 0))

        days_in_program = days_between(row.get("entry_date"), effective_exit_date)
        if days_in_program is not None and days_in_program >= 0:
            days_values.append(days_in_program)

        category_counts[category_label] = category_counts.get(category_label, 0) + 1
        reason_counts[reason_label] = reason_counts.get(reason_label, 0) + 1

        shelter_bucket = shelter_counts.setdefault(
            shelter_key or shelter_label.lower(),
            {
                "shelter_label": shelter_label,
                "exit_count": 0,
                "graduate_count": 0,
                "leave_ama_count": 0,
            },
        )
        shelter_bucket["exit_count"] = int(shelter_bucket["exit_count"]) + 1
        if graduated:
            shelter_bucket["graduate_count"] = int(shelter_bucket["graduate_count"]) + 1
            graduate_count += 1
        if leave_ama:
            shelter_bucket["leave_ama_count"] = int(shelter_bucket["leave_ama_count"]) + 1
            leave_ama_count += 1

        detail_rows.append(
            {
                "resident_name": " ".join(
                    part for part in [row.get("first_name"), row.get("last_name")] if part
                ).strip()
                or "Unknown Resident",
                "resident_display_id": row.get("resident_code")
                or row.get("resident_identifier")
                or str(row.get("resident_id") or ""),
                "shelter_label": shelter_label,
                "entry_date": row.get("entry_date") or "",
                "effective_exit_date": effective_exit_date,
                "days_in_program": days_in_program if days_in_program is not None else "—",
                "exit_category": category_label,
                "exit_reason": reason_label,
                "graduated_label": "Yes" if graduated else "No",
                "leave_ama_label": "Yes" if leave_ama else "No",
            }
        )

    total_exits = len(detail_rows)
    average_days_at_exit = round(sum(days_values) / len(days_values), 1) if days_values else 0.0

    category_rows = [
        {
            "label": label,
            "count": count,
            "percent": _fmt_percent(count, total_exits),
        }
        for label, count in sorted(
            category_counts.items(), key=lambda item: (-item[1], item[0].lower())
        )
    ]
    reason_rows = [
        {
            "label": label,
            "count": count,
            "percent": _fmt_percent(count, total_exits),
        }
        for label, count in sorted(
            reason_counts.items(), key=lambda item: (-item[1], item[0].lower())
        )
    ]
    shelter_rows = sorted(
        [
            {
                **value,
                "graduate_rate": _fmt_percent(
                    int(value["graduate_count"]), int(value["exit_count"])
                ),
            }
            for value in shelter_counts.values()
        ],
        key=lambda item: item["shelter_label"].lower(),
    )

    selected_scope_label = (
        "Total Program"
        if normalized_scope == "total_program"
        else display_shelter_label(normalized_scope)
    )

    return {
        "scope": normalized_scope,
        "scope_label": selected_scope_label,
        "start_date": start_date,
        "end_date": end_date,
        "total_exits": total_exits,
        "graduate_count": graduate_count,
        "leave_ama_count": leave_ama_count,
        "average_days_at_exit": average_days_at_exit,
        "successful_completion_count": category_counts.get("Successful Completion", 0),
        "positive_exit_count": category_counts.get("Positive Exit", 0),
        "negative_exit_count": category_counts.get("Negative Exit", 0),
        "administrative_exit_count": category_counts.get("Administrative Exit", 0),
        "category_rows": category_rows,
        "reason_rows": reason_rows,
        "shelter_rows": shelter_rows,
        "detail_rows": detail_rows,
        "scope_options": [
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
    }


@reports_exit_outcomes.route("/staff/reports/exit-outcomes", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def exit_outcomes_report():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))
    report = _build_exit_outcomes_report(scope=scope, start_date=start_date, end_date=end_date)

    return render_template(
        "reports/exit_outcomes.html",
        title="Exit Outcomes Report",
        report=report,
    )
