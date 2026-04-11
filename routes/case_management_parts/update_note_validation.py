from __future__ import annotations

from flask import flash, redirect, url_for


def has_structured_progress(values, *, include_needs: bool):
    return (
        values["updated_grit"] is not None
        or values["parenting_class_completed"] is not None
        or values["warrants_or_fines_paid"] is not None
        or values["ready_for_next_level"] is not None
        or bool(values["recommended_next_level"])
        or bool(values["blocker_reason"])
        or bool(values["override_or_exception"])
        or bool(values["staff_review_note"])
        or bool(values["service_types"])
        or (include_needs and bool(values["need_updates"]))
    )


def validate_note_values(values, *, resident_id: int, include_needs: bool):
    if values["updated_grit_raw"] and values["updated_grit"] is None:
        flash("Updated grit must be a whole number between 0 and 100.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    if not values["meeting_date"]:
        flash("Meeting date is required.", "error")
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    structured_progress = has_structured_progress(values, include_needs=include_needs)

    if (
        not values["notes"]
        and not values["progress_notes"]
        and not values["setbacks_or_incidents"]
        and not values["action_items"]
        and not values["overall_summary"]
        and not structured_progress
    ):
        if include_needs:
            flash(
                "Enter notes, progress notes, setbacks or incidents, action items, meeting summary, advancement review details, structured progress, need resolutions, or at least one service.",
                "error",
            )
        else:
            flash(
                "Enter notes, progress notes, setbacks or incidents, action items, meeting summary, advancement review details, structured progress, or at least one service.",
                "error",
            )
        return redirect(url_for("case_management.resident_case", resident_id=resident_id))

    return None
