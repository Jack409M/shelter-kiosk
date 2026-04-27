from __future__ import annotations

from statistics import median

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall
from core.runtime import init_db
from core.stats.common import display_shelter_label, normalize_shelter_value

reports_income_change = Blueprint("reports_income_change", __name__)

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


def _safe_float(value) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except Exception:
        return None


def _fmt_currency(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def _fmt_percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0.0%"
    return f"{(numerator / denominator) * 100:.1f}%"


def _average_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _median_or_none(values: list[float]) -> float | None:
    if not values:
        return None
    return round(float(median(values)), 2)


def _build_income_change_report(scope: str, start_date: str, end_date: str) -> dict:
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
            ia.income_at_entry,
            ea.income_at_exit,
            ea.graduation_income_snapshot,
            COALESCE(
                NULLIF(TRIM(ea.date_exit_dwc), ''),
                NULLIF(TRIM(pe.exit_date), ''),
                NULLIF(TRIM(ea.date_graduated), '')
            ) AS effective_exit_date,
            f6.followup_date AS six_month_date,
            f6.income_at_followup AS six_month_income,
            f12.followup_date AS one_year_date,
            f12.income_at_followup AS one_year_income
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        LEFT JOIN intake_assessments ia
          ON ia.enrollment_id = pe.id
        LEFT JOIN exit_assessments ea
          ON ea.enrollment_id = pe.id
        LEFT JOIN (
            SELECT f.enrollment_id, f.followup_date, f.income_at_followup
            FROM followups f
            JOIN (
                SELECT enrollment_id, MAX(followup_date) AS latest_date
                FROM followups
                WHERE followup_type = '6_month'
                GROUP BY enrollment_id
            ) latest
              ON latest.enrollment_id = f.enrollment_id
             AND latest.latest_date = f.followup_date
            WHERE f.followup_type = '6_month'
        ) f6
          ON f6.enrollment_id = pe.id
        LEFT JOIN (
            SELECT f.enrollment_id, f.followup_date, f.income_at_followup
            FROM followups f
            JOIN (
                SELECT enrollment_id, MAX(followup_date) AS latest_date
                FROM followups
                WHERE followup_type = '1_year'
                GROUP BY enrollment_id
            ) latest
              ON latest.enrollment_id = f.enrollment_id
             AND latest.latest_date = f.followup_date
            WHERE f.followup_type = '1_year'
        ) f12
          ON f12.enrollment_id = pe.id
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

    detail_rows: list[dict] = []
    shelter_rollup: dict[str, dict] = {}

    entry_values: list[float] = []
    exit_values: list[float] = []
    graduation_values: list[float] = []
    six_month_values: list[float] = []
    one_year_values: list[float] = []
    entry_to_exit_changes: list[float] = []

    improved_count = 0
    declined_count = 0
    unchanged_count = 0
    comparable_count = 0

    for raw_row in rows:
        row = dict(raw_row)
        shelter_key = normalize_shelter_value(row.get("shelter"))
        shelter_label = display_shelter_label(shelter_key or row.get("shelter"))

        entry_income = _safe_float(row.get("income_at_entry"))
        exit_income = _safe_float(row.get("income_at_exit"))
        graduation_income = _safe_float(row.get("graduation_income_snapshot"))
        six_month_income = _safe_float(row.get("six_month_income"))
        one_year_income = _safe_float(row.get("one_year_income"))

        if entry_income is not None:
            entry_values.append(entry_income)
        if exit_income is not None:
            exit_values.append(exit_income)
        if graduation_income is not None:
            graduation_values.append(graduation_income)
        if six_month_income is not None:
            six_month_values.append(six_month_income)
        if one_year_income is not None:
            one_year_values.append(one_year_income)

        change_entry_to_exit = None
        change_status = "No comparison"
        if entry_income is not None and exit_income is not None:
            comparable_count += 1
            change_entry_to_exit = round(exit_income - entry_income, 2)
            entry_to_exit_changes.append(change_entry_to_exit)
            if change_entry_to_exit > 0:
                improved_count += 1
                change_status = "Improved"
            elif change_entry_to_exit < 0:
                declined_count += 1
                change_status = "Declined"
            else:
                unchanged_count += 1
                change_status = "Unchanged"

        shelter_bucket = shelter_rollup.setdefault(
            shelter_key or shelter_label.lower(),
            {
                "shelter_label": shelter_label,
                "resident_count": 0,
                "entry_values": [],
                "exit_values": [],
                "change_values": [],
                "improved_count": 0,
                "comparable_count": 0,
            },
        )
        shelter_bucket["resident_count"] += 1
        if entry_income is not None:
            shelter_bucket["entry_values"].append(entry_income)
        if exit_income is not None:
            shelter_bucket["exit_values"].append(exit_income)
        if change_entry_to_exit is not None:
            shelter_bucket["change_values"].append(change_entry_to_exit)
            shelter_bucket["comparable_count"] += 1
            if change_entry_to_exit > 0:
                shelter_bucket["improved_count"] += 1

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
                "effective_exit_date": row.get("effective_exit_date") or "",
                "entry_income_display": _fmt_currency(entry_income),
                "exit_income_display": _fmt_currency(exit_income),
                "graduation_income_display": _fmt_currency(graduation_income),
                "six_month_date": row.get("six_month_date") or "",
                "six_month_income_display": _fmt_currency(six_month_income),
                "one_year_date": row.get("one_year_date") or "",
                "one_year_income_display": _fmt_currency(one_year_income),
                "change_entry_to_exit_display": _fmt_currency(change_entry_to_exit),
                "change_status": change_status,
            }
        )

    shelter_rows = []
    for bucket in shelter_rollup.values():
        shelter_rows.append(
            {
                "shelter_label": bucket["shelter_label"],
                "resident_count": bucket["resident_count"],
                "avg_entry_income": _fmt_currency(_average_or_none(bucket["entry_values"])),
                "avg_exit_income": _fmt_currency(_average_or_none(bucket["exit_values"])),
                "avg_change": _fmt_currency(_average_or_none(bucket["change_values"])),
                "improved_count": bucket["improved_count"],
                "improved_rate": _fmt_percent(bucket["improved_count"], bucket["comparable_count"]),
            }
        )

    shelter_rows.sort(key=lambda item: item["shelter_label"].lower())

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
        "total_rows": len(detail_rows),
        "comparable_count": comparable_count,
        "improved_count": improved_count,
        "declined_count": declined_count,
        "unchanged_count": unchanged_count,
        "improved_rate": _fmt_percent(improved_count, comparable_count),
        "avg_entry_income": _average_or_none(entry_values),
        "avg_exit_income": _average_or_none(exit_values),
        "avg_graduation_income": _average_or_none(graduation_values),
        "avg_six_month_income": _average_or_none(six_month_values),
        "avg_one_year_income": _average_or_none(one_year_values),
        "median_entry_income": _median_or_none(entry_values),
        "median_exit_income": _median_or_none(exit_values),
        "median_six_month_income": _median_or_none(six_month_values),
        "median_one_year_income": _median_or_none(one_year_values),
        "avg_change_entry_to_exit": _average_or_none(entry_to_exit_changes),
        "shelter_rows": shelter_rows,
        "detail_rows": detail_rows,
        "scope_options": [
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        "fmt_currency": _fmt_currency,
    }


@reports_income_change.route("/staff/reports/income-change", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def income_change_report():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    start_date = _clean_iso_date(request.args.get("start_date"))
    end_date = _clean_iso_date(request.args.get("end_date"))
    report = _build_income_change_report(scope=scope, start_date=start_date, end_date=end_date)

    return render_template(
        "reports/income_change.html",
        title="Income Change Report",
        report=report,
    )
