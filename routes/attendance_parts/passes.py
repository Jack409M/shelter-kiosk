from __future__ import annotations

from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from flask import abort, flash, g, redirect, render_template, session, url_for

from core.attendance_hours import calculate_prior_week_attendance_hours
from core.audit import log_action
from core.db import db_execute, db_fetchall, db_fetchone, db_transaction
from core.helpers import fmt_dt, fmt_pretty_date, utcnow_iso
from core.pass_retention import cleanup_deadline_from_expected_back, run_pass_retention_cleanup_for_shelter
from core.pass_rules import (
    gh_pass_rule_box,
    load_pass_settings_for_shelter,
    pass_required_hours,
    pass_type_label,
    shared_pass_rule_box,
    standard_pass_deadline_for_leave,
    use_gh_pass_form,
)
from core.sms_sender import send_sms
from routes.attendance_parts.helpers import can_manage_passes, complete_active_passes, to_local

CHICAGO_TZ = ZoneInfo("America/Chicago")


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


def _deadline_detail_text(deadline_local, settings: dict) -> str:
    weekday_lookup = {
        0: "Monday",
        1: "Tuesday",
        2: "Wednesday",
        3: "Thursday",
        4: "Friday",
        5: "Saturday",
        6: "Sunday",
    }
    weekday_name = weekday_lookup.get(settings.get("pass_deadline_weekday", 0), "Monday")
    time_label = deadline_local.strftime("%I:%M %p").lstrip("0")
    return f"Configured deadline is {weekday_name} at {time_label}. Actual deadline for this pass was {deadline_local.strftime('%B %d, %Y %I:%M %p')}."


def _end_of_day_utc_naive(date_text: str | None) -> str | None:
    raw = (date_text or "").strip()
    if not raw:
        return None
    try:
        local_dt = datetime.combine(
            datetime.fromisoformat(raw).date(),
            time(hour=23, minute=59, second=59),
            tzinfo=CHICAGO_TZ,
        )
        return (
            local_dt.astimezone(timezone.utc)
            .replace(tzinfo=None)
            .isoformat(timespec="seconds")
        )
    except Exception:
        return None


