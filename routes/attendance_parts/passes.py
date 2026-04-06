from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from flask import abort, flash, g, redirect, render_template, session, url_for

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_dt, utcnow_iso
from core.pass_rules import (
    CHICAGO_TZ,
    gh_pass_rule_box,
    pass_type_label,
    shared_pass_rule_box,
    standard_pass_deadline_for_leave,
    use_gh_pass_form,
)
from routes.attendance_parts.helpers import can_manage_passes, to_local


def _resident_value(row, key: str, index: int, default=""):
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[index]
    except Exception:
        return default


def _load_resident_pass_profile(resident_id: int):
    return db_fetchone(
        """
        SELECT
            id,
            shelter,
            program_level
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
            program_level
        FROM residents
        WHERE id = ?
        LIMIT 1
        """,
        (resident_id,),
    )


def _build_policy_check(pass_row: dict, pass_detail: dict | None, hour_summary):
    resident_id = int(pass_row.get("resident_id") or 0)
    resident_profile = _load_resident_pass_profile(resident_id) if resident_id else None

    resident_level = ""
    if pass_detail and pass_detail.get("resident_level"):
        resident_level = str(pass_detail.get("resident_level") or "").strip()
    elif resident_profile:
        resident_level = str(_resident_value(resident_profile, "program_level", 2, "") or "").strip()

    shelter = str(pass_row.get("shelter") or "").strip()
    use_gh = use_gh_pass_form(shelter, resident_level)

    rule_box = gh_pass_rule_box(resident_level) if use_gh else shared_pass_rule_box(resident_level)
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()
    pass_type_text = pass_type_label(pass_type_key)

    checks: list[dict] = []

    if pass_type_key in {"pass", "overnight"}:
        start_local = pass_row.get("start_at_local")
        if start_local:
            deadline_local = standard_pass_deadline_for_leave(start_local)
            created_local = pass_row.get("created_at_local")
            submitted_on_time = bool(created_local and created_local <= deadline_local)

            checks.append(
                {
                    "label": "Deadline",
                    "value": "On time" if submitted_on_time else "Late",
                    "status_class": "pass" if submitted_on_time else "fail",
                    "detail": f"Deadline was {deadline_local.strftime('%B %d, %Y %I:%M %p')}",
                }
            )

        if pass_type_key == "pass":
            same_day = bool(
                pass_row.get("start_at_local")
                and pass_row.get("end_at_local")
                and pass_row["start_at_local"].date() == pass_row["end_at_local"].date()
            )
            checks.append(
                {
                    "label": "Pass timing",
                    "value": "Same day" if same_day else "Not same day",
                    "status_class": "pass" if same_day else "fail",
                    "detail": "Normal Pass should leave and return on the same day.",
                }
            )

        if pass_type_key == "overnight":
            overnight_ok = bool(
                pass_row.get("start_at_local")
                and pass_row.get("end_at_local")
                and pass_row["end_at_local"].date() > pass_row["start_at_local"].date()
            )
            checks.append(
                {
                    "label": "Overnight timing",
                    "value": "Overnight" if overnight_ok else "Not overnight",
                    "status_class": "pass" if overnight_ok else "fail",
                    "detail": "Overnight Pass should return on a later day.",
                }
            )

        requirements_ack = (pass_detail or {}).get("requirements_acknowledged")
        if requirements_ack:
            checks.append(
                {
                    "label": "Resident said obligations will be met",
                    "value": "Yes" if requirements_ack == "yes" else "No",
                    "status_class": "pass" if requirements_ack == "yes" else "fail",
                    "detail": (pass_detail or {}).get("requirements_not_met_explanation") or "",
                }
            )

        if hour_summary:
            checks.append(
                {
                    "label": "Previous week hours",
                    "value": hour_summary.get("status_label", ""),
                    "status_class": hour_summary.get("status_class", "fail"),
                    "detail": (
                        f"Productive {hour_summary.get('productive_hours', 0)} / {hour_summary.get('productive_required_hours', 0)}"
                        f" • Work {hour_summary.get('work_hours', 0)} / {hour_summary.get('work_required_hours', 0)}"
                    ),
                }
            )

    if pass_type_key == "special":
        checks.append(
            {
                "label": "Special pass handling",
                "value": "Exception review",
                "status_class": "pass",
                "detail": "Special Pass is for funerals or similar serious situations.",
            }
        )

    title = "Gratitude House Policy Check" if use_gh else "Pass Policy Check"

    return {
        "title": title,
        "resident_level": resident_level or "Not Set",
        "pass_type_label": pass_type_text,
        "rule_lines": rule_box.get("lines", []),
        "checks": checks,
    }


