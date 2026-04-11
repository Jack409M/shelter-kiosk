from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, g, redirect, render_template, session, url_for

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.db import db_execute, db_fetchone, db_transaction
from core.helpers import fmt_dt, fmt_pretty_date, utcnow_iso
from core.meeting_progress import calculate_meeting_progress
from core.pass_retention import cleanup_deadline_from_expected_back, run_pass_retention_cleanup_for_shelter
from core.pass_rules import pass_type_label
from core.sms_sender import send_sms
from routes.attendance_parts.helpers import can_manage_passes, complete_active_passes, to_local
from routes.attendance_parts.pass_policy import (
    build_policy_check,
    has_active_pass_block,
    load_resident_pass_profile,
    resident_value,
)
from routes.attendance_parts.pass_queries import (
    fetch_approved_pass_rows,
    fetch_current_pass_rows,
    fetch_pending_pass_rows,
)

CHICAGO_TZ = ZoneInfo("America/Chicago")


def _insert_resident_notification(
    *,
    resident_id: int,
    shelter: str,
    notification_type: str,
    title: str,
    message: str,
    related_pass_id: int | None,
) -> None:
    db_execute(
        """
        INSERT INTO resident_notifications (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, 0, %s, %s)
        """
        if g.get("db_kind") == "pg"
        else
        """
        INSERT INTO resident_notifications (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            is_read,
            created_at,
            read_at
        )
        VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?)
        """,
        (
            resident_id,
            shelter,
            notification_type,
            title,
            message,
            related_pass_id,
            utcnow_iso(),
            None,
        ),
    )


def _load_pass_sms_context(pass_id: int, shelter: str):
    return db_fetchone(
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            r.first_name,
            r.last_name,
            d.resident_phone
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        LEFT JOIN resident_pass_request_details d ON d.pass_id = rp.id
        WHERE rp.id = %s
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            r.first_name,
            r.last_name,
            d.resident_phone
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        LEFT JOIN resident_pass_request_details d ON d.pass_id = rp.id
        WHERE rp.id = ?
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )


def _build_approval_sms(pass_row: dict) -> str:
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()
    pass_type_text = pass_type_label(pass_type_key)
    first_name = str(pass_row.get("first_name") or "").strip()

    if pass_type_key in {"pass", "overnight"}:
        leave_text = fmt_pretty_date(pass_row.get("start_at"))
        return_text = fmt_pretty_date(pass_row.get("end_at"))
        return f"{pass_type_text} approved for {first_name}. Leave {leave_text}. Return {return_text}."
    start_date = str(pass_row.get("start_date") or "").strip()
    end_date = str(pass_row.get("end_date") or "").strip()
    return f"{pass_type_text} approved for {first_name}. Dates: {start_date} to {end_date}."


