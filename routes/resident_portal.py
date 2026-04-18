from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, current_app, flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.db import db_execute, db_fetchall, db_fetchone, get_db
from core.kiosk_activity_categories import (
    AA_NA_PARENT_ACTIVITY_KEY,
    VOLUNTEER_PARENT_ACTIVITY_KEY,
    load_active_kiosk_activity_child_options_for_shelter,
    load_kiosk_activity_categories_for_shelter,
)
from core.pass_retention import run_pass_retention_cleanup_for_shelter
from core.pass_rules import CHICAGO_TZ, pass_type_label
from core.helpers import utcnow_iso
from routes.attendance_parts.helpers import to_local

resident_portal = Blueprint("resident_portal", __name__)


def _clear_resident_session() -> None:
    session.clear()


def _resident_signin_redirect():
    return redirect(url_for("resident_requests.resident_signin", next=request.path))


def _sql(pg_sql: str, sqlite_sql: str) -> str:
    return pg_sql if g.get("db_kind") == "pg" else sqlite_sql


def _clean_text(value: object) -> str:
    return str(value or "").strip()


def _safe_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _safe_float(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None

    if parsed <= 0:
        return None

    return parsed


def _daily_log_event_time_iso(log_date_text: str) -> str | None:
    try:
        parsed_date = datetime.strptime(log_date_text, "%Y-%m-%d")
    except ValueError:
        return None

    local_dt = parsed_date.replace(hour=12, minute=0, second=0, microsecond=0, tzinfo=CHICAGO_TZ)
    utc_dt = local_dt.astimezone(timezone.utc).replace(tzinfo=None)
    return utc_dt.isoformat(timespec="seconds")


def _load_resident_program_level(resident_id: int | None) -> int:
    if resident_id is None:
        return 0

    row = db_fetchone(
        _sql(
            """
            SELECT program_level
            FROM residents
            WHERE id = %s
            LIMIT 1
            """,
            """
            SELECT program_level
            FROM residents
            WHERE id = ?
            LIMIT 1
            """,
        ),
        (resident_id,),
    )

    if not row:
        return 0

    return _safe_int(row.get("program_level")) or 0


def _load_daily_log_categories(shelter: str) -> list[dict[str, Any]]:
    if not shelter:
        return []

    rows = load_kiosk_activity_categories_for_shelter(shelter)
    categories: list[dict[str, Any]] = []

    for row in rows or []:
        item = dict(row)
        if not item.get("active"):
            continue

        activity_label = _clean_text(item.get("activity_label"))
        if not activity_label:
            continue

        categories.append(item)

    return categories


def _load_aa_na_child_options(shelter: str) -> list[dict[str, Any]]:
    if not shelter:
        return []

    rows = load_active_kiosk_activity_child_options_for_shelter(
        shelter,
        AA_NA_PARENT_ACTIVITY_KEY,
    )
    options: list[dict[str, Any]] = []

    for row in rows or []:
        item = dict(row)
        if not _clean_text(item.get("option_label")):
            continue
        options.append(item)

    return options


def _load_volunteer_child_options(shelter: str) -> list[dict[str, Any]]:
    if not shelter:
        return []

    rows = load_active_kiosk_activity_child_options_for_shelter(
        shelter,
        VOLUNTEER_PARENT_ACTIVITY_KEY,
    )
    options: list[dict[str, Any]] = []

    for row in rows or []:
        item = dict(row)
        if not _clean_text(item.get("option_label")):
            continue
        options.append(item)

    return options


@resident_portal.route("/resident/home")
@require_resident
def home():
    resident_id = None
    shelter = ""

    try:
        resident_id_raw = session.get("resident_id")
        resident_id = int(resident_id_raw) if resident_id_raw not in (None, "") else None
        shelter = str(session.get("resident_shelter") or "").strip()
        resident_identifier = str(session.get("resident_identifier") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        resident_level = _load_resident_program_level(resident_id)
        pass_items = []
        active_pass = None
        notification_items = []
        transport_items = []
        chores: list[dict[str, Any]] = []

        return render_template(
            "resident_home.html",
            recent_items=pass_items,
            pass_items=pass_items,
            active_pass=active_pass,
            notification_items=notification_items,
            transport_items=transport_items,
            chores=chores,
            resident_level=resident_level,
        )
    except Exception as exc:
        current_app.logger.exception(
            "resident_portal_home_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()


@resident_portal.route("/resident/daily-log", methods=["GET", "POST"])
@require_resident
def resident_daily_log():
    resident_id = None
    shelter = ""

    try:
        resident_id_raw = session.get("resident_id")
        resident_id = int(resident_id_raw) if resident_id_raw not in (None, "") else None
        shelter = str(session.get("resident_shelter") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        resident_level = _load_resident_program_level(resident_id)
        if resident_level < 5:
            return redirect(url_for("resident_portal.home"))

        checkout_categories = _load_daily_log_categories(shelter)
        aa_na_child_options = _load_aa_na_child_options(shelter)
        volunteer_child_options = _load_volunteer_child_options(shelter)

        if request.method == "POST":
            log_date = _clean_text(request.form.get("log_date"))
            activity_category = _clean_text(request.form.get("activity_category"))
            hours_raw = request.form.get("hours")
            aa_na_meeting_1 = _clean_text(request.form.get("aa_na_meeting_1"))
            aa_na_meeting_2 = _clean_text(request.form.get("aa_na_meeting_2"))
            volunteer_option = _clean_text(request.form.get("volunteer_community_service_option"))
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
            is_volunteer = selected_activity_key == VOLUNTEER_PARENT_ACTIVITY_KEY

            hours_value = _safe_float(hours_raw)

            if is_aa_na:
                if not aa_na_meeting_1:
                    errors.append("Meeting 1 is required.")
                if aa_na_meeting_1 and aa_na_meeting_2 and aa_na_meeting_1 == aa_na_meeting_2:
                    errors.append("Meetings cannot be the same.")
            else:
                if hours_value is None:
                    errors.append("Valid hours are required.")

            if is_volunteer and not volunteer_option:
                errors.append("Volunteer selection is required.")

            if errors:
                for err in errors:
                    flash(err, "error")
                return render_template(
                    "resident_daily_log.html",
                    shelter=shelter,
                    resident_level=resident_level,
                    checkout_categories=checkout_categories,
                    aa_na_parent_activity_key=AA_NA_PARENT_ACTIVITY_KEY,
                    aa_na_child_options=aa_na_child_options,
                    volunteer_parent_activity_key=VOLUNTEER_PARENT_ACTIVITY_KEY,
                    volunteer_child_options=volunteer_child_options,
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

            if is_volunteer and volunteer_option:
                note_parts.append(f"Volunteer or Community Service: {volunteer_option}")

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
            shelter=shelter,
            resident_level=resident_level,
            checkout_categories=checkout_categories,
            aa_na_parent_activity_key=AA_NA_PARENT_ACTIVITY_KEY,
            aa_na_child_options=aa_na_child_options,
            volunteer_parent_activity_key=VOLUNTEER_PARENT_ACTIVITY_KEY,
            volunteer_child_options=volunteer_child_options,
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


@resident_portal.route("/resident/chores")
@require_resident
def resident_chores():
    shelter = ""

    try:
        shelter = str(session.get("resident_shelter") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        return render_template("resident_chores.html")
    except Exception as exc:
        current_app.logger.exception(
            "resident_portal_chores_failed shelter=%s exception_type=%s",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
