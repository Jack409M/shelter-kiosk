from __future__ import annotations

from flask import abort, flash, g, redirect, render_template, request, session, url_for

from core.audit import log_action
from core.db import db_execute
from core.demo_seed import clear_demo_seed, get_demo_seed_counts, run_demo_seed
from core.runtime import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db
from routes.admin_parts.helpers import require_admin_role as _require_admin


# ------------------------------------------------------------
# Dangerous Admin System Operations
# ------------------------------------------------------------
# These routes perform destructive or high impact database work.
# ------------------------------------------------------------


def _confirm_phrase_valid(expected: str) -> bool:
    entered = (request.form.get("confirm_phrase") or "").strip()
    return entered == expected


def _require_dangerous_admin_access():
    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    return None


def admin_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    init_db()
    counts = get_demo_seed_counts()

    return render_template(
        "admin_demo_data.html",
        demo_counts=counts,
        dangerous_routes_enabled=ENABLE_DANGEROUS_ADMIN_ROUTES,
    )


def seed_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("SEED DEMO DATA"):
        flash("Confirmation phrase did not match.", "error")
        return redirect(url_for("admin.admin_demo_data"))

    init_db()

    try:
        result = run_demo_seed(per_shelter=10, weeks=12)
    except Exception as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_demo_data"))

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "seed_demo_data",
        (
            f"resident_count={result.get('resident_count', 0)}\n"
            f"weeks_per_resident={result.get('weeks_per_resident', 0)}"
        ),
    )

    flash(
        f"Demo data created. Added {result.get('resident_count', 0)} residents.",
        "ok",
    )
    return redirect(url_for("admin.admin_demo_data"))


def clear_demo_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("CLEAR DEMO DATA"):
        flash("Confirmation phrase did not match.", "error")
        return redirect(url_for("admin.admin_demo_data"))

    init_db()

    try:
        result = clear_demo_seed()
    except Exception as exc:
        flash(str(exc), "error")
        return redirect(url_for("admin.admin_demo_data"))

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "clear_demo_data",
        f"resident_count={result.get('resident_count', 0)}",
    )

    flash(
        f"Demo data cleared. Removed {result.get('resident_count', 0)} residents.",
        "ok",
    )
    return redirect(url_for("admin.admin_demo_data"))


def wipe_all_data_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("WIPE ALL DATA"):
        flash("Confirmation phrase did not match.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    db_execute(
        "TRUNCATE TABLE attendance_events RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM attendance_events"
    )

    db_execute(
        "TRUNCATE TABLE resident_pass_request_details RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM resident_pass_request_details"
    )

    db_execute(
        "TRUNCATE TABLE resident_notifications RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM resident_notifications"
    )

    db_execute(
        "TRUNCATE TABLE resident_passes RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM resident_passes"
    )

    db_execute(
        "TRUNCATE TABLE transport_requests RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM transport_requests"
    )

    db_execute(
        "TRUNCATE TABLE residents RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM residents"
    )

    db_execute(
        "TRUNCATE TABLE audit_log RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM audit_log"
    )

    db_execute(
        "TRUNCATE TABLE security_incidents RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM security_incidents"
    )

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "wipe_all_data",
        "Wiped attendance, resident passes, resident notifications, transport, residents, audit_log, security_incidents",
    )

    return "All non staff data wiped."


def recreate_schema_view():
    denied = _require_dangerous_admin_access()
    if denied is not None:
        return denied

    if request.method != "POST":
        abort(405)

    if not _confirm_phrase_valid("RECREATE SCHEMA"):
        flash("Confirmation phrase did not match.", "error")
        return redirect(url_for("attendance.staff_attendance"))

    init_db()

    if g.get("db_kind") == "pg":
        db_execute("DROP TABLE IF EXISTS resident_notifications CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_pass_request_details CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_passes CASCADE")
        db_execute("DROP TABLE IF EXISTS attendance_events CASCADE")
        db_execute("DROP TABLE IF EXISTS transport_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS residents CASCADE")
        db_execute("DROP TABLE IF EXISTS audit_log CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_transfers CASCADE")
        db_execute("DROP TABLE IF EXISTS rate_limit_events CASCADE")
        db_execute("DROP TABLE IF EXISTS security_incidents CASCADE")
        db_execute("DROP TABLE IF EXISTS security_settings CASCADE")
    else:
        db_execute("DROP TABLE IF EXISTS resident_notifications")
        db_execute("DROP TABLE IF EXISTS resident_pass_request_details")
        db_execute("DROP TABLE IF EXISTS resident_passes")
        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS transport_requests")
        db_execute("DROP TABLE IF EXISTS residents")
        db_execute("DROP TABLE IF EXISTS audit_log")
        db_execute("DROP TABLE IF EXISTS resident_transfers")
        db_execute("DROP TABLE IF EXISTS security_incidents")
        db_execute("DROP TABLE IF EXISTS security_settings")

    init_db()

    log_action(
        "admin",
        None,
        None,
        session.get("staff_user_id"),
        "recreate_schema",
        "Dropped and recreated tables",
    )

    return "Schema recreated."
