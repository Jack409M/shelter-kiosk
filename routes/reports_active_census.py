from __future__ import annotations

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
from core.db import db_fetchall
from core.runtime import init_db
from core.stats.common import days_between, display_shelter_label, iso_today, normalize_shelter_value
from core.stats.snapshot import get_capacity_snapshot

reports_active_census = Blueprint("reports_active_census", __name__)

_ALLOWED_SCOPES = {"total_program", "abba", "haven", "gratitude"}


def _clean_scope(value: str | None) -> str:
    cleaned = (value or "total_program").strip().lower()
    if cleaned in _ALLOWED_SCOPES:
        return cleaned
    return "total_program"


def _fmt_currency(value) -> str:
    if value in (None, ""):
        return "—"
    try:
        return f"${float(value):,.2f}"
    except Exception:
        return "—"


def _case_manager_label(row: dict) -> str:
    first_name = str(row.get("case_manager_first_name") or "").strip()
    last_name = str(row.get("case_manager_last_name") or "").strip()
    username = str(row.get("case_manager_username") or "").strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip()
    return full_name or username or "—"


def _rad_status(row: dict) -> str:
    if bool(int(row.get("rad_complete") or 0)):
        return "Complete"
    if row.get("rad_completed_date"):
        return "Complete"
    return "Incomplete"


def _build_active_census_report(scope: str) -> dict:
    normalized_scope = _clean_scope(scope)
    today = iso_today()

    capacity_snapshot = get_capacity_snapshot()
    shelter_rows = [dict(item) for item in capacity_snapshot.get("shelters", [])]
    if normalized_scope != "total_program":
        shelter_rows = [item for item in shelter_rows if item.get("key") == normalized_scope]

    total_capacity = sum(int(item.get("capacity") or 0) for item in shelter_rows)
    total_occupied = sum(int(item.get("occupied") or 0) for item in shelter_rows)
    total_open_spaces = max(total_capacity - total_occupied, 0)
    total_occupancy_rate = round((total_occupied / total_capacity) * 100, 1) if total_capacity else 0.0

    params: list[str] = [today, today]
    scope_sql = ""
    if normalized_scope != "total_program":
        scope_sql = " AND LOWER(TRIM(COALESCE(pe.shelter, ''))) IN (?, ?)"
        params.extend([normalized_scope, f"{normalized_scope} house"])

    rows = db_fetchall(
        f"""
        SELECT
            pe.id AS enrollment_id,
            pe.resident_id,
            pe.shelter,
            pe.entry_date,
            pe.program_status,
            pe.case_manager_id,
            pe.rad_complete,
            pe.rad_completed_date,
            r.first_name,
            r.last_name,
            r.resident_code,
            r.resident_identifier,
            r.program_level,
            r.phone,
            r.monthly_income,
            su.username AS case_manager_username,
            su.first_name AS case_manager_first_name,
            su.last_name AS case_manager_last_name
        FROM program_enrollments pe
        JOIN residents r
          ON r.id = pe.resident_id
        LEFT JOIN staff_users su
          ON su.id = pe.case_manager_id
        WHERE pe.entry_date <= ?
          AND (pe.exit_date IS NULL OR pe.exit_date = '' OR pe.exit_date >= ?)
          {scope_sql}
        ORDER BY
          LOWER(TRIM(COALESCE(pe.shelter, ''))),
          LOWER(TRIM(COALESCE(r.last_name, ''))),
          LOWER(TRIM(COALESCE(r.first_name, ''))),
          pe.id
        """,
        tuple(params),
    ) or []

    resident_rows: list[dict] = []
    days_in_program_values: list[int] = []

    for raw_row in rows:
        row = dict(raw_row)
        shelter_key = normalize_shelter_value(row.get("shelter"))
        days_in_program = days_between(row.get("entry_date"), today)
        if days_in_program is not None and days_in_program >= 0:
            days_in_program_values.append(days_in_program)

        resident_rows.append(
            {
                "resident_id": row.get("resident_id"),
                "resident_name": " ".join(
                    part for part in [row.get("first_name"), row.get("last_name")] if part
                ).strip() or "Unknown Resident",
                "resident_display_id": row.get("resident_code") or row.get("resident_identifier") or str(row.get("resident_id") or ""),
                "shelter_key": shelter_key,
                "shelter_label": display_shelter_label(shelter_key or row.get("shelter")),
                "entry_date": row.get("entry_date") or "",
                "days_in_program": days_in_program if days_in_program is not None else "—",
                "program_level": row.get("program_level") or "—",
                "monthly_income_display": _fmt_currency(row.get("monthly_income")),
                "phone": row.get("phone") or "—",
                "rad_status": _rad_status(row),
                "case_manager_label": _case_manager_label(row),
            }
        )

    average_days_in_program = round(sum(days_in_program_values) / len(days_in_program_values), 1) if days_in_program_values else 0.0
    longest_stay_days = max(days_in_program_values) if days_in_program_values else 0

    selected_scope_label = "Total Program" if normalized_scope == "total_program" else display_shelter_label(normalized_scope)

    return {
        "scope": normalized_scope,
        "scope_label": selected_scope_label,
        "as_of_date": today,
        "total_capacity": total_capacity,
        "total_occupied": total_occupied,
        "total_open_spaces": total_open_spaces,
        "total_occupancy_rate": total_occupancy_rate,
        "resident_count": len(resident_rows),
        "average_days_in_program": average_days_in_program,
        "longest_stay_days": longest_stay_days,
        "shelter_rows": shelter_rows,
        "resident_rows": resident_rows,
        "scope_options": [
            {"value": "total_program", "label": "Total Program"},
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
    }


@reports_active_census.route("/staff/reports/active-census", methods=["GET"])
@require_login
@require_shelter
@require_roles("admin", "shelter_director", "case_manager", "demographics_viewer")
def active_census_report():
    init_db()

    scope = _clean_scope(request.args.get("scope"))
    report = _build_active_census_report(scope)

    return render_template(
        "reports/active_census.html",
        title="Active Census Report",
        report=report,
    )
