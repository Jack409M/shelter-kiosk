from __future__ import annotations

# ============================================================================
# Case Management Routes
# ----------------------------------------------------------------------------
# This file is now the transition shell for case management.
#
# Current responsibilities still living here:
# 1. Temporary admin utilities during build and testing
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
# - routes.case_management_parts.intake
#   intake form flow shell
# - routes.case_management_parts.intake_duplicates
#   duplicate review flow for pending intake records
# - routes.case_management_parts.resident_case
#   resident summary page and related reads
# - routes.case_management_parts.index
#   dashboard and intake landing
# - routes.case_management_parts.update
#   progress update flow
# - routes.case_management_parts.actions
#   create enrollment, add goal, and add appointment writes
# - routes.case_management_parts.exit
#   exit assessment flow
# - routes.case_management_parts.followups
#   6 month and 1 year follow up flow
#
# Future extraction plan:
# - routes.case_management_parts.helpers
#   shared parsing, shelter, permission, and SQL helpers
#
# Goal:
# keep shrinking this file until it becomes a thin blueprint shell like admin.py
# ============================================================================

from flask import Blueprint, flash, redirect, session, url_for

from core.auth import require_login, require_shelter
from core.db import db_execute
from core.runtime import init_db
from routes.case_management_parts.actions import add_appointment_view
from routes.case_management_parts.actions import add_goal_view
from routes.case_management_parts.actions import create_enrollment_view
from routes.case_management_parts.assessment import assessment_form_view
from routes.case_management_parts.assessment import submit_assessment_view
from routes.case_management_parts.exit import exit_assessment_form_view
from routes.case_management_parts.exit import submit_exit_assessment_view
from routes.case_management_parts.followups import followup_form_view
from routes.case_management_parts.followups import submit_followup_view
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
from routes.case_management_parts.index import index_view
from routes.case_management_parts.index import intake_index_view
from routes.case_management_parts.intake import family_intake_view
from routes.case_management_parts.intake import intake_form_view
from routes.case_management_parts.intake import submit_intake_assessment_view
from routes.case_management_parts.intake_duplicates import duplicate_review_create_new_view
from routes.case_management_parts.intake_duplicates import duplicate_review_dismiss_view
from routes.case_management_parts.intake_duplicates import duplicate_review_return_to_edit_view
from routes.case_management_parts.intake_duplicates import duplicate_review_use_existing_view
from routes.case_management_parts.intake_duplicates import duplicate_review_view
from routes.case_management_parts.resident_case import resident_case_view
from routes.case_management_parts.update import add_case_note_view
from routes.case_management_parts.update import edit_case_note_view


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
# Index and Intake Landing Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.index
# ============================================================================

@case_management.get("/")
@require_login
@require_shelter
def index():
    return index_view()


@case_management.get("/intake-assessment")
@require_login
@require_shelter
def intake_index():
    return intake_index_view()


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
# Extracted to routes.case_management_parts.intake
# ============================================================================

@case_management.get("/intake-assessment/new")
@require_login
@require_shelter
def intake_form():
    return intake_form_view()


@case_management.post("/intake-assessment/new")
@require_login
@require_shelter
def submit_intake_assessment():
    return submit_intake_assessment_view()


@case_management.route("/<int:resident_id>/family-intake", methods=["GET", "POST"])
@require_login
@require_shelter
def family_intake(resident_id: int):
    return family_intake_view(resident_id)


# ============================================================================
# Intake Duplicate Review Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.intake_duplicates
# ============================================================================

@case_management.get("/intake-assessment/duplicate-review/<int:draft_id>")
@require_login
@require_shelter
def intake_duplicate_review(draft_id: int):
    return duplicate_review_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/use-existing")
@require_login
@require_shelter
def intake_duplicate_use_existing(draft_id: int):
    return duplicate_review_use_existing_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/create-new")
@require_login
@require_shelter
def intake_duplicate_create_new(draft_id: int):
    return duplicate_review_create_new_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/dismiss")
@require_login
@require_shelter
def intake_duplicate_dismiss(draft_id: int):
    return duplicate_review_dismiss_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/return-to-edit")
