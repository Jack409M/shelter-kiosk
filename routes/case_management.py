from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter
from routes.case_management_parts.actions import (
    add_appointment_view,
    add_goal_view,
    create_enrollment_view,
)
from routes.case_management_parts.assessment import assessment_form_view, submit_assessment_view
from routes.case_management_parts.budget_sessions import (
    add_budget_session_view,
    budget_sessions_view,
    delete_budget_session_view,
    edit_budget_session_view,
)
from routes.case_management_parts.exit import exit_assessment_form_view, submit_exit_assessment_view
from routes.case_management_parts.exit_followup import exit_followup_view
from routes.case_management_parts.family import (
    child_services_view,
    delete_child_service_view,
    delete_child_view,
    edit_child_service_view,
    edit_child_view,
    family_intake_view,
)
from routes.case_management_parts.followups import followup_form_view, submit_followup_view
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    digits_only,
    normalize_shelter_name,
    parse_int,
    parse_iso_date,
    parse_money,
    placeholder,
    shelter_equals_sql,
    yes_no_to_int,
)
from routes.case_management_parts.income_support import income_support_view
from routes.case_management_parts.index import index_view, intake_index_view
from routes.case_management_parts.inspection_log import (
    add_inspection_log_view,
    edit_inspection_log_view,
    inspection_log_view,
)
from routes.case_management_parts.intake import (
    intake_edit_view,
    intake_form_view,
    submit_intake_assessment_view,
)
from routes.case_management_parts.intake_duplicates import (
    duplicate_review_create_new_view,
    duplicate_review_dismiss_view,
    duplicate_review_return_to_edit_view,
    duplicate_review_use_existing_view,
    duplicate_review_view,
)
from routes.case_management_parts.medications import (
    add_medication_view,
    edit_medication_view,
    medication_form_view,
)
from routes.case_management_parts.notes_history import notes_history_view
from routes.case_management_parts.progress_report import progress_report_print_view
from routes.case_management_parts.promotion_review import promotion_review_view
from routes.case_management_parts.recovery_profile import update_recovery_profile_view
from routes.case_management_parts.resident_case import resident_case_view
from routes.case_management_parts.transfer import (
    submit_transfer_resident_view,
    transfer_resident_form_view,
)
from routes.case_management_parts.ua_log import add_ua_log_view, edit_ua_log_view, ua_log_view
from routes.case_management_parts.update import add_case_note_view, edit_case_note_view


def _view(view_func):
    return require_login(require_shelter(view_func))


case_management = Blueprint(
    "case_management",
    __name__,
    url_prefix="/staff/case-management",
)


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


@case_management.get("/")
@_view
def index():
    return index_view()


@case_management.get("/intake-assessment")
@_view
def intake_index():
    return intake_index_view()


@case_management.get("/assessment/new")
@_view
def assessment_form():
    return assessment_form_view()


@case_management.post("/assessment/new")
@_view
def submit_assessment():
    return submit_assessment_view()


@case_management.get("/intake-assessment/new")
@_view
def intake_form():
    return intake_form_view()


@case_management.post("/intake-assessment/new")
@_view
def submit_intake_assessment():
    return submit_intake_assessment_view()


@case_management.get("/<int:resident_id>/intake-edit")
@_view
def intake_edit(resident_id: int):
    return intake_edit_view(resident_id)


@case_management.route("/<int:resident_id>/family-intake", methods=["GET", "POST"])
@_view
def family_intake(resident_id: int):
    return family_intake_view(resident_id)


@case_management.route("/child/<int:child_id>/edit", methods=["GET", "POST"])
@_view
def edit_child(child_id: int):
    return edit_child_view(child_id)


@case_management.post("/child/<int:child_id>/delete")
@_view
def delete_child(child_id: int):
    return delete_child_view(child_id)


@case_management.route("/child/<int:child_id>/services", methods=["GET", "POST"])
@_view
def child_services(child_id: int):
    return child_services_view(child_id)


@case_management.route("/child-service/<int:service_id>/edit", methods=["GET", "POST"])
@_view
def edit_child_service(service_id: int):
    return edit_child_service_view(service_id)


@case_management.post("/child-service/<int:service_id>/delete")
@_view
def delete_child_service(service_id: int):
    return delete_child_service_view(service_id)


@case_management.get("/intake-assessment/duplicate-review/<int:draft_id>")
@_view
def intake_duplicate_review(draft_id: int):
    return duplicate_review_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/use-existing")
@_view
def intake_duplicate_use_existing(draft_id: int):
    return duplicate_review_use_existing_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/create-new")
@_view
def intake_duplicate_create_new(draft_id: int):
    return duplicate_review_create_new_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/dismiss")
@_view
def intake_duplicate_dismiss(draft_id: int):
    return duplicate_review_dismiss_view(draft_id)


@case_management.post("/intake-assessment/duplicate-review/<int:draft_id>/return-to-edit")
@_view
def intake_duplicate_return_to_edit(draft_id: int):
    return duplicate_review_return_to_edit_view(draft_id)


@case_management.get("/<int:resident_id>/exit-assessment")
@_view
def exit_assessment(resident_id: int):
    return exit_assessment_form_view(resident_id)


