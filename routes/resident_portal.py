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
from core.resident_portal_service import chi_today_str, complete_chore, get_today_chores
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


def _load_child_options_by_parent(shelter: str, checkout_categories: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    if not shelter:
        return {}

    parent_keys = {
        _clean_text(item.get("activity_key"))
        for item in checkout_categories
        if _clean_text(item.get("activity_key"))
    }

    child_options_by_parent: dict[str, list[dict[str, Any]]] = {}
    for parent_key in sorted(parent_keys):
        rows = load_active_kiosk_activity_child_options_for_shelter(shelter, parent_key)
        options: list[dict[str, Any]] = []

        for row in rows or []:
            item = dict(row)
            if not _clean_text(item.get("option_label")):
                continue
            options.append(item)

        if options:
            child_options_by_parent[parent_key] = options

    return child_options_by_parent


def _daily_log_template_context(
    *,
    shelter: str,
    resident_level: int,
    checkout_categories: list[dict[str, Any]],
    child_options_by_parent: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    aa_na_child_options = child_options_by_parent.get(AA_NA_PARENT_ACTIVITY_KEY, [])
    child_option_labels_by_parent = {
        parent_key: [
            _clean_text(item.get("option_label"))
            for item in rows
            if _clean_text(item.get("option_label"))
        ]
        for parent_key, rows in child_options_by_parent.items()
    }

    return {
        "shelter": shelter,
        "resident_level": resident_level,
        "checkout_categories": checkout_categories,
        "aa_na_parent_activity_key": AA_NA_PARENT_ACTIVITY_KEY,
        "aa_na_child_options": aa_na_child_options,
        "volunteer_parent_activity_key": VOLUNTEER_PARENT_ACTIVITY_KEY,
        "child_option_labels_by_parent": child_option_labels_by_parent,
    }


def _hydrate_pass_item(row: dict[str, Any]) -> dict[str, Any]:
    item = dict(row)
    item["pass_type_label"] = pass_type_label(item.get("pass_type"))
    item["start_at_local"] = to_local(item.get("start_at"))
    item["end_at_local"] = to_local(item.get("end_at"))
    item["created_at_local"] = to_local(item.get("created_at"))
    item["approved_at_local"] = to_local(item.get("approved_at"))
    item["is_active"] = _pass_item_is_active(item)
    return item


def _pass_item_is_active(item: dict[str, Any]) -> bool:
    if _clean_text(item.get("status")).lower() != "approved":
        return False

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]
    start_at = _clean_text(item.get("start_at"))
    end_at = _clean_text(item.get("end_at"))
    start_date = _clean_text(item.get("start_date"))
    end_date = _clean_text(item.get("end_date"))

    if start_at and end_at:
        return start_at <= now_iso <= end_at

    if start_date and end_date:
        return start_date <= today_iso <= end_date

    return False


def _load_recent_pass_items(resident_id: int | None, shelter: str) -> list[dict[str, Any]]:
    if resident_id is None or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at,
                rprd.request_date
            FROM resident_passes rp
            LEFT JOIN resident_pass_request_details rprd
              ON rprd.pass_id = rp.id
            WHERE rp.resident_id = %s
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
            ORDER BY rp.created_at DESC, rp.id DESC
            LIMIT 5
            """,
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at,
                rprd.request_date
            FROM resident_passes rp
            LEFT JOIN resident_pass_request_details rprd
              ON rprd.pass_id = rp.id
            WHERE rp.resident_id = ?
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
            ORDER BY rp.created_at DESC, rp.id DESC
            LIMIT 5
            """,
        ),
        (resident_id, shelter),
    )

    return [_hydrate_pass_item(row) for row in rows]


