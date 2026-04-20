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
    edit_budget_session_view,
    delete_budget_session_view,
)
# rest unchanged...

@case_management.post("/<int:resident_id>/budget-sessions/<int:budget_id>/delete")
@_view
def delete_budget_session(resident_id: int, budget_id: int):
    return delete_budget_session_view(resident_id, budget_id)
