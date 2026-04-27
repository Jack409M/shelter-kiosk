from __future__ import annotations

from flask import Blueprint, current_app, flash, redirect, url_for

from core.auth import require_login, require_shelter
from routes.case_management_parts.actions import (
    add_appointment_view,
    add_goal_view,
    create_enrollment_view,
    set_resident_shelter_pre_enrollment_view,
)
from routes.case_management_parts.assessment import assessment_form_view, submit_assessment_view
from routes.case_management_parts.budget_sessions import (
    add_budget_session_view,
    budget_sessions_view,
    delete_budget_session_view,
    edit_budget_session_view,
    print_budget_view,
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
from routes.case_management_parts.l9_complete import l9_complete_view
from routes.case_management_parts.l9_detail import l9_detail_view
from routes.case_management_parts.l9_disposition import (
    l9_disposition_view,
    submit_l9_disposition_view,
)
from routes.case_management_parts.l9_workspace import (
    complete_l9_followup_view,
    l9_workspace_view,
    review_l9_lifecycle_view,
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
from routes.case_management_parts.resident_status import deactivate_resident_view
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


@case_management.post("/<int:resident_id>/deactivate")
@_view
def deactivate_resident(resident_id: int):
    return deactivate_resident_view(resident_id)


@case_management.get("")
@case_management.get("/")
@_view
def index():
    return index_view()


@case_management.get("/intake-assessment")
@_view
def intake_index():
    return intake_index_view()


# (rest of file unchanged)
