"""
Database schema management helpers.
"""

from __future__ import annotations

from flask import current_app, g
from werkzeug.security import generate_password_hash

from core.db import db_execute, db_fetchall, db_fetchone


def _run_configured_init() -> None:
    """
    Run the initializer currently registered by the app.

    This remains available during the transition while schema logic
    is still being moved out of app.py.
    """
    init_func = current_app.config.get("INIT_DB_FUNC")
    if callable(init_func):
        init_func()
        return

    raise RuntimeError("Database initializer is not configured")


def _create(sqlite_sql: str, pg_sql: str, kind: str) -> None:
    """
    Execute the SQLite or Postgres version of a schema statement.
    """
    db_execute(pg_sql if kind == "pg" else sqlite_sql)


def ensure_sms_consent_columns(kind: str) -> None:
    """
    Ensure SMS consent columns exist on residents.

    Safe to run repeatedly for both Postgres and SQLite.
    """
    if kind == "pg":
        try:
            db_execute(
                "ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in BOOLEAN NOT NULL DEFAULT FALSE"
            )
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS sms_opt_out_source TEXT")
        except Exception:
            pass
    else:
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_in_source TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_at TEXT")
        except Exception:
            pass
        try:
            db_execute("ALTER TABLE residents ADD COLUMN sms_opt_out_source TEXT")
        except Exception:
            pass


def ensure_resident_code_schema(kind: str) -> None:
    """
    Ensure residents.resident_code exists and has a unique index.

    Safe to run repeatedly for both Postgres and SQLite.
    """
    try:
        if kind == "pg":
            db_execute("ALTER TABLE residents ADD COLUMN IF NOT EXISTS resident_code TEXT")
        else:
            db_execute("ALTER TABLE residents ADD COLUMN resident_code TEXT")
    except Exception:
        pass

    try:
        db_execute("CREATE UNIQUE INDEX IF NOT EXISTS residents_resident_code_uq ON residents (resident_code)")
    except Exception:
        pass


def ensure_leave_request_phone_column(kind: str) -> None:
    """
    Ensure leave_requests.resident_phone exists.

    Safe to run repeatedly for both Postgres and SQLite.
    """
    try:
        if kind == "pg":
            db_execute("ALTER TABLE leave_requests ADD COLUMN IF NOT EXISTS resident_phone TEXT")
        else:
            db_execute("ALTER TABLE leave_requests ADD COLUMN resident_phone TEXT")
    except Exception:
        pass


def drop_transport_dob_column_if_present(kind: str) -> None:
    """
    Remove the old transport_requests.dob column when running on Postgres.

    This is safe to run repeatedly and is a no op for SQLite.
    """
    if kind != "pg":
        return

    try:
        db_execute("ALTER TABLE transport_requests DROP COLUMN IF EXISTS dob")
    except Exception:
        pass


def ensure_admin_bootstrap() -> None:
    """
    Create the first admin user from environment variables if no admin exists.

    This is safe to run repeatedly. If an admin already exists, it exits.
    If the environment variables are missing, it exits.
    """
    row = db_fetchone("SELECT COUNT(1) AS c FROM staff_users WHERE role = 'admin'")
    count = int(row["c"] if isinstance(row, dict) else row[0])

    if count > 0:
        return

    admin_user = (current_app.config.get("ADMIN_USERNAME") or "").strip()
    admin_pass = (current_app.config.get("ADMIN_PASSWORD") or "").strip()

    if not admin_user or not admin_pass:
        return

    db_execute(
        "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (%s, %s, %s, %s, %s)"
        if g.get("db_kind") == "pg"
        else "INSERT INTO staff_users (username, password_hash, role, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
        (
            admin_user,
            generate_password_hash(admin_pass),
            "admin",
            True,
            current_app.config["UTCNOW_ISO_FUNC"](),
        ),
    )


def backfill_resident_codes(kind: str, make_resident_code_func) -> None:
    """
    Ensure every resident has a resident_code.

    Safe to run repeatedly. Only residents missing a code are updated.
    """
    rows = db_fetchall(
        "SELECT id FROM residents WHERE resident_code IS NULL OR resident_code = ''"
    )

    for row in rows or []:
        resident_id = row["id"] if isinstance(row, dict) else row[0]
        code = make_resident_code_func()

        for _ in range(10):
            exists = db_fetchone(
                "SELECT id FROM residents WHERE resident_code = %s"
                if kind == "pg"
                else "SELECT id FROM residents WHERE resident_code = ?",
                (code,),
            )
            if not exists:
                break
            code = make_resident_code_func()

        db_execute(
            "UPDATE residents SET resident_code = %s WHERE id = %s"
            if kind == "pg"
            else "UPDATE residents SET resident_code = ? WHERE id = ?",
            (code, resident_id),
        )


def ensure_rate_limit_events_table(kind: str) -> None:
    """
    Ensure the Postgres rate_limit_events table exists.

    Safe to run repeatedly. This is a no op for SQLite.
    """
    if kind != "pg":
        return

    db_execute(
        """
        CREATE TABLE IF NOT EXISTS rate_limit_events (
            id SERIAL PRIMARY KEY,
            k TEXT NOT NULL,
            created_at TIMESTAMP NOT NULL DEFAULT NOW()
        );
        """
    )


def ensure_rate_limit_event_indexes(kind: str) -> None:
    """
    Ensure Postgres indexes exist for rate_limit_events.

    Safe to run repeatedly. This is a no op for SQLite.
    """
    if kind != "pg":
        return

    db_execute("CREATE INDEX IF NOT EXISTS rate_limit_events_k_idx ON rate_limit_events (k)")
    db_execute("CREATE INDEX IF NOT EXISTS rate_limit_events_created_at_idx ON rate_limit_events (created_at)")


def init_db() -> None:
    """
    Current public schema entry point.

    For now this still forwards to the configured initializer.
    Later this module will own the full database bootstrap logic.
    """
    _run_configured_init()
