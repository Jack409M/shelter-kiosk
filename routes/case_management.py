from __future__ import annotations

# ============================================================================
# Case Management Routes
# ----------------------------------------------------------------------------
# This file is now the transition shell for case management.
#
# Current responsibilities still living here:
# 1. Intake form shell and submit route
# 2. Resident case page display
# 3. Temporary admin utilities during build and testing
#
# Extracted:
# - routes.case_management_parts.assessment
#   assessment form, assessment drafts, validation, and persistence
# - routes.case_management_parts.intake_drafts
#   intake draft save, load, and complete
# - routes.case_management_parts.intake_validation
#   intake validation and duplicate detection
# - routes.case_management_parts.intake_inserts
#   resident, enrollment, intake assessment, and family snapshot inserts
#
# Future extraction plan:
# - routes.case_management_parts.helpers
#   shared parsing, shelter, permission, and SQL helpers
# - routes.case_management_parts.intake
#   intake form flow shell
# - routes.case_management_parts.resident_case
#   resident summary page and related reads
# - routes.case_management_parts.exit
#   exit assessment flow
# - routes.case_management_parts.update
#   progress update flow
#
# Goal:
# keep shrinking this file until it becomes a thin blueprint shell like admin.py
# ============================================================================

from typing import Any

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute, db_fetchall, db_fetchone
from core.runtime import init_db
from routes.case_management_parts.assessment import assessment_form_view
from routes.case_management_parts.assessment import submit_assessment_view
from routes.case_management_parts.helpers import case_manager_allowed
from routes.case_management_parts.helpers import clean
from routes.case_management_parts.helpers import digits_only
from routes.case_management_parts.helpers import normalize_shelter_name
from routes.case_management_parts.helpers import parse_int
from routes.case_management_parts.helpers import parse_iso_date
from routes.case_management_parts.helpers import parse_money
from routes.case_management_parts.helpers import placeholder
from routes.case_management_parts.helpers import shelter_equals_sql
from routes.case_management_parts.helpers import yes_no_to_int
from routes.case_management_parts.intake_drafts import _complete_intake_draft
from routes.case_management_parts.intake_drafts import _load_intake_draft
from routes.case_management_parts.intake_drafts import _save_intake_draft
from routes.case_management_parts.intake_inserts import _insert_family_snapshot
from routes.case_management_parts.intake_inserts import _insert_intake_assessment
from routes.case_management_parts.intake_inserts import _insert_program_enrollment
from routes.case_management_parts.intake_inserts import _insert_resident
from routes.case_management_parts.intake_validation import _find_possible_duplicate
from routes.case_management_parts.intake_validation import _validate_intake_form


# ============================================================================
# Compatibility aliases
# ----------------------------------------------------------------------------
# Other route modules still import the old underscore helper names directly
# from routes.case_management. Keep these aliases in place during the refactor
# so those modules do not break while logic is moved into case_management_parts.
# ============================================================================

_case_manager_allowed = case_manager_allowed
_clean = clean
_digits_only = digits_only
_normalize_shelter_name = normalize_shelter_name
_parse_int = parse_int
_parse_iso_date = parse_iso_date
_parse_money = parse_money
_placeholder = placeholder
_shelter_equals_sql = shelter_equals_sql
_yes_no_to_int = yes_no_to_int


# ============================================================================
# Blueprint Registration
# ----------------------------------------------------------------------------
# All routes in this file live under /staff/case-management
#
# Future state:
# this file should mostly contain blueprint creation plus thin decorated wrappers
# that delegate into routes.case_management_parts.*
# ============================================================================

case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


# ============================================================================
# Intake Template Context
# ----------------------------------------------------------------------------
# Future extraction target:
# routes.case_management_parts.intake
# ============================================================================

