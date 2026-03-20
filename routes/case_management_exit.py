from __future__ import annotations

from flask import Blueprint

from core.auth import require_login, require_shelter
from routes.case_management_parts.exit import exit_assessment_form_view
from routes.case_management_parts.exit import submit_exit_assessment_view


case_management_exit = Blueprint(
    "case_management_exit",
    __name__,
    url_prefix="/staff/case-management",
)


@case_management_exit.get("/<int:resident_id>/exit-assessment")
@require_login
@require_shelter
def exit_assessment_form(resident_id: int):
    return exit_assessment_form_view(resident_id)


@case_management_exit.post("/<int:resident_id>/exit-assessment")
@require_login
@require_shelter
def submit_exit_assessment(resident_id: int):
    return submit_exit_assessment_view(resident_id)
