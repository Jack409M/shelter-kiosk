from __future__ import annotations

from flask import Blueprint, render_template, request

from core.auth import require_login, require_roles, require_shelter
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

    return render_template(
        "reports/demographics.html",
        title="Demographics and Statistics",
        filters=stats["filters"],
        program_snapshot=stats["program_snapshot"],
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
            {"value": "abba", "label": "Abba"},
            {"value": "haven", "label": "Haven"},
            {"value": "gratitude", "label": "Gratitude"},
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
