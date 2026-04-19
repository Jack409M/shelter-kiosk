from __future__ import annotations

from flask import current_app, flash, redirect, render_template, request, url_for

from core.access import require_resident
from routes.resident_portal import resident_portal
from routes.resident_portal_parts.helpers import (
    _clean_text,
    _clear_resident_session,
    _daily_log_event_time_iso,
    _daily_log_template_context,
    _load_child_options_by_parent,
    _load_daily_log_categories,
    _load_resident_program_level,
    _prepare_resident_request_context,
    _resident_signin_redirect,
    _safe_float,
)
from core.db import db_execute
from routes.resident_portal_parts.helpers import _sql
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_KEY,
    VOLUNTEER_PARENT_ACTIVITY_KEY,
)


@resident_portal.route("/resident/daily-log", methods=["GET", "POST"])
@require_resident
def resident_daily_log():
    resident_id = None
    shelter = ""

    try:
        resident_id, shelter, _resident_identifier = _prepare_resident_request_context()

        resident_level = _load_resident_program_level(resident_id)
        if resident_level < 5:
            return redirect(url_for("resident_portal.home"))

        checkout_categories = _load_daily_log_categories(shelter)
        child_options_by_parent = _load_child_options_by_parent(shelter, checkout_categories)

        if request.method == "POST":
            log_date = _clean_text(request.form.get("log_date"))
            activity_category = _clean_text(request.form.get("activity_category"))
            hours_raw = request.form.get("hours")
            aa_na_meeting_1 = _clean_text(request.form.get("aa_na_meeting_1"))
            aa_na_meeting_2 = _clean_text(request.form.get("aa_na_meeting_2"))
            child_option_value = _clean_text(
                request.form.get("child_option_value")
                or request.form.get("volunteer_community_service_option")
            )
            note = _clean_text(request.form.get("note"))

            errors: list[str] = []

            if not log_date:
                errors.append("Log date is required.")

            event_time_value = _daily_log_event_time_iso(log_date) if log_date else None
            if log_date and not event_time_value:
                errors.append("Invalid log date.")

            category_map = {
                _clean_text(item.get("activity_label")): item
                for item in checkout_categories
                if _clean_text(item.get("activity_label"))
            }
            selected_category = category_map.get(activity_category)

            if not selected_category:
                errors.append("Please select a valid activity category.")

            selected_activity_key = (
                _clean_text(selected_category.get("activity_key")) if selected_category else ""
            )

            is_aa_na = selected_activity_key == AA_NA_PARENT_ACTIVITY_KEY
            selected_child_rows = child_options_by_parent.get(selected_activity_key, [])
            selected_child_option_labels = {
                _clean_text(item.get("option_label"))
                for item in selected_child_rows
                if _clean_text(item.get("option_label"))
            }
            has_generic_child_options = bool(selected_child_option_labels)

            hours_value = _safe_float(hours_raw)

            if is_aa_na:
                if not aa_na_meeting_1:
                    errors.append("Meeting 1 is required.")
                elif aa_na_meeting_1 not in selected_child_option_labels:
                    errors.append("Please select a valid Meeting 1 option.")

                if aa_na_meeting_2 and aa_na_meeting_2 not in selected_child_option_labels:
                    errors.append("Please select a valid Meeting 2 option.")

                if aa_na_meeting_1 and aa_na_meeting_2 and aa_na_meeting_1 == aa_na_meeting_2:
                    errors.append("Meetings cannot be the same.")
            else:
                if hours_value is None:
                    errors.append("Valid hours are required.")

            if not is_aa_na and has_generic_child_options:
                if not child_option_value:
                    errors.append("Activity detail is required.")
                elif child_option_value not in selected_child_option_labels:
                    errors.append("Please select a valid activity detail option.")

            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template(
                    "resident_daily_log.html",
                    **_daily_log_template_context(
                        shelter=shelter,
                        resident_level=resident_level,
                        checkout_categories=checkout_categories,
                        child_options_by_parent=child_options_by_parent,
                    ),
                ), 400

            meeting_count = 0
            meeting_1_value = None
            meeting_2_value = None
            is_recovery = 0

            if is_aa_na:
                meeting_1_value = aa_na_meeting_1 or None
                meeting_2_value = aa_na_meeting_2 or None
                if meeting_1_value:
                    meeting_count += 1
                if meeting_2_value:
                    meeting_count += 1
                is_recovery = 1

            note_parts: list[str] = []

            if not is_aa_na and child_option_value:
                if selected_activity_key == VOLUNTEER_PARENT_ACTIVITY_KEY:
                    note_parts.append(f"Volunteer or Community Service: {child_option_value}")
                else:
                    note_parts.append(f"Activity Detail: {child_option_value}")

            if note:
                note_parts.append(note)

            full_note = " | ".join(note_parts) if note_parts else None

            db_execute(
                _sql(
                    """
                    INSERT INTO attendance_events (
                        resident_id,
                        shelter,
                        event_type,
                        event_time,
                        staff_user_id,
                        note,
                        expected_back_time,
                        destination,
                        obligation_start_time,
                        obligation_end_time,
                        meeting_count,
                        meeting_1,
                        meeting_2,
                        is_recovery_meeting,
                        logged_hours
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    """
                    INSERT INTO attendance_events (
                        resident_id,
                        shelter,
                        event_type,
                        event_time,
                        staff_user_id,
                        note,
                        expected_back_time,
                        destination,
                        obligation_start_time,
                        obligation_end_time,
                        meeting_count,
                        meeting_1,
                        meeting_2,
                        is_recovery_meeting,
                        logged_hours
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                ),
                (
                    resident_id,
                    shelter.lower(),
                    "resident_daily_log",
                    event_time_value,
                    None,
                    full_note,
                    None,
                    activity_category,
                    None,
                    None,
                    meeting_count,
                    meeting_1_value,
                    meeting_2_value,
                    is_recovery,
                    hours_value,
                ),
            )

            flash("Daily log submitted successfully.", "success")
            return redirect(url_for("resident_portal.resident_daily_log"))

        return render_template(
            "resident_daily_log.html",
            **_daily_log_template_context(
                shelter=shelter,
                resident_level=resident_level,
                checkout_categories=checkout_categories,
                child_options_by_parent=child_options_by_parent,
            ),
        )
    except Exception as exc:
        current_app.logger.exception(
            "resident_daily_log_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
