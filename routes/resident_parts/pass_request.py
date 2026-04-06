from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.db import db_fetchone, get_db
from core.helpers import utcnow_iso
from core.pass_rules import (
    CHICAGO_TZ,
    gh_pass_rule_box,
    is_late_standard_pass_request,
    pass_type_options,
    shared_pass_rule_box,
    use_gh_pass_form,
)
from core.rate_limit import is_rate_limited
from core.runtime import init_db


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def _load_resident_profile(resident_id: int):
    return db_fetchone(
        """
        SELECT
            id,
            shelter,
            program_level,
            phone
        FROM residents
        WHERE id = %s
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            id,
            shelter,
            program_level,
            phone
        FROM residents
        WHERE id = ?
        LIMIT 1
        """,
        (resident_id,),
    )


def _resident_value(row, key: str, index: int, default=""):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def _render_pass_form(
    *,
    shelter: str,
    resident_level: str,
    resident_phone: str,
    hour_summary,
    form_data: dict | None = None,
):
    use_gh_form = use_gh_pass_form(shelter, resident_level)
    template_name = "resident_pass_request_gh.html" if use_gh_form else "resident_pass_request.html"
    rule_box = gh_pass_rule_box(resident_level) if use_gh_form else shared_pass_rule_box(resident_level)

    return render_template(
        template_name,
        shelter=shelter,
        resident_level=resident_level,
        resident_phone=resident_phone,
        hour_summary=hour_summary,
        pass_type_options=pass_type_options(),
        rule_box=rule_box,
        form_data=form_data or {},
    )


