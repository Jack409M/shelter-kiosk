from __future__ import annotations

from datetime import timezone
from typing import Any
from zoneinfo import ZoneInfo

from flask import abort, g, render_template, request, session

from core.db import db_fetchall, db_fetchone
from core.helpers import fmt_dt, fmt_time_only, utcnow_iso
from core.residents import has_active_pass
from routes.attendance_parts.helpers import parse_dt


def staff_attendance_resident_print_view(resident_id: int):
    shelter = session["shelter"]

    start = (request.args.get("start") or "").strip()
    end = (request.args.get("end") or "").strip()

    resident = db_fetchone(
        "SELECT first_name, last_name FROM residents WHERE id = %s AND shelter = %s"
        if g.get("db_kind") == "pg"
        else "SELECT first_name, last_name FROM residents WHERE id = ? AND shelter = ?",
        (resident_id, shelter),
    )

    if not resident:
        abort(404)

    first = resident["first_name"] if isinstance(resident, dict) else resident[0]
    last = resident["last_name"] if isinstance(resident, dict) else resident[1]

    resident_name = f"{last}, {first}"

    params = [resident_id, shelter]
    date_filter = ""

    if start:
        date_filter += " AND ae.event_time >= %s" if g.get("db_kind") == "pg" else " AND ae.event_time >= ?"
        params.append(start + "T00:00:00")

    if end:
        date_filter += " AND ae.event_time <= %s" if g.get("db_kind") == "pg" else " AND ae.event_time <= ?"
        params.append(end + "T23:59:59")

    events_raw = db_fetchall(
        f"""
        SELECT
            ae.event_type,
            ae.event_time,
            ae.note,
            ae.expected_back_time,
            su.username
        FROM attendance_events ae
        LEFT JOIN staff_users su ON su.id = ae.staff_user_id
        WHERE ae.resident_id = {"%s" if g.get("db_kind") == "pg" else "?"}
        AND ae.shelter = {"%s" if g.get("db_kind") == "pg" else "?"}
        {date_filter}
        ORDER BY ae.event_time ASC, ae.id ASC
        """,
        tuple(params),
    )

    def local_day(dt_iso):
        try:
            dt = parse_dt(dt_iso).replace(tzinfo=timezone.utc)
            return dt.astimezone(ZoneInfo("America/Chicago")).strftime("%Y-%m-%d")
        except Exception:
            return dt_iso[:10]

    events = []
    last_checkout = None

    for e in events_raw:
        event_type = e["event_type"] if isinstance(e, dict) else e[0]
        event_time = e["event_time"] if isinstance(e, dict) else e[1]
        note = e["note"] if isinstance(e, dict) else e[2]
        expected_back = e["expected_back_time"] if isinstance(e, dict) else e[3]
        staff = e["username"] if isinstance(e, dict) else e[4]

        if event_type == "check_out":
            last_checkout = {
                "checked_out_at": event_time,
                "expected_back_at": expected_back,
                "note": note,
                "out_staff": staff or "",
            }
            continue

        if event_type == "check_in" and last_checkout:
            late = None
            if last_checkout["expected_back_at"]:
                try:
                    late = parse_dt(event_time) > parse_dt(last_checkout["expected_back_at"])
                except Exception:
                    pass

            events.append({
                "date": local_day(event_time),
                "checked_out_at": last_checkout["checked_out_at"],
                "expected_back_at": last_checkout["expected_back_at"],
                "checked_in_at": event_time,
                "late": late,
                "note": last_checkout["note"],
                "out_staff": last_checkout["out_staff"],
                "in_staff": staff or "",
            })

            last_checkout = None

    return render_template(
        "staff_attendance_resident_print.html",
        resident_id=resident_id,
        resident_name=resident_name,
        shelter=shelter,
        start=start,
        end=end,
        events=events,
        fmt_dt=fmt_time_only,
        printed_on=fmt_dt(utcnow_iso()),
    )


def staff_attendance_print_today_view():
    shelter = session["shelter"]

    rows = db_fetchall(
        """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            ae.event_type,
            ae.event_time,
            ae.expected_back_time,
            ae.note,
            su.username
        FROM residents r
        LEFT JOIN attendance_events ae
            ON ae.id = (
                SELECT ae2.id
                FROM attendance_events ae2
                WHERE ae2.resident_id = r.id
                  AND ae2.shelter = r.shelter
                ORDER BY ae2.event_time DESC, ae2.id DESC
                LIMIT 1
            )
        LEFT JOIN staff_users su
            ON su.id = ae.staff_user_id
        WHERE r.shelter = %s
        ORDER BY r.last_name, r.first_name, r.id
        """
        if g.get("db_kind") == "pg"
        else """
        SELECT
            r.id,
            r.first_name,
            r.last_name,
            ae.event_type,
            ae.event_time,
            ae.expected_back_time,
            ae.note,
            su.username
        FROM residents r
        LEFT JOIN attendance_events ae
            ON ae.id = (
                SELECT ae2.id
                FROM attendance_events ae2
                WHERE ae2.resident_id = r.id
                  AND ae2.shelter = r.shelter
                ORDER BY ae2.event_time DESC, ae2.id DESC
                LIMIT 1
            )
        LEFT JOIN staff_users su
            ON su.id = ae.staff_user_id
        WHERE r.shelter = ?
        ORDER BY r.last_name, r.first_name, r.id
        """,
        (shelter,),
    )

    residents: list[dict[str, Any]] = []

    for r in rows:
        rid = r["id"] if isinstance(r, dict) else r[0]
        first = r["first_name"] if isinstance(r, dict) else r[1]
        last = r["last_name"] if isinstance(r, dict) else r[2]
        event_type = r["event_type"] if isinstance(r, dict) else r[3]
        event_time = r["event_time"] if isinstance(r, dict) else r[4]
        expected = r["expected_back_time"] if isinstance(r, dict) else r[5]
        note = r["note"] if isinstance(r, dict) else r[6]
        staff = r["username"] if isinstance(r, dict) else r[7]

        residents.append(
            {
                "name": f"{last}, {first}",
                "status": "OUT" if event_type == "check_out" else "IN",
                "out_time": event_time if event_type == "check_out" else None,
                "expected": expected if event_type == "check_out" else None,
                "staff": (staff or "") if event_type == "check_out" else "",
                "note": (note or "") if event_type == "check_out" else "",
                "has_active_pass": has_active_pass(rid, shelter),
            }
        )

    return render_template(
        "staff_attendance_today_print.html",
        residents=residents,
        shelter=shelter,
        printed_on=fmt_dt(utcnow_iso()),
        fmt_dt=fmt_time_only,
    )