@case_management.post("/<int:resident_id>/exit-assessment")
@_view
def submit_exit_assessment(resident_id: int):
    return submit_exit_assessment_view(resident_id)


@case_management.get("/<int:resident_id>/transfer")
@_view
def transfer_resident_form(resident_id: int):
    return transfer_resident_form_view(resident_id)


@case_management.post("/<int:resident_id>/transfer")
@_view
def submit_transfer_resident(resident_id: int):
    return submit_transfer_resident_view(resident_id)


@case_management.get("/<int:resident_id>/followup/<string:followup_type>")
@_view
def followup_form(resident_id: int, followup_type: str):
    return followup_form_view(resident_id, followup_type)


@case_management.post("/<int:resident_id>/followup/<string:followup_type>")
@_view
def submit_followup(resident_id: int, followup_type: str):
    return submit_followup_view(resident_id, followup_type)


@case_management.post("/case/<int:resident_id>/enroll")
@_view
def create_enrollment(resident_id: int):
    return create_enrollment_view(resident_id)


@case_management.post("/case/<int:resident_id>/goal")
@_view
def add_goal(resident_id: int):
    return add_goal_view(resident_id)


@case_management.post("/case/<int:resident_id>/appointment")
@_view
def add_appointment(resident_id: int):
    return add_appointment_view(resident_id)


@case_management.post("/<int:resident_id>/recovery-profile")
@_view
def update_recovery_profile(resident_id: int):
    return update_recovery_profile_view(resident_id)


@case_management.route("/<int:resident_id>/income-support", methods=["GET", "POST"])
@_view
def income_support(resident_id: int):
    return income_support_view(resident_id)


@case_management.get("/<int:resident_id>/medications")
@_view
def medications(resident_id: int):
    return medication_form_view(resident_id)


@case_management.post("/<int:resident_id>/medications")
@_view
def add_medication(resident_id: int):
    return add_medication_view(resident_id)


@case_management.route(
    "/<int:resident_id>/medications/<int:medication_id>/edit", methods=["GET", "POST"]
)
@_view
def edit_medication(resident_id: int, medication_id: int):
    return edit_medication_view(resident_id, medication_id)


@case_management.get("/<int:resident_id>/ua-log")
@_view
def ua_log(resident_id: int):
    return ua_log_view(resident_id)


@case_management.post("/<int:resident_id>/ua-log")
@_view
def add_ua_log(resident_id: int):
    return add_ua_log_view(resident_id)


@case_management.route("/<int:resident_id>/ua-log/<int:ua_id>/edit", methods=["GET", "POST"])
@_view
def edit_ua_log(resident_id: int, ua_id: int):
    return edit_ua_log_view(resident_id, ua_id)


@case_management.get("/<int:resident_id>/inspection-log")
@_view
def inspection_log(resident_id: int):
    return inspection_log_view(resident_id)


@case_management.post("/<int:resident_id>/inspection-log")
@_view
def add_inspection_log(resident_id: int):
    return add_inspection_log_view(resident_id)


@case_management.route(
    "/<int:resident_id>/inspection-log/<int:inspection_id>/edit", methods=["GET", "POST"]
)
@_view
def edit_inspection_log(resident_id: int, inspection_id: int):
    return edit_inspection_log_view(resident_id, inspection_id)


@case_management.get("/<int:resident_id>/budget-sessions")
@_view
def budget_sessions(resident_id: int):
    return budget_sessions_view(resident_id)


@case_management.post("/<int:resident_id>/budget-sessions")
@_view
def add_budget_session(resident_id: int):
    return add_budget_session_view(resident_id)


@case_management.route(
    "/<int:resident_id>/budget-sessions/<int:budget_id>/edit", methods=["GET", "POST"]
)
@_view
def edit_budget_session(resident_id: int, budget_id: int):
    return edit_budget_session_view(resident_id, budget_id)


@case_management.post("/<int:resident_id>/budget-sessions/<int:budget_id>/delete")
@_view
def delete_budget_session(resident_id: int, budget_id: int):
    return delete_budget_session_view(resident_id, budget_id)


@case_management.post("/<int:resident_id>/case-notes")
@_view
def add_case_note(resident_id: int):
    return add_case_note_view(resident_id)


@case_management.route(
    "/<int:resident_id>/case-notes/<int:update_id>/edit", methods=["GET", "POST"]
)
@_view
def edit_case_note(resident_id: int, update_id: int):
    return edit_case_note_view(resident_id, update_id)


@case_management.get("/<int:resident_id>/case-notes/<int:update_id>/print")
@_view
def progress_report_print(resident_id: int, update_id: int):
    return progress_report_print_view(resident_id, update_id)


@case_management.route("/<int:resident_id>/promotion-review", methods=["GET", "POST"])
@_view
def promotion_review(resident_id: int):
    return promotion_review_view(resident_id)


@case_management.get("/<int:resident_id>/exit-followup")
@_view
def exit_followup(resident_id: int):
    return exit_followup_view(resident_id)


@case_management.get("/<int:resident_id>/notes-history")
@_view
def notes_history(resident_id: int):
    return notes_history_view(resident_id)


@case_management.get("/<int:resident_id>")
@_view
def resident_case(resident_id: int):
    return resident_case_view(resident_id)
