from __future__ import annotations

from typing import Any

from flask import abort, current_app, flash, redirect, render_template, request, session, url_for

from core.constants import EDUCATION_LEVEL_OPTIONS
from core.intake_service import (
    intake_edit_form_data,
    resident_enrollment_in_scope,
    save_intake_review_decision,
    update_intake,
)
from core.intake_finalization import finalize_intake
from core.runtime import init_db
from routes.case_management_parts.helpers import (
    case_manager_allowed,
    clean,
    normalize_shelter_name,
    parse_int,
)
from routes.case_management_parts.intake_drafts import _load_intake_draft
from routes.case_management_parts.intake_validation import (
    _find_possible_duplicate,
    _validate_intake_form,
)
from routes.case_management_parts.needs import OFFICIAL_NEEDS

# --- rest of file unchanged until _handle_create ---

# (content omitted here intentionally for brevity in this operation - no functional change above)


def _handle_create(
    *,
    current_shelter: str,
    draft_id: int | None,
    resident_id: int | None,
    data: dict[str, Any],
    review_passed: bool,
    is_edit_mode: bool,
):
    del resident_id
    del is_edit_mode

    try:
        create_result = finalize_intake(
            current_shelter=current_shelter,
            data=data,
            draft_id=draft_id,
        )
    except Exception:
        current_app.logger.exception(
            "Failed to finalize intake for shelter=%s first_name=%s last_name=%s",
            current_shelter,
            data.get("first_name"),
            data.get("last_name"),
        )
        flash("Unable to save intake. Please try again or contact an administrator.", "error")
        return _render_intake_form_from_request(
            current_shelter=current_shelter,
            review_passed=review_passed,
            is_edit_mode=False,
            resident_id=None,
        )

    flash(
        f"Resident created successfully. Resident ID: {create_result.resident_identifier}. Resident Code: {create_result.resident_code}",
        "success",
    )
    return redirect(url_for("case_management.intake_edit", resident_id=create_result.resident_id))