def _intake_template_context(
    current_shelter: str,
    form_data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "current_shelter": current_shelter,
        "form_data": form_data or {},
        "shelters": [
            {"value": "abba", "label": "Abba House"},
            {"value": "haven", "label": "Haven House"},
            {"value": "gratitude", "label": "Gratitude House"},
        ],
        "prior_living_options": [
            {"value": "street", "label": "Street"},
            {"value": "shelter", "label": "Emergency Shelter"},
            {"value": "jail", "label": "Jail"},
            {"value": "hospital", "label": "Hospital"},
            {"value": "family", "label": "Family or Friends"},
            {"value": "treatment", "label": "Treatment Program"},
            {"value": "other", "label": "Other"},
        ],
        "ethnicity_options": [
            {"value": "hispanic", "label": "Hispanic"},
            {"value": "not_hispanic", "label": "Not Hispanic"},
        ],
        "race_options": [
            {"value": "white", "label": "White"},
            {"value": "black", "label": "Black"},
            {"value": "native", "label": "Native American"},
            {"value": "asian", "label": "Asian"},
            {"value": "pacific", "label": "Pacific Islander"},
            {"value": "other", "label": "Other"},
        ],
        "gender_options": [
            {"value": "female", "label": "Female"},
            {"value": "male", "label": "Male"},
            {"value": "nonbinary", "label": "Nonbinary"},
            {"value": "other", "label": "Other"},
        ],
        "yes_no_options": [
            {"value": "yes", "label": "Yes"},
            {"value": "no", "label": "No"},
        ],
        "drug_options": [
            {"value": "alcohol", "label": "Alcohol"},
            {"value": "meth", "label": "Meth"},
            {"value": "opioids", "label": "Opioids"},
            {"value": "cocaine", "label": "Cocaine"},
            {"value": "multiple", "label": "Multiple"},
            {"value": "other", "label": "Other"},
        ],
        "education_options": [
            {"value": "no_hs", "label": "No High School"},
            {"value": "hs", "label": "High School"},
            {"value": "ged", "label": "GED"},
            {"value": "college", "label": "Some College"},
            {"value": "associate", "label": "Associate"},
            {"value": "bachelor", "label": "Bachelor"},
        ],
        "marital_status_options": [
            {"value": "single", "label": "Single"},
            {"value": "married", "label": "Married"},
            {"value": "divorced", "label": "Divorced"},
            {"value": "separated", "label": "Separated"},
            {"value": "widowed", "label": "Widowed"},
            {"value": "partnered", "label": "Partnered"},
            {"value": "other", "label": "Other"},
        ],
        "amarillo_length_options": [
            {"value": "less_than_30_days", "label": "Less than 30 days"},
            {"value": "1_to_6_months", "label": "1 to 6 months"},
            {"value": "6_to_12_months", "label": "6 to 12 months"},
            {"value": "1_to_3_years", "label": "1 to 3 years"},
            {"value": "more_than_3_years", "label": "More than 3 years"},
            {"value": "lifelong", "label": "Lifelong"},
            {"value": "unknown", "label": "Unknown"},
        ],
    }


# ============================================================================
# Index and Intake Landing Routes
# ----------------------------------------------------------------------------
# Future extraction target:
# routes.case_management_parts.index
# ============================================================================

