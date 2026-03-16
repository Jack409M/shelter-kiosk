from __future__ import annotations

from flask import Blueprint, flash, g, redirect, render_template, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_fetchall, db_fetchone
from core.runtime import init_db

case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


def _case_manager_allowed() -> bool:
    return session.get("role") in {"admin", "shelter_director", "case_manager"}


def _normalize_shelter_name(value: str | None) -> str:
    return (value or "").strip().lower()


def _shelter_equals_sql(column_name: str) -> str:
    if g.get("db_kind") == "pg":
        return f"LOWER(COALESCE({column_name}, '')) = %s"
    return f"LOWER(COALESCE({column_name}, '')) = ?"


def _placeholder() -> str:
    return "%s" if g.get("db_kind") == "pg" else "?"


@case_management.get("")
@require_login
@require_shelter
def index():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()
    shelter = _normalize_shelter_name(session.get("shelter"))

    residents = db_fetchall(
        f"""
        SELECT id, first_name, last_name, resident_code, is_active
        FROM residents
        WHERE {_shelter_equals_sql("shelter")}
        ORDER BY last_name ASC, first_name ASC
        """,
        (shelter,),
    )

    return render_template(
        "case_management/index.html",
        residents=residents,
        shelter=shelter,
    )


@case_management.get("/intake-assessment")
@require_login
@require_shelter
def intake_assessment():
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    return render_template(
        "case_management/intake_assessment.html",
        current_shelter=_normalize_shelter_name(session.get("shelter")),
        shelters=[
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        prior_living_options=[
            {"value": "street", "label": "Street"},
            {"value": "shelter",