def resident_pass_request_view():
    @require_resident
    def _inner():
        init_db()

        shelter = (session.get("resident_shelter") or "").strip()
        resident_id = session.get("resident_id")

        if not resident_id:
            flash("Resident session is incomplete. Please sign in again.", "error")
            return redirect(url_for("resident_requests.resident_signin"))

        resident_row = _load_resident_profile(int(resident_id))
        resident_level = (_resident_value(resident_row, "program_level", 2, "") or "").strip()
        resident_phone_from_db = (_resident_value(resident_row, "phone", 3, "") or "").strip()

        hour_summary = None
        if resident_id and shelter:
            try:
                hour_summary = calculate_prior_week_attendance_hours(int(resident_id), shelter)
            except Exception:
                hour_summary = None

        if request.method == "GET":
            return _render_pass_form(
                shelter=shelter,
                resident_level=resident_level,
                resident_phone=resident_phone_from_db,
                hour_summary=hour_summary,
                form_data={},
            )

        resident_identifier = (session.get("resident_identifier") or "").strip()
        first = (session.get("resident_first") or "").strip()
        last = (session.get("resident_last") or "").strip()
        resident_phone = (request.form.get("resident_phone") or resident_phone_from_db or "").strip()

        ip = _client_ip()
        rl_key = f"resident_pass_request:{ip}:{resident_identifier or 'unknown'}"
        if is_rate_limited(rl_key, limit=6, window_seconds=900):
            flash("Too many pass submissions. Please wait a few minutes and try again.", "error")
            return _render_pass_form(
                shelter=shelter,
                resident_level=resident_level,
                resident_phone=resident_phone,
                hour_summary=hour_summary,
                form_data=request.form.to_dict(),
            ), 429

        pass_type = (request.form.get("pass_type") or "").strip().lower()
        destination = (request.form.get("destination") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        resident_notes = (request.form.get("resident_notes") or "").strip()

        request_date = (request.form.get("request_date") or "").strip()
        requirements_acknowledged = (request.form.get("requirements_acknowledged") or "").strip().lower()
        requirements_not_met_explanation = (request.form.get("requirements_not_met_explanation") or "").strip()
        who_with = (request.form.get("who_with") or "").strip()
        destination_address = (request.form.get("destination_address") or "").strip()
        destination_phone = (request.form.get("destination_phone") or "").strip()
        companion_names = (request.form.get("companion_names") or "").strip()
        companion_phone_numbers = (request.form.get("companion_phone_numbers") or "").strip()
        budgeted_amount = (request.form.get("budgeted_amount") or "").strip()

        start_at_raw = (request.form.get("start_at") or "").strip()
        end_at_raw = (request.form.get("end_at") or "").strip()
        start_date_raw = (request.form.get("start_date") or "").strip()
        end_date_raw = (request.form.get("end_date") or "").strip()
        special_reason = (request.form.get("special_reason") or "").strip()

        errors: list[str] = []

        if not resident_id or not first or not last or not shelter:
            errors.append("Resident session is incomplete. Please sign in again.")

        if pass_type not in {"pass", "overnight", "special"}:
            errors.append("Select a valid pass type.")

        if not destination:
            errors.append("Destination is required.")

        if not resident_level:
            errors.append("Resident level is missing. Please contact staff.")

        if not request_date:
            errors.append("Request date is required.")

        if pass_type in {"pass", "overnight"} and requirements_acknowledged not in {"yes", "no"}:
            errors.append("Please answer whether you will meet all requirements for this pass.")

        if pass_type in {"pass", "overnight"} and requirements_acknowledged == "no" and not requirements_not_met_explanation:
            errors.append("Please explain why requirements will not be met.")

        if pass_type == "special" and not special_reason:
            errors.append("Special pass reason is required.")

        start_at_iso = None
        end_at_iso = None
        start_date_iso = None
        end_date_iso = None

        now_local = datetime.now(CHICAGO_TZ)

        if pass_type in {"pass", "overnight"}:
            if not start_at_raw or not end_at_raw:
                errors.append("Leave date and time and return date and time are required.")
            else:
                try:
                    local_start = datetime.fromisoformat(start_at_raw).replace(tzinfo=CHICAGO_TZ)
                    local_end = datetime.fromisoformat(end_at_raw).replace(tzinfo=CHICAGO_TZ)

                    if local_end <= local_start:
                        errors.append("Return time must be after leave time.")

                    if local_start < now_local:
                        errors.append("Leave time cannot be in the past.")

                    if pass_type == "pass" and local_start.date() != local_end.date():
                        errors.append("A normal Pass must begin and end on the same day.")

                    if pass_type == "overnight" and local_end.date() <= local_start.date():
                        errors.append("An Overnight Pass must return on a later day.")

                    if is_late_standard_pass_request(now_local, local_start):
                        errors.append("This request was submitted after the Monday 8:00 a.m. deadline.")

                    start_at_iso = (
                        local_start.astimezone(timezone.utc)
                        .replace(tzinfo=None)
                        .isoformat(timespec="seconds")
                    )
                    end_at_iso = (
                        local_end.astimezone(timezone.utc)
                        .replace(tzinfo=None)
                        .isoformat(timespec="seconds")
                    )
                except Exception:
                    errors.append("Invalid leave or return date and time.")
        elif pass_type == "special":
            if not start_date_raw or not end_date_raw:
                errors.append("Start date and end date are required for a Special Pass.")
            else:
                try:
                    start_date_value = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
                    end_date_value = datetime.strptime(end_date_raw, "%Y-%m-%d").date()

                    if end_date_value < start_date_value:
                        errors.append("End date cannot be earlier than start date.")

                    start_date_iso = start_date_value.isoformat()
                    end_date_iso = end_date_value.isoformat()
                except Exception:
                    errors.append("Invalid Special Pass dates.")

        if errors:
            for e in errors:
                flash(e, "error")
            return _render_pass_form(
                shelter=shelter,
                resident_level=resident_level,
                resident_phone=resident_phone,
                hour_summary=hour_summary,
                form_data=request.form.to_dict(),
            ), 400

        conn = get_db()
        kind = g.get("db_kind")
        now_iso = utcnow_iso()

        pass_sql = (
            """
            INSERT INTO resident_passes (
                resident_id,
                shelter,
                pass_type,
                status,
                start_at,
                end_at,
                start_date,
                end_date,
                destination,
                reason,
                resident_notes,
                staff_notes,
                approved_by,
                approved_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, 'pending', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """
            if kind == "pg"
            else
            """
            INSERT INTO resident_passes (
                resident_id,
                shelter,
                pass_type,
                status,
                start_at,
                end_at,
                start_date,
                end_date,
                destination,
                reason,
                resident_notes,
                staff_notes,
                approved_by,
                approved_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        )

        final_reason = special_reason if pass_type == "special" else reason

        pass_params = (
            resident_id,
            shelter,
            pass_type,
            start_at_iso,
            end_at_iso,
            start_date_iso,
            end_date_iso,
            destination,
            final_reason or None,
            resident_notes or None,
            None,
            None,
            None,
            now_iso,
            now_iso,
        )

        detail_sql = (
            """
            INSERT INTO resident_pass_request_details (
                pass_id,
                resident_phone,
                request_date,
                resident_level,
                requirements_acknowledged,
                requirements_not_met_explanation,
                reason_for_request,
                who_with,
                destination_address,
                destination_phone,
                companion_names,
                companion_phone_numbers,
                budgeted_amount,
                approved_amount,
                reviewed_by_user_id,
                reviewed_by_name,
                reviewed_at,
                created_at,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            if kind == "pg"
            else
            """
            INSERT INTO resident_pass_request_details (
                pass_id,
                resident_phone,
                request_date,
                resident_level,
                requirements_acknowledged,
                requirements_not_met_explanation,
                reason_for_request,
                who_with,
                destination_address,
                destination_phone,
                companion_names,
                companion_phone_numbers,
                budgeted_amount,
                approved_amount,
                reviewed_by_user_id,
                reviewed_by_name,
                reviewed_at,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """
        )

        cur = conn.cursor()
        try:
            cur.execute(pass_sql, pass_params)
            if kind == "pg":
                req_id = cur.fetchone()[0]
            else:
                conn.commit()
                req_id = cur.lastrowid

            detail_params = (
                req_id,
                resident_phone or None,
                request_date or None,
                resident_level or None,
                requirements_acknowledged or None,
                requirements_not_met_explanation or None,
                final_reason or None,
                who_with or None,
                destination_address or None,
                destination_phone or None,
                companion_names or None,
                companion_phone_numbers or None,
                budgeted_amount or None,
                None,
                None,
                None,
                None,
                now_iso,
                now_iso,
            )
            cur.execute(detail_sql, detail_params)

            if kind != "pg":
                conn.commit()
        finally:
            cur.close()

        log_action(
            "pass",
            req_id,
            shelter,
            None,
            "create",
            f"Resident submitted {pass_type} pass request phone={resident_phone or ''}".strip(),
        )

        flash("Your pass request was submitted successfully.", "ok")
        return redirect(url_for("resident_portal.home"))

    return _inner()