def _build_policy_check(pass_row: dict, pass_detail: dict | None, hour_summary):
    resident_id = int(pass_row.get("resident_id") or 0)
    resident_profile = _load_resident_pass_profile(resident_id) if resident_id else None

    resident_level = ""
    if pass_detail and pass_detail.get("resident_level"):
        resident_level = str(pass_detail.get("resident_level") or "").strip()
    elif resident_profile:
        resident_level = str(_resident_value(resident_profile, "program_level", 2, "") or "").strip()

    shelter = str(pass_row.get("shelter") or "").strip()
    settings = load_pass_settings_for_shelter(shelter)
    required_hours = pass_required_hours(shelter)
    use_gh = use_gh_pass_form(shelter, resident_level)

    rule_box = gh_pass_rule_box(shelter, resident_level) if use_gh else shared_pass_rule_box(shelter, resident_level)
    pass_type_key = str(pass_row.get("pass_type") or "").strip().lower()
    pass_type_text = pass_type_label(pass_type_key)

    checks: list[dict] = []

    if pass_type_key in {"pass", "overnight"}:
        start_local = pass_row.get("start_at_local")
        if start_local:
            deadline_local = standard_pass_deadline_for_leave(start_local, shelter=shelter)
            created_local = pass_row.get("created_at_local")
            submitted_on_time = bool(created_local and created_local <= deadline_local)

            checks.append(
                {
                    "label": "Deadline",
                    "value": "On time" if submitted_on_time else "Late",
                    "status_class": "pass" if submitted_on_time else "fail",
                    "detail": _deadline_detail_text(deadline_local, settings),
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
                    "detail": "Pass should leave and return on the same day.",
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
            productive_required = required_hours.get("productive_required_hours", 35)
            work_required = required_hours.get("work_required_hours", 29)
            productive_hours = hour_summary.get("productive_hours", 0)
            work_hours = hour_summary.get("work_hours", 0)

            meets_hours = (productive_hours >= productive_required) and (work_hours >= work_required)

            checks.append(
                {
                    "label": "Previous week hours",
                    "value": "Meets configured hours" if meets_hours else "Below configured hours",
                    "status_class": "pass" if meets_hours else "fail",
                    "detail": (
                        f"Productive {productive_hours} / {productive_required}"
                        f" • Work {work_hours} / {work_required}"
                    ),
                }
            )

    if pass_type_key == "special":
        checks.append(
            {
                "label": "Special pass handling",
                "value": "Exception review",
                "status_class": "pass",
                "detail": "Special Pass is reviewed under the configured special pass rules.",
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


def _latest_checkout_type_map_for_shelter(shelter: str) -> dict[int, str]:
    rows = db_fetchall(
        """
        SELECT resident_id, event_type
        FROM (
            SELECT
                resident_id,
                event_type,
                ROW_NUMBER() OVER (
                    PARTITION BY resident_id
                    ORDER BY event_time DESC, id DESC
                ) AS rn
            FROM attendance_events
            WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(%s))
        ) x
        WHERE rn = 1
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT resident_id, event_type
        FROM (
            SELECT
                resident_id,
                event_type,
                ROW_NUMBER() OVER (
                    PARTITION BY resident_id
                    ORDER BY event_time DESC, id DESC
                ) AS rn
            FROM attendance_events
            WHERE LOWER(TRIM(COALESCE(shelter, ''))) = LOWER(TRIM(?))
        ) x
        WHERE rn = 1
        """,
        (shelter,),
    )
    result: dict[int, str] = {}
    for row in rows:
        result[int(row["resident_id"])] = str(row["event_type"] or "")
    return result


def _current_pass_rows(shelter: str) -> list[dict]:
    now_iso = utcnow_iso()
    today_iso = now_iso[:10]

    rows = db_fetchall(
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.pass_type,
            rp.status,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            rp.reason,
            rp.created_at,
            rp.approved_at,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(%s))
          AND (
                (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= %s AND rp.end_at >= %s)
             OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= %s AND rp.end_date >= %s)
          )
        ORDER BY
            COALESCE(rp.end_at, %s) ASC,
            COALESCE(rp.end_date, %s) ASC,
            rp.created_at ASC
        """
        if g.get("db_kind") == "pg"
        else
        """
        SELECT
            rp.id,
            rp.resident_id,
            rp.shelter,
            rp.pass_type,
            rp.status,
            rp.start_at,
            rp.end_at,
            rp.start_date,
            rp.end_date,
            rp.destination,
            rp.reason,
            rp.created_at,
            rp.approved_at,
            r.first_name,
            r.last_name
        FROM resident_passes rp
        JOIN residents r ON r.id = rp.resident_id
        WHERE rp.status = 'approved'
          AND LOWER(TRIM(rp.shelter)) = LOWER(TRIM(?))
          AND (
                (rp.start_at IS NOT NULL AND rp.end_at IS NOT NULL AND rp.start_at <= ? AND rp.end_at >= ?)
             OR (rp.start_date IS NOT NULL AND rp.end_date IS NOT NULL AND rp.start_date <= ? AND rp.end_date >= ?)
          )
        ORDER BY
            COALESCE(rp.end_at, ?) ASC,
            COALESCE(rp.end_date, ?) ASC,
            rp.created_at ASC
        """,
        (shelter, now_iso, now_iso, today_iso, today_iso, now_iso, today_iso),
    )

    latest_event_map = _latest_checkout_type_map_for_shelter(shelter)
    processed: list[dict] = []

    for row in rows:
        item = dict(row)
        latest_event_type = (latest_event_map.get(int(item["resident_id"])) or "").strip().lower()
        if latest_event_type != "check_out":
            continue

        item["start_at_local"] = to_local(item.get("start_at"))
        item["end_at_local"] = to_local(item.get("end_at"))
        item["created_at_local"] = to_local(item.get("created_at"))
        item["approved_at_local"] = to_local(item.get("approved_at"))
        item["pass_type_label"] = pass_type_label(item.get("pass_type"))

        if item.get("end_at"):
            expected_back_iso = str(item.get("end_at") or "").strip()
        else:
            expected_back_iso = _end_of_day_utc_naive(item.get("end_date"))

        item["expected_back_at"] = expected_back_iso
        item["expected_back_local"] = to_local(expected_back_iso)

        processed.append(item)

    return processed


def staff_passes_pending_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
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
        row = dict(r)
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
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
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
        row = dict(r)
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


def staff_passes_away_now_view():
    shelter = session.get("shelter")
    run_pass_retention_cleanup_for_shelter(str(shelter or "").strip())
    role = session.get("role")

    if role not in {"admin", "shelter_director", "case_manager"}:
        abort(403)

    rows = _current_pass_rows(str(shelter or "").strip())

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

    for row in _current_pass_rows(str(shelter or "").strip()):
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
            obligation_end_time
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
        ),
    )

    complete_active_passes(resident_id, str(shelter or "").strip())

    log_action("pass", resident_id, shelter, staff_id, "check_in", f"pass_id={pass_id}")
    flash("Resident checked in from pass.", "ok")
    return redirect(url_for("attendance.staff_passes_away_now"))
