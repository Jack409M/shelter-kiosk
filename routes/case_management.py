from __future__ import annotations

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

from routes.case_management_parts.intake import intake_form_view
from routes.case_management_parts.intake import submit_intake_assessment_view

from routes.case_management_parts.intake_duplicates import duplicate_review_create_new_view
from routes.case_management_parts.intake_duplicates import duplicate_review_dismiss_view
from routes.case_management_parts.intake_duplicates import duplicate_review_return_to_edit_view
from routes.case_management_parts.intake_duplicates import duplicate_review_use_existing_view
from routes.case_management_parts.intake_duplicates import duplicate_review_view

from routes.case_management_parts.resident_case import resident_case_view

# 🔥 UPDATED IMPORT
from routes.case_management_parts.update import add_case_note_view
from routes.case_management_parts.update import edit_case_note_view


case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


# =========================
# Index
# =========================

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


# =========================
# Assessment
# =========================

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


# =========================
# Intake
# =========================

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


# =========================
# Duplicate Review
# =========================

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


# =========================
# Exit
# =========================

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


# =========================
# Followup
# =========================

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


# =========================
# Actions
# =========================

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


# =========================
# Case Notes
# =========================

@case_management.post("/<int:resident_id>/case-notes")
@require_login
@require_shelter
def add_case_note(resident_id: int):
    return add_case_note_view(resident_id)


# 🔥 NEW EDIT ROUTE
@case_management.post("/<int:resident_id>/case-notes/<int:note_id>/edit")
@require_login
@require_shelter
def edit_case_note(resident_id: int, note_id: int):
    return edit_case_note_view(resident_id, note_id)


# =========================
# Resident Page
# =========================

@case_management.get("/<int:resident_id>")
@require_login
@require_shelter
def resident_case(resident_id: int):
    return resident_case_view(resident_id)
