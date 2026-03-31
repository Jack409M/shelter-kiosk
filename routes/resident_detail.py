from __future__ import annotations

from datetime import datetime

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from routes.case_management_parts.helpers import case_manager_allowed as _shared_case_manager_allowed
from routes.case_management_parts.helpers import normalize_shelter_name as _shared_normalize_shelter_name
from routes.case_management_parts.helpers import shelter_equals_sql as _shared_shelter_equals_sql
from routes.resident_detail_parts.actions import add_appointment_view
from routes.resident_detail_parts.actions import add_case_note_view
from routes.resident_detail_parts.actions import add_goal_view
from routes.resident_detail_parts.actions import complete_goal_view
from routes.resident_detail_parts.actions import create_enrollment_view
from routes.resident_detail_parts.read import load_enrollment_context_for_shelter
from routes.resident_detail_parts.read import load_resident_for_shelter
from routes.resident_detail_parts.read import row_value
from routes.resident_detail_parts.timeline import build_calendar_context
from routes.resident_detail_parts.timeline import coerce_calendar_view
from routes.resident_detail_parts.timeline import load_timeline
from routes.resident_detail_parts.timeline import normalize_timeline
from routes.resident_detail_parts.timeline import parse_anchor_date
from routes.resident_detail_parts.timeline import parse_dt

resident_detail = Blueprint(
    "resident_detail",
    __name__,
    url_prefix="/staff/resident",
)


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    from flask import g

    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _normalize_shelter_name(value: str | None) -> str:
    return _shared_normalize_shelter_name(value)


def _shelter_equals_sql(column_name: str) -> str:
    return _shared_shelter_equals_sql(column_name)


def _case_manager_allowed() -> bool:
    return _shared_case_manager_allowed()


def _resident_detail_view_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager", "ra", "staff"}


def _days_in_program(entry_date_value) -> str:
    entry_dt = parse_dt(entry_date_value)
    if not entry_dt:
        return "—"

    days = (datetime.utcnow().date() - entry_dt.date()).days
    if days < 0:
        days = 0
    return str(days)


def _days_sober_today(sobriety_date_value):
    sobriety_dt = parse_dt(sobriety_date_value)
    if not sobriety_dt:
        return None

    days = (datetime.utcnow().date() - sobriety_dt.date()).days
    if days < 0:
        days = 0
    return days


@resident_detail.route("/<int:resident_id>")
@require_login
@require_shelter
def resident_profile(resident_id: int):
    if not _resident_detail_view_allowed():
        flash("Resident detail access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = load_resident_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
    )

    if not resident:
        return render_template(
            "resident_detail/profile.html",
            resident=None,
            compliance=None,
            goals=[],
            notes=[],
            appointment=None,
            snapshot=None,
            days_sober_today=None,
        )

    days_sober_today = _days_sober_today(row_value(resident, "sobriety_date", 19))

    return render_template(
        "resident_detail/profile.html",
        resident=resident,
        compliance=None,
        goals=[],
        notes=[],
        appointment=None,
        snapshot=None,
        days_sober_today=days_sober_today,
    )


@resident_detail.route("/<int:resident_id>/timeline")
@require_login
@require_shelter
def resident_timeline(resident_id: int):
    if not _resident_detail_view_allowed():
        flash("Resident detail access required.", "error")
        return redirect(url_for("residents.staff_residents"))

    shelter = _normalize_shelter_name(session.get("shelter"))
    resident = load_resident_for_shelter(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
    )

    selected_view = coerce_calendar_view(request.args.get("view"))
    anchor_date = parse_anchor_date(request.args.get("anchor"))
    empty_calendar = build_calendar_context([], selected_view, anchor_date)

    if not resident:
        return render_template(
            "resident_detail/timeline.html",
            resident=None,
            timeline=[],
            snapshot=None,
            calendar=empty_calendar,
        )

    enrollment_id = row_value(resident, "enrollment_id", 5)

    timeline = []
    snapshot = None
    calendar = empty_calendar

    if enrollment_id:
        timeline = normalize_timeline(load_timeline(enrollment_id, _sql))
        snapshot = {
            "program_status": str(row_value(resident, "program_status", 7, "—") or "—").replace("_", " ").title(),
            "days_in_program": _days_in_program(row_value(resident, "entry_date", 8)),
        }
        calendar = build_calendar_context(timeline, selected_view, anchor_date)

    return render_template(
        "resident_detail/timeline.html",
        resident=resident,
        timeline=timeline,
        snapshot=snapshot,
        calendar=calendar,
    )


@resident_detail.post("/<int:resident_id>/enroll")
@require_login
@require_shelter
def create_enrollment(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))
    return create_enrollment_view(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
        _case_manager_allowed,
    )


@resident_detail.post("/<int:resident_id>/goals")
@require_login
@require_shelter
def add_goal(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))
    return add_goal_view(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
        _case_manager_allowed,
        load_enrollment_context_for_shelter,
    )


@resident_detail.post("/goal/<int:goal_id>/complete")
@require_login
@require_shelter
def complete_goal(goal_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))
    return complete_goal_view(
        goal_id,
        shelter,
        _sql,
        _shelter_equals_sql,
        _case_manager_allowed,
        row_value,
    )


@resident_detail.post("/<int:resident_id>/case-note")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))
    return add_case_note_view(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
        _case_manager_allowed,
        load_enrollment_context_for_shelter,
    )


@resident_detail.post("/<int:resident_id>/appointments")
@require_login
@require_shelter
def add_appointment(resident_id: int):
    shelter = _normalize_shelter_name(session.get("shelter"))
    return add_appointment_view(
        resident_id,
        shelter,
        _sql,
        _shelter_equals_sql,
        _case_manager_allowed,
        load_enrollment_context_for_shelter,
    )
