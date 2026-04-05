from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import flash, g, redirect, render_template, request, session, url_for

from core.access import require_resident
from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.db import get_db
from core.helpers import utcnow_iso
from core.rate_limit import is_rate_limited
from core.runtime import init_db


def _client_ip() -> str:
    return (request.remote_addr or "").strip() or "unknown"


def _normalize_pass_type(value: str | None) -> str:
    raw = (value or "").strip().lower()
    if raw == "extended_special":
        return "extended_special"
    return "ordinary"


def resident_pass_request_view():
    @require_resident
    def _inner():
        init_db()

        shelter = (session.get("resident_shelter") or "").strip()
        resident_id = session.get("resident_id")

        hour_summary = None
        if resident_id and shelter:
            try:
                hour_summary = calculate_prior_week_attendance_hours(int(resident_id), shelter)
            except Exception:
                hour_summary = None

        if request.method == "GET":
            return render_template(
                "resident_pass_request.html",
                shelter=shelter,
                hour_summary=hour_summary,
            )

        resident_identifier = (session.get("resident_identifier") or "").strip()
        first = (session.get("resident_first") or "").strip()
        last = (session.get("resident_last") or "").strip()
        resident_phone = (request.form.get("resident_phone") or session.get("resident_phone") or "").strip()

        ip = _client_ip()
        rl_key = f"resident_pass_request:{ip}:{resident_identifier or 'unknown'}"
        if is_rate_limited(rl_key, limit=6, window_seconds=900):
            flash("Too many pass submissions. Please wait a few minutes and try again.", "error")
            return render_template(
                "resident_pass_request.html",
                shelter=shelter,
                hour_summary=hour_summary,
            ), 429

        pass_type = _normalize_pass_type(request.form.get("pass_type"))
        destination = (request.form.get("destination") or "").strip()
        reason = (request.form.get("reason") or "").strip()
        resident_notes = (request.form.get("resident_notes") or "").strip()

        request_date = (request.form.get("request_date") or "").strip()
        resident_level = (request.form.get("resident_level") or "").strip()
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

        errors: list[str] = []

        if not resident_id or not first or not last or not shelter:
            errors.append("Resident session is incomplete. Please sign in again.")

        if not destination:
            errors.append("Destination is required.")

        if resident_level not in {"Level 1", "Level 2", "Level 3", "Level 4"}:
            errors.append("Resident level is required.")

        if requirements_acknowledged not in {"yes", "no"}:
            errors.append("Please answer whether you will meet all requirements for this pass.")

        if requirements_acknowledged == "no" and not requirements_not_met_explanation:
            errors.append("Please explain why requirements will not be met.")

        ordinary_start_iso = None
        ordinary_end_iso = None
        extended_start_date = None
        extended_end_date = None

        if pass_type == "ordinary":
            if not start_at_raw or not end_at_raw:
                errors.append("Start time and end time are required for an ordinary pass.")
            else:
                try:
                    local_start = datetime.fromisoformat(start_at_raw).replace(
                        tzinfo=ZoneInfo("America/Chicago")
                    )
                    local_end = datetime.fromisoformat(end_at_raw).replace(
                        tzinfo=ZoneInfo("America/Chicago")
                    )

                    utc_start = local_start.astimezone(timezone.utc).replace(tzinfo=None)
                    utc_end = local_end.astimezone(timezone.utc).replace(tzinfo=None)

                    if utc_end <= utc_start:
                        errors.append("End time must be after start time.")

                    if utc_start < datetime.utcnow() - timedelta(minutes=1):
                        errors.append("Start time cannot be in the past.")

                    ordinary_start_iso = utc_start.replace(microsecond=0).isoformat()
                    ordinary_end_iso = utc_end.replace(microsecond=0).isoformat()
                except Exception:
                    errors.append("Invalid ordinary pass date or time.")
        else:
            if not start_date_raw or not end_date_raw:
                errors.append("Start date and end date are required for an extended pass.")
            else:
                try:
                    start_date = datetime.strptime(start_date_raw, "%Y-%m-%d").date()
                    end_date = datetime.strptime(end_date_raw, "%Y-%m-%d").date()

                    if end_date < start_date:
                        errors.append("End date cannot be earlier than start date.")

                    extended_start_date = start_date.isoformat()
                    extended_end_date = end_date.isoformat()
                except Exception:
                    errors.append("Invalid extended pass date.")

        if errors:
            for e in errors:
                flash(e, "error")
            return render_template(
                "resident_pass_request.html",
                shelter=shelter,
                hour_summary=hour_summary,
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
            else """
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

        pass_params = (
            resident_id,
            shelter,
            pass_type,
            ordinary_start_iso,
            ordinary_end_iso,
            extended_start_date,
            extended_end_date,
            destination,
            reason or None,
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
            else """
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
                reason or None,
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
