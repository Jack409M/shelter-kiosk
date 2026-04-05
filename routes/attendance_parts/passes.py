from __future__ import annotations

from flask import abort, flash, g, redirect, render_template, session, url_for

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.db import db_execute, db_fetchall, db_fetchone
from core.helpers import fmt_dt, utcnow_iso
from routes.attendance_parts.helpers import can_manage_passes, to_local


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
        else """
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
        else """
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
        else """
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
        else """
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

    if pass_detail:
        pass_detail["reviewed_at_local"] = to_local(pass_detail.get("reviewed_at"))

    hour_summary = None
    try:
        hour_summary = calculate_prior_week_attendance_hours(int(p["resident_id"]), str(p["shelter"]))
    except Exception:
        hour_summary = None

    return render_template(
        "staff_pass_detail.html",
        p=p,
        pass_detail=pass_detail,
        hour_summary=hour_summary,
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
        else """
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
        else """
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
        else """
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
        else """
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
        else """
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
        else """
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
