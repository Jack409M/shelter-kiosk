from __future__ import annotations

from flask import abort, g, redirect, session, url_for, flash

from core.audit import log_action
from core.db import db_execute
from routes.admin_parts.helpers import require_admin_role as _require_admin


# ------------------------------------------------------------
# Dangerous Admin System Operations
# ------------------------------------------------------------
# These routes perform destructive database operations.
#
# Keeping them isolated protects the rest of the admin code
# from accidental edits and makes future permission layers
# easier to add.
#
# Future hardening ideas:
# require dual confirmation
# require special admin flag
# require time based approval token
# ------------------------------------------------------------


def wipe_all_data_view():

    from app import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    db_execute(
        "TRUNCATE TABLE attendance_events RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM attendance_events"
    )

    db_execute(
        "TRUNCATE TABLE leave_requests RESTART IDENTITY CASCADE"
        if g.get("db_kind") == "pg"
        else "DELETE FROM leave_requests"
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
        "Wiped attendance, leave, transport, residents, audit_log, security_incidents",
    )

    return "All non staff data wiped."


def recreate_schema_view():

    from app import ENABLE_DANGEROUS_ADMIN_ROUTES, init_db

    if not _require_admin():
        flash("Admin only.", "error")
        return redirect(url_for("auth.staff_home"))

    if not ENABLE_DANGEROUS_ADMIN_ROUTES:
        abort(404)

    init_db()

    if g.get("db_kind") == "pg":

        db_execute("DROP TABLE IF EXISTS attendance_events CASCADE")
        db_execute("DROP TABLE IF EXISTS leave_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS transport_requests CASCADE")
        db_execute("DROP TABLE IF EXISTS residents CASCADE")
        db_execute("DROP TABLE IF EXISTS audit_log CASCADE")
        db_execute("DROP TABLE IF EXISTS resident_transfers CASCADE")
        db_execute("DROP TABLE IF EXISTS rate_limit_events CASCADE")
        db_execute("DROP TABLE IF EXISTS security_incidents CASCADE")
        db_execute("DROP TABLE IF EXISTS security_settings CASCADE")

    else:

        db_execute("DROP TABLE IF EXISTS attendance_events")
        db_execute("DROP TABLE IF EXISTS leave_requests")
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
