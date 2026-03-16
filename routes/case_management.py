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
        SELECT
            id,
            first_name,
            last_name,
            resident_code,
            is_active
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
        shelters=[
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        prior_living_options=[
            {"value": "street", "label": "Street"},
            {"value": "shelter", "label": "Emergency Shelter"},
            {"value": "jail", "label": "Jail"},
            {"value": "hospital", "label": "Hospital"},
            {"value": "family", "label": "Family or Friends"},
            {"value": "treatment", "label": "Treatment Program"},
            {"value": "other", "label": "Other"},
        ],
        ethnicity_options=[
            {"value": "hispanic", "label": "Hispanic"},
            {"value": "not_hispanic", "label": "Not Hispanic"},
        ],
        race_options=[
            {"value": "white", "label": "White"},
            {"value": "black", "label": "Black"},
            {"value": "native", "label": "Native American"},
            {"value": "asian", "label": "Asian"},
            {"value": "pacific", "label": "Pacific Islander"},
            {"value": "other", "label": "Other"},
        ],
        gender_options=[
            {"value": "female", "label": "Female"},
            {"value": "male", "label": "Male"},
            {"value": "nonbinary", "label": "Nonbinary"},
            {"value": "other", "label": "Other"},
        ],
        yes_no_options=[
            {"value": "yes", "label": "Yes"},
            {"value": "no", "label": "No"},
        ],
        drug_options=[
            {"value": "alcohol", "label": "Alcohol"},
            {"value": "meth", "label": "Meth"},
            {"value": "opioids", "label": "Opioids"},
            {"value": "cocaine", "label": "Cocaine"},
            {"value": "multiple", "label": "Multiple"},
            {"value": "other", "label": "Other"},
        ],
        education_options=[
            {"value": "no_hs", "label": "No High School"},
            {"value": "hs", "label": "High School"},
            {"value": "ged", "label": "GED"},
            {"value": "college", "label": "Some College"},
            {"value": "associate", "label": "Associate"},
            {"value": "bachelor", "label": "Bachelor"},
        ],
    )


@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    if not _case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = _normalize_shelter_name(session.get("shelter"))
    placeholder = _placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {placeholder}
          AND {_shelter_equals_sql("shelter")}
        """,
        (resident_id, shelter),
    )

    if not resident:
        flash("Resident not found.", "error")
        return redirect(url_for("case_management.index"))

    enrollment = db_fetchone(
        f"""
        SELECT
            id,
            program_status,
            entry_date,
            exit_date
        FROM program_enrollments
        WHERE resident_id = {placeholder}
        ORDER BY id DESC
        LIMIT 1
        """,
        (resident_id,),
    )

    enrollment_id = None
    if enrollment:
        enrollment_id = enrollment["id"] if isinstance(enrollment, dict) else enrollment[0]

    goals = []
    appointments = []
    notes = []

    if enrollment_id:
        goals = db_fetchall(
            f"""
            SELECT
                goal_text,
                status,
                target_date,
                created_at
            FROM goals
            WHERE enrollment_id = {placeholder}
            ORDER BY created_at DESC
            """,
            (enrollment_id,),
        )

        appointments = db_fetchall(
            f"""
            SELECT
                appointment_date,
                appointment_type,
                notes
            FROM appointments
            WHERE enrollment_id = {placeholder}
            ORDER BY appointment_date DESC, id DESC
            """,
            (enrollment_id,),
        )

        notes = db_fetchall(
            f"""
            SELECT
                meeting_date,
                notes,
                progress_notes,
                action_items,
                created_at
            FROM case_manager_updates
            WHERE enrollment_id = {placeholder}
            ORDER BY meeting_date DESC, id DESC
            """,
            (enrollment_id,),
        )

    return render_template(
        "case_management/resident_case.html",
        resident=resident,
        enrollment=enrollment,
        enrollment_id=enrollment_id,
        goals=goals,
        appointments=appointments,
        notes=notes,
    )