@require_login
@require_shelter
def intake_duplicate_return_to_edit(draft_id: int):
    return duplicate_review_return_to_edit_view(draft_id)


# ============================================================================
# Exit Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.exit
# ============================================================================

@case_management.get("/<int:resident_id>/exit-assessment")
@require_login
@require_shelter
def exit_assessment(resident_id: int):
    return exit_assessment_form_view(resident_id)


@case_management.post("/<int:resident_id>/exit-assessment")
@require_login
@require_shelter
def submit_exit_assessment(resident_id: int):
    return submit_exit_assessment_view(resident_id)


# ============================================================================
# Follow Up Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.followups
# ============================================================================

@case_management.get("/<int:resident_id>/followup/<string:followup_type>")
@require_login
@require_shelter
def followup_form(resident_id: int, followup_type: str):
    return followup_form_view(resident_id, followup_type)


@case_management.post("/<int:resident_id>/followup/<string:followup_type>")
@require_login
@require_shelter
def submit_followup(resident_id: int, followup_type: str):
    return submit_followup_view(resident_id, followup_type)


# ============================================================================
# Case Management Actions
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.actions
# ============================================================================

@case_management.post("/case/<int:resident_id>/enroll")
@require_login
@require_shelter
def create_enrollment(resident_id: int):
    return create_enrollment_view(resident_id)


@case_management.post("/case/<int:resident_id>/goal")
@require_login
@require_shelter
def add_goal(resident_id: int):
    return add_goal_view(resident_id)


@case_management.post("/case/<int:resident_id>/appointment")
@require_login
@require_shelter
def add_appointment(resident_id: int):
    return add_appointment_view(resident_id)


# ============================================================================
# Case Manager Update Routes
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.update
# ============================================================================

@case_management.post("/<int:resident_id>/case-notes")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    return add_case_note_view(resident_id)


@case_management.route("/<int:resident_id>/case-notes/<int:update_id>/edit", methods=["GET", "POST"])
@require_login
@require_shelter
def edit_case_note(resident_id: int, update_id: int):
    return edit_case_note_view(resident_id, update_id)


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - START
# ----------------------------------------------------------------------------
# PURPOSE:
# This temporary admin only route wipes resident related test data so intake
# can be retested from a clean state during development.
#
# IMPORTANT:
# Delete everything from the START comment above to the END comment below after
# testing is complete. Do not leave this route in production long term.
#
# WHAT IT DELETES:
# - weekly_resident_summary
# - exit_assessments
# - followups
# - family_snapshots
# - intake_assessments
# - assessment_drafts
# - intake_drafts
# - case_manager_updates
# - appointments
# - goals
# - resident_form_submissions
# - resident_transfers
# - attendance_events
# - resident_passes
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
        # Deepest child records first
        db_execute("DELETE FROM weekly_resident_summary")
        db_execute("DELETE FROM exit_assessments")
        db_execute("DELETE FROM followups")
        db_execute("DELETE FROM family_snapshots")
        db_execute("DELETE FROM intake_assessments")
        db_execute("DELETE FROM case_manager_updates")
        db_execute("DELETE FROM goals")
        db_execute("DELETE FROM appointments")
        db_execute("DELETE FROM resident_form_submissions")

        # Drafts and resident linked supporting records
        db_execute("DELETE FROM assessment_drafts")
        db_execute("DELETE FROM intake_drafts")
        db_execute("DELETE FROM resident_transfers")
        db_execute("DELETE FROM attendance_events")
        db_execute("DELETE FROM resident_passes")
        db_execute("DELETE FROM resident_children")
        db_execute("DELETE FROM resident_substances")

        # Parent records last
        db_execute("DELETE FROM program_enrollments")
        db_execute("DELETE FROM residents")

        flash("All residents and resident related data were wiped.", "success")
    except Exception as e:
        flash(f"Wipe failed: {e}", "error")

    return redirect(url_for("case_management.index"))


# ============================================================================
# TEMPORARY TEST DATA WIPE ROUTE - END
# ============================================================================


# ============================================================================
# Resident Case Page
# ----------------------------------------------------------------------------
# Extracted to routes.case_management_parts.resident_case
# ============================================================================

@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    return resident_case_view(resident_id)