def staff_passes_pending_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = fetch_pending_pass_rows(str(shelter or "").strip())

    processed = []

    for row in rows:
        blocked, restriction_rows = has_active_pass_block(int(row.get("resident_id") or 0))
        row["has_disciplinary_block"] = blocked
        row["disciplinary_restrictions"] = restriction_rows
        processed.append(row)

    return render_template(
        "staff_passes_pending.html",
        rows=processed,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_approved_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = fetch_approved_pass_rows(str(shelter or "").strip())

    return render_template(
        "staff_passes_approved.html",
        rows=rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_away_now_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = fetch_current_pass_rows(str(shelter or "").strip())

    return render_template(
        "staff_passes_away_now.html",
        rows=rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_overdue_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    now_local = datetime.now(CHICAGO_TZ)
    overdue_rows: list[dict] = []

    for row in fetch_current_pass_rows(str(shelter or "").strip()):
        expected_back_local = row.get("expected_back_local")
        if expected_back_local and expected_back_local < now_local:
            overdue_rows.append(row)

    return render_template(
        "staff_passes_overdue.html",
        rows=overdue_rows,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_pass_detail_view(pass_id: int):
    shelter = session.get("shelter")

    if not can_manage_passes():
        abort(403)

    row = db_fetchone(
        """
        SELECT
            rp.id,
            rp.resident_id,
            r.first_name,
            r.last_name,
            rp.shelter,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            rp.reason,
            rp.resident_notes,
            rp.staff_notes,
            rp.created_at,
            rp.status
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.id = %s AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            r.first_name,
            r.last_name,
            rp.shelter,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            rp.reason,
            rp.resident_notes,
            rp.staff_notes,
            rp.created_at,
            rp.status
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.id = ? AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        """,
        (pass_id, shelter),
    )

    if not row:
        abort(404)

    p = dict(row)

    detail_row = db_fetchone(
        """
        SELECT
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
            reviewed_at
        FROM resident_pass_request_details
        WHERE pass_id = %s
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
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
            reviewed_at
        FROM resident_pass_request_details
        WHERE pass_id = ?
        LIMIT 1
        """,
        (pass_id,),
    )

    pass_detail = dict(detail_row) if detail_row else None

    p["start_at_local"] = to_local(p.get("start_at"))
    p["end_at_local"] = to_local(p.get("end_at"))
    p["created_at_local"] = to_local(p.get("created_at"))
    p["pass_type_label"] = pass_type_label(p.get("pass_type"))

    if pass_detail:
        pass_detail["reviewed_at_local"] = to_local(pass_detail.get("reviewed_at"))

    hour_summary = None
    try:
        hour_summary = calculate_prior_week_attendance_hours(int(p["resident_id"]), str(p["shelter"]))
    except Exception:
        hour_summary = None

    resident_profile = load_resident_pass_profile(int(p["resident_id"]))
    resident_level = ""
    sponsor_name = ""
    sponsor_active = None
    step_current = None
    step_work_active = None
    monthly_income = None
    program_start_date = None

    if resident_profile:
        resident_level = str(resident_value(resident_profile, "program_level", 2, "") or "").strip()
        sponsor_name = str(resident_value(resident_profile, "sponsor_name", 3, "") or "").strip()
        sponsor_active = resident_value(resident_profile, "sponsor_active", 4, None)
        step_current = resident_value(resident_profile, "step_current", 5, None)
        step_work_active = resident_value(resident_profile, "step_work_active", 6, None)
        monthly_income = resident_value(resident_profile, "monthly_income", 7, None)
        program_start_date = resident_value(resident_profile, "date_entered", 8, None)

    if pass_detail and pass_detail.get("resident_level"):
        resident_level = str(pass_detail.get("resident_level") or "").strip() or resident_level

    meeting_summary = None
    try:
        meeting_summary = calculate_meeting_progress(
            resident_id=int(p["resident_id"]),
            shelter=str(p["shelter"]),
            program_start_date=program_start_date,
            level_value=resident_level,
        )
    except Exception:
        meeting_summary = None

    policy_check = build_policy_check(p, pass_detail, hour_summary, meeting_summary)

    return render_template(
        "staff_pass_detail.html",
        p=p,
        pass_detail=pass_detail,
        hour_summary=hour_summary,
        meeting_summary=meeting_summary,
        resident_level=resident_level,
        sponsor_name=sponsor_name,
        sponsor_active=sponsor_active,
        step_current=step_current,
        step_work_active=step_work_active,
        monthly_income=monthly_income,
        policy_check=policy_check,
        fmt_dt=fmt_dt,
    )


def staff_pass_approve_view(pass_id: int):
    shelter = session.get("shelter")
    staff_id = session.get("staff_user_id")
    staff_name = (session.get("username") or "").strip()

    if not can_manage_passes():
        abort(403)

    pass_row = db_fetchone(
        """
        SELECT id, resident_id, shelter, status, pass_type, end_at, end_date
        FROM resident_passes
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, resident_id, shelter, status, pass_type, end_at, end_date
        FROM resident_passes
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        flash("Pass request not found.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    status = str(pass_row.get("status") or "").strip().lower()
    resident_id = int(pass_row.get("resident_id"))
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()

    if status != "pending":
        flash("That pass request is no longer pending.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    blocked, restriction_rows = has_active_pass_block(resident_id)
    if blocked:
        label = restriction_rows[0].get("restriction_label") or "disciplinary restriction"
        detail = restriction_rows[0].get("restriction_detail") or ""
        flash(f"Pass cannot be approved because resident is under {label}. {detail}".strip(), "error")
        return redirect(url_for("attendance.staff_pass_detail", pass_id=pass_id))

    now_iso = utcnow_iso()
    delete_after_at = cleanup_deadline_from_expected_back(
        pass_row.get("end_at"),
        pass_row.get("end_date"),
    )

    with db_transaction():
        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                approved_by = %s,
                approved_at = %s,
                delete_after_at = %s,
                updated_at = %s
            WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            """,
            ("approved", staff_id, now_iso, delete_after_at, now_iso, pass_id, shelter),
        )

        db_execute(
            """
            UPDATE resident_pass_request_details
            SET reviewed_by_user_id = %s,
                reviewed_by_name = %s,
                reviewed_at = %s,
                updated_at = %s
            WHERE pass_id = %s
            """,
            (staff_id, staff_name or None, now_iso, now_iso, pass_id),
        )

        _insert_resident_notification(
            resident_id=resident_id,
            shelter=str(shelter or "").strip(),
            notification_type="pass_approved",
            title=f"{pass_type_label(pass_type_key)} Approved",
            message="Your pass request was approved.",
            related_pass_id=int(pass_id),
        )

    sms_context = _load_pass_sms_context(pass_id, str(shelter or "").strip())
    if sms_context:
        phone = str(sms_context.get("resident_phone") or "").strip()
        if phone:
            try:
                send_sms(phone, _build_approval_sms(sms_context))
            except Exception:
                pass

    log_action("pass", resident_id, shelter, staff_id, "approve", f"pass_id={pass_id}")
    flash("Pass request approved.", "ok")
    return redirect(url_for("attendance.staff_passes_pending"))


def staff_pass_deny_view(pass_id: int):
    shelter = session.get("shelter")
    staff_id = session.get("staff_user_id")
    staff_name = (session.get("username") or "").strip()

    if not can_manage_passes():
        abort(403)

    pass_row = db_fetchone(
        """
        SELECT id, resident_id, shelter, status, pass_type
        FROM resident_passes
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, resident_id, shelter, status, pass_type
        FROM resident_passes
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        flash("Pass request not found.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    status = str(pass_row.get("status") or "").strip().lower()
    resident_id = int(pass_row.get("resident_id"))
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()

    if status != "pending":
        flash("That pass request is no longer pending.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    now_iso = utcnow_iso()

    with db_transaction():
        db_execute(
            """
            UPDATE resident_passes
            SET status = %s,
                approved_by = %s,
                approved_at = %s,
                updated_at = %s
            WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
            """,
            ("denied", staff_id, now_iso, now_iso, pass_id, shelter),
        )

        db_execute(
            """
            UPDATE resident_pass_request_details
            SET reviewed_by_user_id = %s,
                reviewed_by_name = %s,
                reviewed_at = %s,
                updated_at = %s
            WHERE pass_id = %s
            """,
            (staff_id, staff_name or None, now_iso, now_iso, pass_id),
        )

        _insert_resident_notification(
            resident_id=resident_id,
            shelter=str(shelter or "").strip(),
            notification_type="pass_denied",
            title=f"{pass_type_label(pass_type_key)} Denied",
            message="Your pass request was denied.",
            related_pass_id=int(pass_id),
        )

    log_action("pass", resident_id, shelter, staff_id, "deny", f"pass_id={pass_id}")
    flash("Pass request denied.", "ok")
    return redirect(url_for("attendance.staff_passes_pending"))


def staff_pass_check_in_view(pass_id: int):
    shelter = session.get("shelter")
    staff_id = session.get("staff_user_id")

    if not can_manage_passes():
        abort(403)

    pass_row = db_fetchone(
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.status,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.id = %s
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.status,
            rp.pass_type,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.id = ?
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        flash("Pass not found.", "error")
        return redirect(url_for("attendance.staff_passes_away_now"))

    resident_id = int(pass_row["resident_id"])
    status = str(pass_row.get("status") or "").strip().lower()

    if status != "approved":
        flash("Only approved passes can be checked back in.", "error")
        return redirect(url_for("attendance.staff_passes_away_now"))

    db_execute(
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
            is_recovery_meeting
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """,
        (
            resident_id,
            shelter,
            "check_in",
            utcnow_iso(),
            staff_id,
            "Pass return check in",
            None,
            None,
            None,
            None,
            0,
            None,
            None,
            0,
        ),
    )

    complete_active_passes(resident_id, str(shelter or "").strip())

    log_action("pass", resident_id, shelter, staff_id, "check_in", f"pass_id={pass_id}")
    flash("Resident checked in from pass.", "ok")
    return redirect(url_for("attendance.staff_passes_away_now"))