def staff_passes_pending_view():
    shelter = session.get("shelter")
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    sql = (
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
            rp.created_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'pending'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        ORDER BY rp.created_at ASC
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
            rp.created_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'pending'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        ORDER BY rp.created_at ASC
        """
    )

    rows = db_fetchall(sql, (shelter,))

    processed = []

    for r in rows:
        row = dict(r) if isinstance(r, dict) else {
            "id": r[0],
            "resident_id": r[1],
            "first_name": r[2],
            "last_name": r[3],
            "shelter": r[4],
            "pass_type": r[5],
            "start_at": r[6],
            "end_at": r[7],
            "start_date": r[8],
            "end_date": r[9],
            "destination": r[10],
            "reason": r[11],
            "created_at": r[12],
        }

        row["start_at_local"] = to_local(row.get("start_at"))
        row["end_at_local"] = to_local(row.get("end_at"))
        row["created_at_local"] = to_local(row.get("created_at"))
        row["pass_type_label"] = pass_type_label(row.get("pass_type"))

        processed.append(row)

    return render_template(
        "staff_passes_pending.html",
        rows=processed,
        shelter=shelter,
        fmt_dt=fmt_dt,
    )


def staff_passes_approved_view():
    shelter = session.get("shelter")
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    sql = (
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
            rp.created_at,
            rp.approved_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
        ORDER BY rp.approved_at ASC, rp.created_at ASC
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
            rp.created_at,
            rp.approved_at
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
        AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
        ORDER BY rp.approved_at ASC, rp.created_at ASC
        """
    )

    rows = db_fetchall(sql, (shelter,))

    processed = []

    for r in rows:
        row = dict(r) if isinstance(r, dict) else {
            "id": r[0],
            "resident_id": r[1],
            "first_name": r[2],
            "last_name": r[3],
            "shelter": r[4],
            "pass_type": r[5],
            "start_at": r[6],
            "end_at": r[7],
            "start_date": r[8],
            "end_date": r[9],
            "destination": r[10],
            "reason": r[11],
            "created_at": r[12],
            "approved_at": r[13],
        }

        row["start_at_local"] = to_local(row.get("start_at"))
        row["end_at_local"] = to_local(row.get("end_at"))
        row["created_at_local"] = to_local(row.get("created_at"))
        row["approved_at_local"] = to_local(row.get("approved_at"))
        row["pass_type_label"] = pass_type_label(row.get("pass_type"))

        processed.append(row)

    return render_template(
        "staff_passes_approved.html",
        rows=processed,
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

    p = dict(row) if isinstance(row, dict) else {
        "id": row[0],
        "resident_id": row[1],
        "first_name": row[2],
        "last_name": row[3],
        "shelter": row[4],
        "pass_type": row[5],
        "start_at": row[6],
        "end_at": row[7],
        "start_date": row[8],
        "end_date": row[9],
        "destination": row[10],
        "reason": row[11],
        "resident_notes": row[12],
        "staff_notes": row[13],
        "created_at": row[14],
        "status": row[15],
    }

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

    pass_detail = (
        dict(detail_row) if isinstance(detail_row, dict) else {
            "resident_phone": detail_row[0],
            "request_date": detail_row[1],
            "resident_level": detail_row[2],
            "requirements_acknowledged": detail_row[3],
            "requirements_not_met_explanation": detail_row[4],
            "reason_for_request": detail_row[5],
            "who_with": detail_row[6],
            "destination_address": detail_row[7],
            "destination_phone": detail_row[8],
            "companion_names": detail_row[9],
            "companion_phone_numbers": detail_row[10],
            "budgeted_amount": detail_row[11],
            "approved_amount": detail_row[12],
            "reviewed_by_user_id": detail_row[13],
            "reviewed_by_name": detail_row[14],
            "reviewed_at": detail_row[15],
        }
        if detail_row else None
    )

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

    policy_check = _build_policy_check(p, pass_detail, hour_summary)

    return render_template(
        "staff_pass_detail.html",
        p=p,
        pass_detail=pass_detail,
        hour_summary=hour_summary,
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
        SELECT id, resident_id, shelter, status
        FROM resident_passes
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, resident_id, shelter, status
        FROM resident_passes
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        flash("Pass request not found.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    status = pass_row["status"] if isinstance(pass_row, dict) else pass_row[3]
    resident_id = pass_row["resident_id"] if isinstance(pass_row, dict) else pass_row[1]

    if status != "pending":
        flash("That pass request is no longer pending.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    now_iso = utcnow_iso()

    db_execute(
        """
        UPDATE resident_passes
        SET status = %s,
            approved_by = %s,
            approved_at = %s,
            updated_at = %s
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE resident_passes
        SET status = ?,
            approved_by = ?,
            approved_at = ?,
            updated_at = ?
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        """,
        ("approved", staff_id, now_iso, now_iso, pass_id, shelter),
    )

    db_execute(
        """
        UPDATE resident_pass_request_details
        SET reviewed_by_user_id = %s,
            reviewed_by_name = %s,
            reviewed_at = %s,
            updated_at = %s
        WHERE pass_id = %s
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE resident_pass_request_details
        SET reviewed_by_user_id = ?,
            reviewed_by_name = ?,
            reviewed_at = ?,
            updated_at = ?
        WHERE pass_id = ?
        """,
        (staff_id, staff_name or None, now_iso, now_iso, pass_id),
    )

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
        SELECT id, resident_id, shelter, status
        FROM resident_passes
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        LIMIT 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT id, resident_id, shelter, status
        FROM resident_passes
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
        LIMIT 1
        """,
        (pass_id, shelter),
    )

    if not pass_row:
        flash("Pass request not found.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    status = pass_row["status"] if isinstance(pass_row, dict) else pass_row[3]
    resident_id = pass_row["resident_id"] if isinstance(pass_row, dict) else pass_row[1]

    if status != "pending":
        flash("That pass request is no longer pending.", "error")
        return redirect(url_for("attendance.staff_passes_pending"))

    now_iso = utcnow_iso()

    db_execute(
        """
        UPDATE resident_passes
        SET status = %s,
            approved_by = %s,
            approved_at = %s,
            updated_at = %s
        WHERE id = %s AND LOWER(TRIM(shelter)) = LOWER(TRIM(%s))
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE resident_passes
        SET status = ?,
            approved_by = ?,
            approved_at = ?,
            updated_at = ?
        WHERE id = ? AND LOWER(TRIM(shelter)) = LOWER(TRIM(?))
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
        """
        if g.get("db_kind") == "pg"
        else
        """
        UPDATE resident_pass_request_details
        SET reviewed_by_user_id = ?,
            reviewed_by_name = ?,
            reviewed_at = ?,
            updated_at = ?
        WHERE pass_id = ?
        """,
        (staff_id, staff_name or None, now_iso, now_iso, pass_id),
    )

    log_action("pass", resident_id, shelter, staff_id, "deny", f"pass_id={pass_id}")
    flash("Pass request denied.", "ok")
    return redirect(url_for("attendance.staff_passes_pending"))
