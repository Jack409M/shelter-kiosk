from __future__ import annotations

from flask import flash, redirect, url_for


def _save_assessment_draft(
    current_shelter: str,
    form_data: dict,
    resident_id: int,
    draft_id: int | None = None,
) -> int:
    """
    Standalone assessment drafts were removed under the one intake architecture.

    Kept only as a compatibility shim so any legacy call sites fail safely.
    """
    return int(draft_id or 0)


def _load_assessment_draft(current_shelter: str, draft_id: int) -> dict | None:
    """
    Standalone assessment drafts were removed under the one intake architecture.
    """
    return None


def _complete_assessment_draft(draft_id: int) -> None:
    """
    Standalone assessment drafts were removed under the one intake architecture.
    """
    return None


def _validate_assessment_form(form) -> tuple[dict, list[str]]:
    """
    Standalone assessment validation was removed when assessment was folded
    into the intake system.
    """
    return {}, []


def _find_active_enrollment_id(resident_id: int, shelter: str) -> int | None:
    """
    Standalone assessment finalization was removed under the one intake architecture.
    """
    return None


def _upsert_assessment_for_enrollment(enrollment_id: int, data: dict) -> None:
    """
    Standalone assessment writes were removed under the one intake architecture.
    """
    return None


def assessment_form_view():
    """
    Legacy assessment entry point.

    Assessment is no longer a separate workflow.
    Redirect all traffic back to intake.
    """
    flash("Assessment has been moved into the intake workflow.", "info")
    return redirect(url_for("case_management.intake_index"))


def submit_assessment_view():
    """
    Legacy assessment submit endpoint.

    Assessment is no longer a separate workflow.
    Redirect all traffic back to intake.
    """
    flash("Assessment has been moved into the intake workflow.", "info")
    return redirect(url_for("case_management.intake_index"))