@case_management.get("/")
@require_login
@require_shelter
def index():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))

    residents = db_fetchall(
        f"""
        SELECT
            id,
            first_name,
            last_name,
            resident_code,
            is_active
        FROM residents
        WHERE {shelter_equals_sql("shelter")}
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
def intake_index():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_name,
            entry_date,
            updated_at
        FROM intake_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    assessment_drafts = db_fetchall(
        f"""
        SELECT
            id,
            resident_id,
            updated_at
        FROM assessment_drafts
        WHERE LOWER(COALESCE(shelter, '')) = {ph}
          AND status = 'draft'
        ORDER BY updated_at DESC, id DESC
        """,
        (shelter,),
    )

    return render_template(
        "intake_assessment/index.html",
        drafts=drafts,
        assessment_drafts=assessment_drafts,
        shelter=shelter,
    )


# ============================================================================
# Assessment Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.assessment
# ============================================================================

@case_management.get("/assessment/new")
@require_login
@require_shelter
def assessment_form():
    return assessment_form_view()


@case_management.post("/assessment/new")
@require_login
@require_shelter
def submit_assessment():
    return submit_assessment_view()


# ============================================================================
# Intake Routes
# ----------------------------------------------------------------------------
# These routes display the intake form, save intake drafts, detect duplicates,
# create the resident, create the enrollment, and insert the entry snapshot.
# ============================================================================

@case_management.get("/intake-assessment/new")
@require_login
@require_shelter
def intake_form():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    draft_id = parse_int(request.args.get("draft_id"))
    form_data: dict[str, Any] | None = None

    if draft_id is not None:
        form_data = _load_intake_draft(current_shelter, draft_id)
        if not form_data:
            flash("Intake draft not found.", "error")
            return redirect(url_for("case_management.intake_index"))

    return render_template(
        "case_management/intake_assessment.html",
        **_intake_template_context(
            current_shelter=current_shelter,
            form_data=form_data,
        ),
    )


@case_management.post("/intake-assessment/new")
@require_login
@require_shelter
def submit_intake_assessment():
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    current_shelter = normalize_shelter_name(session.get("shelter"))
    action = (request.form.get("action") or "complete").strip().lower()
    draft_id = parse_int(request.form.get("draft_id"))

    if action == "save_draft":
        first_name = clean(request.form.get("first_name"))
        last_name = clean(request.form.get("last_name"))

        if not first_name or not last_name:
            flash("Save Draft requires at least first name and last name.", "error")
            return render_template(
                "case_management/intake_assessment.html",
                **_intake_template_context(
                    current_shelter=current_shelter,
                    form_data=request.form.to_dict(flat=True),
                ),
            )

        saved_draft_id = _save_intake_draft(
            current_shelter=current_shelter,
            form=request.form,
            draft_id=draft_id,
        )

        flash("Intake draft saved.", "success")
        return redirect(url_for("case_management.intake_form", draft_id=saved_draft_id))

    data, errors = _validate_intake_form(request.form, current_shelter)

    duplicate = _find_possible_duplicate(
        first_name=data["first_name"],
        last_name=data["last_name"],
        birth_year=data["birth_year"],
        phone=data["phone"],
        email=data["email"],
        shelter=current_shelter,
        shelter_equals_sql=shelter_equals_sql,
    )

    if duplicate:
        duplicate_id = duplicate["id"] if isinstance(duplicate, dict) else duplicate[0]
        duplicate_identifier = duplicate["resident_identifier"] if isinstance(duplicate, dict) else duplicate[6]
        if duplicate_identifier:
            flash(
                f"Possible duplicate resident found. Existing Resident ID: {duplicate_identifier}. Review that profile before creating a new one.",
                "error",
            )
        else:
            flash(
                "Possible duplicate resident found. Review the existing profile before creating a new one.",
                "error",
            )
        return redirect(url_for("case_management.resident_case", resident_id=duplicate_id))

    if errors:
        for error in errors:
            flash(error, "error")
        return render_template(
            "case_management/intake_assessment.html",
            **_intake_template_context(
                current_shelter=current_shelter,
                form_data=request.form.to_dict(flat=True),
            ),
        )

    resident_id, resident_identifier, resident_code = _insert_resident(data, current_shelter)
    enrollment_id = _insert_program_enrollment(resident_id, data, current_shelter)
    _insert_intake_assessment(enrollment_id, data)
    _insert_family_snapshot(enrollment_id, data)

    if draft_id is not None:
        _complete_intake_draft(draft_id)

    flash(
        f"Resident created successfully. Resident ID: {resident_identifier}. Resident Code: {resident_code}",
        "success",
    )
    return redirect(url_for("case_management.resident_case", resident_id=resident_id))


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - START
# ----------------------------------------------------------------------------
# PURPOSE:
# This temporary admin-only route wipes resident-related test data so intake
# can be retested from a clean state during development.
#
# IMPORTANT:
# Delete everything from the START comment above to the END comment below after
# testing is complete. Do not leave this route in production long term.
#
# WHAT IT DELETES:
# - family_snapshots
# - intake_assessments
# - assessment_drafts
# - intake_drafts
# - case_manager_updates
# - appointments
# - goals
# - resident_children
# - resident_substances
# - program_enrollments
# - residents
# ============================================================================

@case_management.route("/admin/wipe-test-residents", methods=["GET", "POST"])
@require_login
@require_shelter
def wipe_test_residents():
    if session.get("role") != "admin":
        flash("Admin access required.", "error")
        return redirect(url_for("case_management.index"))

    init_db()

    try:
        db_execute("DELETE FROM family_snapshots")
        db_execute("DELETE FROM intake_assessments")
        db_execute("DELETE FROM assessment_drafts")
        db_execute("DELETE FROM intake_drafts")
        db_execute("DELETE FROM case_manager_updates")
        db_execute("DELETE FROM appointments")
        db_execute("DELETE FROM goals")
        db_execute("DELETE FROM resident_transfers")
        db_execute("DELETE FROM resident_children")
        db_execute("DELETE FROM resident_substances")
        db_execute("DELETE FROM program_enrollments")
        db_execute("DELETE FROM residents")

        flash("All resident-related test data was wiped.", "success")
    except Exception as e:
        flash(f"Wipe failed: {e}", "error")

    return redirect(url_for("case_management.index"))


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - END
# ============================================================================


# ============================================================================
# Resident Case Page
# ----------------------------------------------------------------------------
# This route shows the resident summary page with:
# - latest enrollment
# - goals
# - appointments
# - case manager notes
# ============================================================================

@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    if not case_manager_allowed():
        flash("Case manager access required.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    shelter = normalize_shelter_name(session.get("shelter"))
    ph = placeholder()

    resident = db_fetchone(
        f"""
        SELECT
            id,
            resident_identifier,
            first_name,
            last_name,
            resident_code,
            shelter,
            is_active
        FROM residents
        WHERE id = {ph}
          AND {shelter_equals_sql("shelter")}
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
            shelter,
            program_status,
            entry_date,
            exit_date
        FROM program_enrollments
        WHERE resident_id = {ph}
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
            WHERE enrollment_id = {ph}
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
            WHERE enrollment_id = {ph}
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
            WHERE enrollment_id = {ph}
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