def _load_active_pass_item(resident_id: int | None, shelter: str) -> dict[str, Any] | None:
    if resident_id is None or not shelter:
        return None

    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    rows = db_fetchall(
        _sql(
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at
            FROM resident_passes rp
            WHERE rp.resident_id = %s
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
              AND rp.status = 'approved'
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= %s AND rp.end_at >= %s)
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= %s AND rp.end_date >= %s)
              )
            ORDER BY rp.approved_at DESC, rp.created_at DESC, rp.id DESC
            LIMIT 1
            """,
            """
            SELECT
                rp.id,
                rp.pass_type,
                rp.status,
                rp.start_at,
                rp.end_at,
                rp.start_date,
                rp.end_date,
                rp.destination,
                rp.reason,
                rp.resident_notes,
                rp.staff_notes,
                rp.created_at,
                rp.approved_at
            FROM resident_passes rp
            WHERE rp.resident_id = ?
              AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
              AND rp.status = 'approved'
              AND (
                    (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= ? AND rp.end_at >= ?)
                 OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= ? AND rp.end_date >= ?)
              )
            ORDER BY rp.approved_at DESC, rp.created_at DESC, rp.id DESC
            LIMIT 1
            """,
        ),
        (resident_id, shelter, now_iso, now_iso, today_iso, today_iso),
    )

    if not rows:
        return None

    return _hydrate_pass_item(rows[0])


def _load_recent_notification_items(resident_id: int | None, shelter: str) -> list[dict[str, Any]]:
    if resident_id is None or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            """
            SELECT
                id,
                title,
                message,
                is_read,
                created_at,
                related_pass_id,
                notification_type
            FROM resident_notifications
            WHERE resident_id = %s
              AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """,
            """
            SELECT
                id,
                title,
                message,
                is_read,
                created_at,
                related_pass_id,
                notification_type
            FROM resident_notifications
            WHERE resident_id = ?
              AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
            ORDER BY created_at DESC, id DESC
            LIMIT 5
            """,
        ),
        (resident_id, shelter),
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["created_at_local"] = to_local(item.get("created_at"))
        item["is_unread"] = str(item.get("is_read") or "0").strip() in {"0", "False", "false", ""}
        items.append(item)
    return items


def _load_recent_transport_items(resident_identifier: str, shelter: str) -> list[dict[str, Any]]:
    if not resident_identifier or not shelter:
        return []

    rows = db_fetchall(
        _sql(
            """
            SELECT
                id,
                needed_at,
                destination,
                status,
                reason,
                resident_notes,
                submitted_at,
                scheduled_at,
                staff_notes
            FROM transport_requests
            WHERE resident_identifier = %s
              AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            ORDER BY submitted_at DESC, id DESC
            LIMIT 5
            """,
            """
            SELECT
                id,
                needed_at,
                destination,
                status,
                reason,
                resident_notes,
                submitted_at,
                scheduled_at,
                staff_notes
            FROM transport_requests
            WHERE resident_identifier = ?
              AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
            ORDER BY submitted_at DESC, id DESC
            LIMIT 5
            """,
        ),
        (resident_identifier, shelter),
    )

    items: list[dict[str, Any]] = []
    for row in rows:
        item = dict(row)
        item["needed_at_local"] = to_local(item.get("needed_at"))
        item["submitted_at_local"] = to_local(item.get("submitted_at"))
        item["scheduled_at_local"] = to_local(item.get("scheduled_at"))
        items.append(item)
    return items


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
        pass_items = _load_recent_pass_items(resident_id, shelter)
        active_pass = _load_active_pass_item(resident_id, shelter)
        notification_items = _load_recent_notification_items(resident_id, shelter)
        transport_items = _load_recent_transport_items(resident_identifier, shelter)
        chores = get_today_chores(resident_id) if resident_id is not None else []

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


@resident_portal.route("/resident/chores", methods=["GET", "POST"])
@require_resident
def resident_chores():
    resident_id = None
    shelter = ""

    try:
        resident_id_raw = session.get("resident_id")
        resident_id = int(resident_id_raw) if resident_id_raw not in (None, "") else None
        shelter = str(session.get("resident_shelter") or "").strip()

        get_db()

        if shelter:
            run_pass_retention_cleanup_for_shelter(shelter)

        if resident_id is None:
            return _resident_signin_redirect()

        if request.method == "POST":
            assignment_id = _clean_text(request.form.get("assignment_id"))
            result = complete_chore(resident_id, assignment_id)

            if not result.found:
                flash("Chore assignment not found.", "error")
            elif result.already_completed:
                flash("That chore was already completed.", "ok")
            elif result.completed:
                flash("Chore marked completed.", "success")
            else:
                flash("Unable to complete that chore.", "error")

            return redirect(url_for("resident_portal.resident_chores"))

        chores = get_today_chores(resident_id)

        return render_template(
            "resident/chores.html",
            chores=chores,
            today=chi_today_str(),
        )
    except Exception as exc:
        current_app.logger.exception(
            "resident_portal_chores_failed resident_id=%s shelter=%s exception_type=%s",
            resident_id if resident_id is not None else "unknown",
            shelter or "unknown",
            type(exc).__name__,
        )
        _clear_resident_session()
        return _resident_signin_redirect()
