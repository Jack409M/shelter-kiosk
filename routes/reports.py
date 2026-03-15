from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.auth import require_login, require_roles, require_shelter
from core.db import db_execute, db_fetchall
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

TOP_METRICS = {
    "women_served": {
        "label": "Women Served",
        "section": "program_snapshot",
        "value_key": "women_served_display",
    },
    "active_residents": {
        "label": "Currently Active",
        "section": "program_snapshot",
        "value_key": "active_residents_current_display",
    },
    "women_admitted": {
        "label": "Women Admitted",
        "section": "program_snapshot",
        "value_key": "women_admitted_display",
    },
    "women_exited": {
        "label": "Women Exited",
        "section": "program_snapshot",
        "value_key": "women_exited_display",
    },
    "graduates": {
        "label": "Graduates",
        "section": "program_snapshot",
        "value_key": "graduates_display",
    },
    "avg_stay": {
        "label": "Average Length of Stay",
        "section": "program_snapshot",
        "value_key": "average_length_of_stay_days",
        "suffix": " days",
    },
    "veteran": {
        "label": "Veteran",
        "section": "demographics",
        "value_key": "veteran_yes_display",
    },
    "disability": {
        "label": "Disability",
        "section": "demographics",
        "value_key": "disability_yes_display",
    },
    "residents_with_children": {
        "label": "Residents With Children",
        "section": "family_composition",
        "value_key": "residents_with_children_display",
    },
    "children_in_shelter": {
        "label": "Children In Shelter",
        "section": "family_composition",
        "value_key": "children_in_shelter_display",
    },
    "children_out_of_shelter": {
        "label": "Children Out Of Shelter",
        "section": "family_composition",
        "value_key": "children_out_of_shelter_display",
    },
    "children_reunited": {
        "label": "Children Reunited",
        "section": "family_composition",
        "value_key": "children_reunited_display",
    },
    "healthy_babies_born": {
        "label": "Healthy Babies Born",
        "section": "family_composition",
        "value_key": "healthy_babies_born_display",
    },
    "avg_days_sober_entry": {
        "label": "Average Days Sober At Entry",
        "section": "recovery_and_sobriety",
        "value_key": "average_days_sober_at_entry",
    },
    "ace_score_average": {
        "label": "Average ACE Score",
        "section": "trauma_and_vulnerability",
        "value_key": "ace_score_average",
    },
    "sexual_survivor": {
        "label": "Sexual Survivor",
        "section": "trauma_and_vulnerability",
        "value_key": "sexual_survivor_display",
    },
    "dv_survivor": {
        "label": "Domestic Violence Survivor",
        "section": "trauma_and_vulnerability",
        "value_key": "dv_survivor_display",
    },
    "human_trafficking_survivor": {
        "label": "Human Trafficking Survivor",
        "section": "trauma_and_vulnerability",
        "value_key": "human_trafficking_survivor_display",
    },
    "entry_felony_conviction": {
        "label": "Entry Felony Conviction",
        "section": "barriers_to_stability",
        "value_key": "entry_felony_conviction_display",
    },
    "entry_parole_probation": {
        "label": "Entry Parole Or Probation",
        "section": "barriers_to_stability",
        "value_key": "entry_parole_probation_display",
    },
    "drug_court": {
        "label": "Drug Court",
        "section": "barriers_to_stability",
        "value_key": "drug_court_display",
    },
    "avg_income_entry": {
        "label": "Average Income At Entry",
        "section": "education_and_income",
        "value_key": "average_income_at_entry",
        "currency": True,
    },
    "avg_income_exit": {
        "label": "Average Income At Exit",
        "section": "education_and_income",
        "value_key": "average_income_at_exit",
        "currency": True,
    },
    "avg_income_improvement": {
        "label": "Average Income Improvement",
        "section": "education_and_income",
        "value_key": "average_income_improvement",
        "currency": True,
    },
    "exit_graduates": {
        "label": "Graduates",
        "section": "exit_outcomes",
        "value_key": "graduates_display",
    },
    "leave_ama": {
        "label": "Leave AMA",
        "section": "exit_outcomes",
        "value_key": "leave_ama_display",
    },
    "total_exit_records": {
        "label": "Total Exit Records",
        "section": "exit_outcomes",
        "value_key": "total_exit_records_display",
    },
}

_DEFAULT_TOP_METRIC_KEYS = [
    "women_served",
    "active_residents",
    "women_admitted",
    "women_exited",
    "graduates",
    "avg_stay",
]


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

        if metric_key in TOP_METRICS and metric_key not in metric_keys:
            metric_keys.append(metric_key)

    return metric_keys


def _get_effective_top_metric_keys(staff_user_id: int | None) -> list[str]:
    if not staff_user_id:
        return list(_DEFAULT_TOP_METRIC_KEYS)

    saved_metric_keys = _get_saved_favorite_metric_keys(staff_user_id)
    if saved_metric_keys:
        return saved_metric_keys[:_MAX_FAVORITES]

    return list(_DEFAULT_TOP_METRIC_KEYS)


def _format_top_stat_value(raw_value, metric: dict) -> str:
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
    prefix = metric.get("prefix", "")

    return f"{prefix}{text}{suffix}"


def _build_top_stats(stats: dict, metric_keys: list[str]) -> list[dict]:
    top_stats: list[dict] = []

    for metric_key in metric_keys:
        metric = TOP_METRICS.get(metric_key)
        if not metric:
            continue

        section_name = metric["section"]
        value_key = metric["value_key"]
        section_data = stats.get(section_name, {}) or {}
        raw_value = section_data.get(value_key, "-")
        value = _format_top_stat_value(raw_value, metric)

        top_stats.append(
            {
                "key": metric_key,
                "label": metric["label"],
                "value": value,
                "is_favorite": metric_key in metric_keys,
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

    if metric_key not in TOP_METRICS:
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

    staff_user_id = _current_staff_user_id()
    favorite_metric_keys = _get_effective_top_metric_keys(staff_user_id)
    top_stats = _build_top_stats(stats, favorite_metric_keys)

    return render_template(
        "reports/demographics.html",
        title="Demographics and Statistics",
        filters=stats["filters"],
        top_stats=top_stats,
        favorite_metric_keys=favorite_metric_keys,
        top_metric_definitions=TOP_METRICS,
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
